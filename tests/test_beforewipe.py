"""All fixtures are synthetic and confined to a newly created temporary tree."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beforewipe.__main__ import main
from beforewipe.core import assess, load_plan, render_text, verify_selection
from beforewipe.demo import create_demo
from beforewipe.fs import Root, ScopeError, digest_file, relative_parts
from beforewipe.gitmeta import parse_index


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_size, info.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None)
    return result


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="beforewipe-test-")
        self.base = Path(self.temporary.name).resolve()
        self.plan_path = create_demo(self.base / "fixture")
        self.plan = load_plan(self.plan_path)
        self.project = Path(self.plan["projects"][0]["path"])
        self.restored = Path(self.plan["recoveries"][0]["restored"])

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        isolated = self.base / "fixture" / "isolated-git-home"
        env = {"PATH": os.defpath, "HOME": str(isolated), "XDG_CONFIG_HOME": str(isolated),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        return subprocess.run([shutil.which("git"), "-c", "core.hooksPath=" + os.devnull,
                               "-c", "core.fsmonitor=false", "-c", "user.name=Fixture",
                               "-c", "user.email=test@example.invalid", *args],
                              cwd=self.project, env=env, check=True, capture_output=True, timeout=15).stdout

    def test_end_to_end_risks_and_narrow_verified_evidence(self):
        report = assess(self.plan, verify=True)
        project, sessions, recovered, stale, missing = report["items"]
        counts = project["observations"]["counts"]
        self.assertEqual(counts["metadata_changed"], 1)
        self.assertEqual(counts["files_outside_index"], 2)  # includes ignored scratch.txt
        self.assertEqual(counts["metadata_matches"], 2)
        self.assertEqual(project["observations"]["inventory"]["excluded"], 1)
        self.assertEqual(sessions["observations"]["regular_files"], 1)
        self.assertEqual(recovered["status"], "verified_content_match")
        self.assertEqual(stale["checks"][0]["status"], "mismatch")
        self.assertEqual(missing["checks"][0]["reason"], "selected_file_missing")
        self.assertEqual(report["readiness"], "not_determined")

    def test_default_reads_only_plan_and_structural_git_metadata(self):
        allowed = {self.plan_path, self.project / ".git" / "index", self.project / ".git" / "HEAD"}
        allowed.update((self.project / ".git" / "refs").rglob("*"))
        identities = {(p.stat().st_dev, p.stat().st_ino) for p in allowed if p.is_file()}
        original_read, original_open = os.read, os.open

        def guarded_read(fd, size):
            info = os.fstat(fd)
            self.assertIn((info.st_dev, info.st_ino), identities, "unexpected content read")
            return original_read(fd, size)

        def readonly_open(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return original_open(path, flags, *args, **kwargs)

        with patch("os.read", side_effect=guarded_read), patch("os.open", side_effect=readonly_open), \
                patch("subprocess.run", side_effect=AssertionError("subprocess forbidden")), \
                patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            report = assess(load_plan(self.plan_path))
        self.assertTrue(all(i["status"] == "unknown" for i in report["items"] if i["kind"] == "recovery"))

    def test_no_assessment_or_verification_writes(self):
        before = snapshot(self.base)
        assess(self.plan)
        assess(self.plan, verify=True)
        self.assertEqual(before, snapshot(self.base))

    def test_reports_omit_private_names_paths_contents_and_hashes(self):
        weird = "PRIVATE_filename\n\x1b[31m.md"
        (self.project / weird).write_text("PRIVATE_CONTENT_SENTINEL")
        self.git("branch", "PRIVATE_branch")
        self.git("remote", "add", "private", "https://user:PRIVATE_PASSWORD@example.invalid/repo")
        report = assess(self.plan, verify=True)
        for rendered in (json.dumps(report), render_text(report)):
            for forbidden in (str(self.base), weird, "PRIVATE_", "never-open-this-fixture", "session.jsonl", "src/app.py"):
                self.assertNotIn(forbidden, rendered)

    def test_cached_remote_tip_match_still_unknown(self):
        project = assess(self.plan)["items"][0]
        self.assertEqual(project["observations"]["counts"]["branch_tips_absent_from_cached_remotes"], 0)
        self.assertEqual(project["observations"]["recoverability"], "unknown")
        self.assertIn("remote_state_unverified", {f["code"] for f in project["findings"]})

    def test_stash_noncurrent_branch_and_detached_head(self):
        self.git("stash", "push", "-m", "synthetic stash")
        self.git("checkout", "-b", "unpublished")
        (self.project / "new.txt").write_text("new committed work")
        self.git("add", "new.txt")
        self.git("commit", "-m", "synthetic unpublished commit")
        self.git("checkout", "--detach")
        project = assess(self.plan)["items"][0]
        counts = project["observations"]["counts"]
        self.assertEqual(counts["stash_ref_present"], 1)
        self.assertEqual(counts["local_branches"], 2)
        self.assertEqual(counts["branch_tips_absent_from_cached_remotes"], 1)
        self.assertTrue(project["observations"]["detached_head"])

    def test_packed_refs(self):
        self.git("pack-refs", "--all", "--prune")
        project = assess(self.plan)["items"][0]
        self.assertEqual(project["observations"]["counts"]["local_branches"], 1)
        self.assertEqual(project["observations"]["counts"]["branch_tips_absent_from_cached_remotes"], 0)

    def test_staged_only_change_is_explicitly_unknown(self):
        self.git("add", "notes.md")
        project = assess(self.plan)["items"][0]
        self.assertEqual(project["observations"]["counts"]["metadata_changed"], 0)
        self.assertEqual(project["observations"]["staging_status"], "unknown")
        self.assertIn("staging_unchecked", {f["code"] for f in project["findings"]})

    def test_index_corruption_fails_closed_per_item(self):
        index = self.project / ".git" / "index"
        data = bytearray(index.read_bytes())
        data[30] ^= 1
        index.write_bytes(data)
        report = assess(self.plan, verify=True)
        self.assertEqual(report["items"][0]["reason"], "invalid_git_index_checksum")
        self.assertEqual(report["items"][2]["status"], "verified_content_match")

    def test_index_v4_is_unknown(self):
        self.git("update-index", "--index-version", "4")
        self.assertEqual(assess(self.plan)["items"][0]["reason"], "unsupported_git_index_version")

    def test_split_index_is_unknown(self):
        self.git("update-index", "--split-index")
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertIn(result["reason"], {"unsupported_split_index", "unsupported_git_index_extension"})

    def test_unmerged_index_is_detected(self):
        base = self.git("rev-parse", "HEAD").decode().strip()
        self.git("checkout", "-b", "conflict")
        (self.project / "notes.md").write_text("synthetic change on conflict branch\n")
        self.git("add", "notes.md")
        self.git("commit", "-m", "conflict side")
        other = self.git("rev-parse", "HEAD").decode().strip()
        self.git("checkout", "main")
        (self.project / "notes.md").write_text("synthetic change on main\n")
        self.git("add", "notes.md")
        self.git("commit", "-m", "main side")
        current = self.git("rev-parse", "HEAD").decode().strip()
        # read-tree constructs real conflict stages entirely in the synthetic index.
        self.git("read-tree", "-m", base, current, other)
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["observations"]["counts"]["unmerged_entries"], 3)
        self.assertIn("unmerged_index", {f["code"] for f in result["findings"]})

    def test_submodule_entry_is_explicitly_unchecked(self):
        oid = self.git("rev-parse", "HEAD").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "160000," + oid + ",nested")
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["observations"]["counts"]["submodules"], 1)
        self.assertIn("coverage_gaps", {f["code"] for f in result["findings"]})

    def test_recovery_root_failure_does_not_abort_other_checks(self):
        self.plan["recoveries"][0]["restored"] = str(self.base / "not-mounted")
        results = assess(self.plan, verify=True)["items"]
        self.assertEqual(results[2]["status"], "unknown")
        self.assertEqual(results[3]["checks"][0]["status"], "mismatch")

    def test_session_inventory_permission_error_is_visible(self):
        from beforewipe import fs
        original = fs.Root.directory

        def denied(root, parts=()):
            if root.path.name == "sessions":
                raise PermissionError("PRIVATE path must not leak")
            return original(root, parts)

        with patch.object(fs.Root, "directory", denied):
            result = assess(self.plan)["items"][1]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["observations"]["inventory"]["errors"], 1)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_default_does_not_open_recovery_roots(self):
        self.plan["recoveries"][0]["restored"] = "/not/authorized/or/mounted"
        result = assess(self.plan)["items"][2]
        self.assertEqual(result["reason"], "content_read_not_authorized")

    def test_plan_paths_are_relative_to_plan_not_process(self):
        self.assertEqual(self.plan["projects"][0]["path"], str(self.plan_path.parent / "project"))

    def test_skip_worktree_is_not_reported_clean(self):
        self.git("update-index", "--skip-worktree", "src/app.py")
        project = assess(self.plan)["items"][0]
        self.assertEqual(project["observations"]["counts"]["unchecked_entries"], 1)

    def test_missing_index_is_coverage_gap(self):
        (self.project / ".git" / "index").unlink()
        project = assess(self.plan)["items"][0]
        self.assertFalse(project["observations"]["index_present"])
        self.assertIn("index_absent", {f["code"] for f in project["findings"]})

    def test_deleted_tracked_file(self):
        (self.project / "src" / "app.py").unlink()
        self.assertEqual(assess(self.plan)["items"][0]["observations"]["counts"]["tracked_missing"], 1)

    def test_symlink_to_outside_is_skipped(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("synthetic private data")
        (self.project / "escape").symlink_to(outside, target_is_directory=True)
        report = assess(self.plan)
        self.assertEqual(report["items"][0]["observations"]["inventory"]["symlinks"], 1)
        self.assertEqual(report["items"][0]["observations"]["counts"]["files_outside_index"], 2)

    def test_symlinked_git_index_is_not_followed(self):
        index = self.project / ".git" / "index"
        index.unlink()
        index.symlink_to(self.base / "not-authorized")
        self.assertEqual(assess(self.plan)["items"][0]["status"], "unknown")

    def test_gitfile_never_follows_external_worktree_pointer(self):
        linked = self.base / "linked"
        linked.mkdir()
        (linked / ".git").write_text("gitdir: /do/not/access\n")
        self.plan["projects"][0]["path"] = str(linked)
        self.assertEqual(assess(self.plan)["items"][0]["reason"], "linked_worktree_or_gitfile_unsupported")

    def test_inventory_limit_is_visible(self):
        with patch("beforewipe.fs.MAX_ENTRIES", 1):
            project = assess(self.plan)["items"][0]
        # A refs limit must not erase independently detectable working-tree risks.
        self.assertEqual(project["status"], "attention")
        self.assertEqual(project["observations"]["coverage_errors"],
                         [{"component": "refs", "reason": "incomplete_git_refs"}])
        self.assertIsNone(project["observations"]["counts"]["local_branches"])

    def test_missing_scope_does_not_hide_other_results(self):
        self.plan["projects"][0]["path"] = str(self.base / "missing")
        report = assess(self.plan, verify=True)
        self.assertEqual(report["items"][0]["status"], "unknown")
        self.assertEqual(report["items"][2]["status"], "verified_content_match")

    def test_verification_refuses_same_file_and_hardlink(self):
        selected = self.plan["recoveries"][0]
        (self.restored / "src" / "app.py").unlink()
        os.link(self.project / "src" / "app.py", self.restored / "src" / "app.py")
        self.assertEqual(verify_selection(selected)["checks"][0]["reason"], "same_file_or_hardlink")

    def test_verification_refuses_overlapping_roots(self):
        selected = dict(self.plan["recoveries"][0], restored=str(self.project / "backup"))
        with self.assertRaisesRegex(ScopeError, "overlapping_recovery_roots"):
            verify_selection(selected)

    def test_verification_cannot_hide_agent_state_in_root(self):
        selected = dict(self.plan["recoveries"][0], source=str(self.base / ".codex" / "sessions"))
        with self.assertRaisesRegex(ScopeError, "agent_or_git_content_root_refused"):
            verify_selection(selected)

    def test_restored_selected_program_runs_in_fixture(self):
        # Execute only the known synthetic script, never arbitrary user code.
        result = subprocess.run([sys.executable, "-B", str(self.restored / "src" / "app.py")],
                                cwd=self.restored, env={"PATH": os.defpath},
                                check=True, capture_output=True, timeout=5)
        self.assertEqual(result.stdout, b"synthetic recovered work\n")

    def test_verification_refuses_secrets_and_session_files_before_open(self):
        selected = dict(self.plan["recoveries"][0], files=[".env", "credentials.json", "session.jsonl", ".git/config", ".GiT/config", "private.pem"])
        with patch("beforewipe.fs.Root.open_file", side_effect=AssertionError("must not read")):
            result = verify_selection(selected)
        self.assertTrue(all(c["reason"] == "sensitive_or_session_file_refused" for c in result["checks"]))

    def test_verification_refuses_symlink_and_fifo(self):
        (self.project / "shortcut.py").symlink_to(self.project / "src" / "app.py")
        (self.restored / "shortcut.py").write_text("not important")
        os.mkfifo(self.project / "pipe.txt")
        (self.restored / "pipe.txt").write_text("not important")
        result = verify_selection(dict(self.plan["recoveries"][0], files=["shortcut.py", "pipe.txt"]))
        self.assertTrue(all(c["reason"] == "not_regular_file" for c in result["checks"]))

    def test_verification_size_limit(self):
        with patch("beforewipe.fs.MAX_FILE_BYTES", 1):
            result = verify_selection(self.plan["recoveries"][0])
        self.assertEqual(result["checks"][0]["reason"], "file_size_limit_exceeded")

    def test_change_during_content_check_cannot_verify(self):
        real_digest = digest_file
        changed = False

        def changing_digest(root, parts, **kwargs):
            nonlocal changed
            result = real_digest(root, parts, **kwargs)
            if not changed:
                changed = True
                (self.project / "src" / "app.py").write_text("changed during check")
            return result

        with patch("beforewipe.core.digest_file", side_effect=changing_digest):
            result = verify_selection(self.plan["recoveries"][0])
        self.assertEqual(result["checks"][0]["reason"], "file_changed_during_check")

    def test_root_symlink_ancestors_and_broad_roots_refused(self):
        alias = self.base / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(OSError):
            with Root(alias / "src"):
                pass
        for value in ("/", str(Path.home())):
            with self.assertRaisesRegex(ScopeError, "scope_too_broad"):
                Root(value)

    def test_cli_exit_codes_and_json_contract(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["verify", "--plan", str(self.plan_path), "--allow-content-read", "--format", "json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["schema_version"], 1)
        only = dict(version=1, recoveries=[dict(self.plan["recoveries"][0])])
        selected_plan = self.base / "only.json"
        selected_plan.write_text(json.dumps(only))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["verify", "--plan", str(selected_plan), "--allow-content-read"]), 0)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(["verify", "--plan", str(selected_plan)])
        self.assertEqual(exc.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["assess", "--plan", str(self.base / "missing.json")]), 2)

    def test_demo_does_not_overwrite(self):
        before = snapshot(self.base)
        with self.assertRaises(FileExistsError):
            create_demo(self.base / "fixture")
        self.assertEqual(before, snapshot(self.base))


class ValidationTests(unittest.TestCase):
    def test_relative_path_escape_rejected(self):
        for path in ("../outside", "/absolute", "a/../../outside", "a//b", "a/./b", "a\\b", "", "\x00", None):
            with self.subTest(path=path), self.assertRaises(ScopeError):
                relative_parts(path)

    def test_malformed_index_never_parses_as_clean(self):
        for value in (b"", b"DIRC", b"secrets must not appear in errors", b"DIRC" + b"\0" * 64):
            with self.subTest(length=len(value)), self.assertRaises(ScopeError):
                parse_index(value)

    def test_invalid_plans_fail_without_private_values(self):
        invalid = ["{", '{"version":1,"version":1}', '{"version":true}', '{"version":2}',
                   '{"version":1}', '{"version":1,"unexpected":"PRIVATE"}',
                   '{"version":1,"projects":[{"id":"PRIVATE\\n","path":"."}]}',
                   '{"version":1,"projects":[{"id":"x","path":"~"}]}',
                   '{"version":1,"recoveries":[{"id":"x","source":"a","restored":"b","files":["../PRIVATE"]}]}']
        with tempfile.TemporaryDirectory(prefix="beforewipe-plan-") as temporary:
            path = Path(temporary).resolve() / "plan.json"
            for value in invalid:
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(ScopeError) as exc:
                    load_plan(path)
                self.assertNotIn("PRIVATE", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
