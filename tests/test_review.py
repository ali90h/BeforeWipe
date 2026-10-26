"""Independent regression cases. All data and Git commands are synthetic."""

import contextlib
import io
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import test_beforewipe as fixture_helpers
from beforewipe.__main__ import main
from beforewipe.core import assess, load_plan, render_text, verify_selection
from beforewipe.fs import Root, ScopeError, digest_file


class ReviewCase(unittest.TestCase):
    setUp = fixture_helpers.FixtureCase.setUp
    tearDown = fixture_helpers.FixtureCase.tearDown
    git = fixture_helpers.FixtureCase.git

    def clean_fixture(self):
        self.git("restore", "notes.md")
        for name in ("untracked.md", "scratch.txt", ".env"):
            (self.project / name).unlink()

    def test_substitution_cannot_verify_same_inode(self):
        original = digest_file
        changed = False

        def substitute(root, parts, **kwargs):
            nonlocal changed
            if not changed:
                changed = True
                target = self.restored / "src/app.py"
                target.unlink()
                os.link(self.project / "src/app.py", target)
            return original(root, parts, **kwargs)

        with patch("beforewipe.core.digest_file", side_effect=substitute):
            check = verify_selection(self.plan["recoveries"][0])["checks"][0]
        self.assertEqual(check["status"], "unknown")

    def test_selected_replacement_is_rejected_before_content_read(self):
        original = digest_file
        selected = self.project / "src/app.py"
        replacement = self.project / "replacement.py"
        replacement.write_text("synthetic unreviewed replacement")
        inode = replacement.stat().st_ino
        original_read = os.read

        def substitute(root, parts, **kwargs):
            if replacement.exists():
                os.replace(replacement, selected)
            return original(root, parts, **kwargs)

        def guarded(fd, size):
            self.assertNotEqual(os.fstat(fd).st_ino, inode, "unreviewed replacement read")
            return original_read(fd, size)

        with patch("beforewipe.core.digest_file", side_effect=substitute), patch("os.read", side_effect=guarded):
            check = verify_selection(self.plan["recoveries"][0])["checks"][0]
        self.assertEqual(check["status"], "unknown")

    def test_hardlinked_git_metadata_never_reads_work_file(self):
        target = self.project / ".git/refs/heads/main"
        target.unlink()
        source = self.project / ".env"
        os.link(source, target)
        identity = (source.stat().st_dev, source.stat().st_ino)
        original_read = os.read

        def guarded(fd, size):
            info = os.fstat(fd)
            self.assertNotEqual((info.st_dev, info.st_ino), identity, "sensitive hardlink read")
            return original_read(fd, size)

        with patch("os.read", side_effect=guarded):
            result = assess(self.plan)["items"][0]
        self.assertIn("hardlinked_metadata_refused", json.dumps(result))

    def test_nested_git_is_visible_even_without_worktree_files(self):
        self.clean_fixture()
        nested = self.project / "nested"
        nested.mkdir()
        self.git("init", "-b", "main", str(nested))
        result = assess(self.plan)["items"][0]
        self.assertIn("coverage_gaps", {f["code"] for f in result["findings"]})
        self.assertEqual(result["observations"]["inventory"]["git_entries_skipped"], 1)

    def test_inaccessible_refs_do_not_erase_working_tree_risks(self):
        (self.project / ".git/refs/heads/main").write_text("invalid synthetic ref")
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["status"], "attention")
        self.assertEqual(result["observations"]["counts"]["metadata_changed"], 1)
        self.assertEqual(result["observations"]["counts"]["files_outside_index"], 2)
        self.assertIsNone(result["observations"]["counts"]["local_branches"])
        self.assertIn("unsupported_or_invalid_git_refs", json.dumps(result))

    def test_incomplete_backup_does_not_verify_project(self):
        result = assess(self.plan, verify=True)
        self.assertEqual(result["items"][2]["status"], "verified_content_match")
        self.assertEqual(result["items"][0]["observations"]["recoverability"], "unknown")
        self.assertEqual(result["readiness"], "not_determined")
        # The restore contains no Git history and lacks important unselected work.
        self.assertFalse((self.restored / ".git").exists())
        self.assertFalse((self.restored / "untracked.md").exists())

    def test_multiple_selections_cannot_hide_missing_file(self):
        selected = dict(self.plan["recoveries"][0], files=["src/app.py", "untracked.md"])
        result = verify_selection(selected)
        self.assertEqual([c["status"] for c in result["checks"]], ["match", "unknown"])
        self.assertEqual(result["status"], "unknown")

    def test_staged_only_variants_against_git_oracle(self):
        self.clean_fixture()
        for variant in ("modified", "added", "deleted", "renamed", "index_only"):
            with self.subTest(variant=variant):
                self.git("reset", "--hard", "HEAD")
                if variant == "modified":
                    (self.project / "notes.md").write_text("staged synthetic edit\n")
                    self.git("add", "notes.md")
                elif variant == "added":
                    (self.project / "added.md").write_text("staged synthetic addition\n")
                    self.git("add", "added.md")
                elif variant == "deleted":
                    self.git("rm", "notes.md")
                elif variant == "renamed":
                    self.git("mv", "notes.md", "renamed.md")
                else:
                    (self.project / "notes.md").write_text("only staged blob retains this work\n")
                    self.git("add", "notes.md")
                    self.git("restore", "--source=HEAD", "--worktree", "notes.md")
                if variant != "index_only":
                    self.git("update-index", "--refresh")
                self.assertTrue(self.git("diff", "--cached", "--name-status"))
                result = assess(self.plan)["items"][0]
                self.assertEqual(result["observations"]["staging_status"], "unknown")
                self.assertEqual(result["observations"]["recoverability"], "unknown")
                self.assertIn("staging_unchecked", {f["code"] for f in result["findings"]})
                self.assertNotEqual(result["status"], "verified_content_match")
                if variant in {"modified", "added", "deleted"}:
                    self.assertEqual(result["observations"]["counts"]["metadata_changed"], 0)

    def test_root_replacement_cannot_verify_old_directory(self):
        original = digest_file
        changed = False

        def replace_root(root, parts, **kwargs):
            nonlocal changed
            result = original(root, parts, **kwargs)
            if not changed:
                changed = True
                self.restored.rename(self.restored.with_name("old-restored"))
                self.restored.mkdir()
            return result

        with patch("beforewipe.core.digest_file", side_effect=replace_root):
            result = verify_selection(self.plan["recoveries"][0])
        self.assertEqual(result["checks"][0]["status"], "unknown")

    def test_matching_work_files_do_not_preserve_index_only_work(self):
        self.clean_fixture()
        (self.project / "notes.md").write_text("work held only in staged blob\n")
        self.git("add", "notes.md")
        self.git("restore", "--source=HEAD", "--worktree", "notes.md")
        self.assertTrue(self.git("diff", "--cached", "--name-only"))
        result = verify_selection(dict(self.plan["recoveries"][0], files=["notes.md"]))
        self.assertEqual(result["status"], "verified_content_match")
        self.assertEqual(result["verification_scope"], "selected_file_bytes")
        self.assertEqual(result["recoverability"], "unknown")
        report = assess(self.plan, verify=True)
        self.assertIn("does not preserve staged-only work", render_text(report))

    def test_metadata_touch_is_inferred_even_when_git_diff_empty(self):
        self.clean_fixture()
        path = self.project / "notes.md"
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["observations"]["counts"]["metadata_changed"], 1)
        self.assertFalse(self.git("diff", "--name-only"))
        finding = next(f for f in result["findings"] if f["code"] == "working_tree_metadata_differs")
        self.assertEqual(finding["evidence"], "inferred")

    def test_branch_behind_cached_remote_is_not_claimed_unpublished(self):
        self.clean_fixture()
        self.git("branch", "older")
        (self.project / "notes.md").write_text("synthetic remote also has this commit\n")
        self.git("add", "notes.md")
        self.git("commit", "-m", "synthetic published commit")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("merge-base", "--is-ancestor", "older", "refs/remotes/origin/main")
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["observations"]["counts"]["branch_tips_absent_from_cached_remotes"], 1)
        finding = next(f for f in result["findings"] if f["code"] == "branch_tip_not_in_cached_remotes")
        self.assertEqual(finding["evidence"], "inferred")
        self.assertIn("does not prove commits are unpublished", finding["detail"])

    def test_double_slash_broad_roots_refused_before_access(self):
        with patch("os.open", side_effect=AssertionError("must refuse before access")):
            for value in ("//", "/" + str(Path.home())):
                with self.subTest(value=value), self.assertRaisesRegex(ScopeError, "scope_too_broad"):
                    with Root(value):
                        pass

    def test_case_variant_home_is_conservatively_refused(self):
        synthetic_home = self.base / "home"
        with patch("beforewipe.fs.Path.home", return_value=synthetic_home), \
                patch("os.open", side_effect=AssertionError("no home access")):
            with self.assertRaisesRegex(ScopeError, "scope_too_broad"):
                Root(self.base / "HOME")

    def test_case_variant_overlapping_recovery_is_refused(self):
        selected = dict(self.plan["recoveries"][0], restored=str(self.project.parent / "PROJECT" / "backup"))
        with patch("os.open", side_effect=AssertionError("no content access")):
            with self.assertRaisesRegex(ScopeError, "overlapping_recovery_roots"):
                verify_selection(selected)

    def test_dotdot_scope_not_silently_reinterpreted(self):
        alias = self.base / "alias"
        alias.symlink_to(self.project / "src", target_is_directory=True)
        value = str(alias) + "/../fixture/project"
        with patch("os.open", side_effect=AssertionError("must refuse before access")):
            with self.assertRaisesRegex(ScopeError, "ambiguous_scope_path"):
                Root(value)
        plan = self.base / "ambiguous.json"
        plan.write_text(json.dumps({"version": 1, "projects": [{"id": "p", "path": value}]}))
        with self.assertRaisesRegex(ScopeError, "ambiguous_scope_path"):
            load_plan(plan)

    def test_nested_plan_json_has_controlled_cli_error(self):
        plan = self.base / "deep.json"
        plan.write_text('{"version":1,"projects":' + "[" * 1100 + "]" * 1100 + "}")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["assess", "--plan", str(plan)]), 2)
        self.assertIn("invalid_plan_json", stderr.getvalue())
        self.assertNotIn(str(self.base), stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_hardlink_substituted_during_metadata_open_is_not_read(self):
        target = self.project / ".git/refs/heads/main"
        source = self.project / ".env"
        original_open, original_read = os.open, os.read
        inode = source.stat().st_ino
        changed = False

        def replace(path, flags, *args, **kwargs):
            nonlocal changed
            if path == "main" and not flags & os.O_DIRECTORY and not changed:
                changed = True
                target.unlink()
                os.link(source, target)
            return original_open(path, flags, *args, **kwargs)

        def guarded(fd, size):
            self.assertNotEqual(os.fstat(fd).st_ino, inode)
            return original_read(fd, size)

        with patch("os.open", side_effect=replace), patch("os.read", side_effect=guarded):
            result = assess(self.plan)["items"][0]
        self.assertTrue(changed)
        self.assertIn("hardlinked_metadata_refused", json.dumps(result))

    def test_metadata_replacement_during_read_is_unknown(self):
        target = self.project / ".git/refs/heads/main"
        original_read = os.read
        inode = target.stat().st_ino
        changed = False

        def replace(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if os.fstat(fd).st_ino == inode and not changed:
                changed = True
                target.unlink()
                target.write_text("0" * 40 + "\n")
            return data

        with patch("os.read", side_effect=replace):
            result = assess(self.plan)["items"][0]
        self.assertTrue(changed)
        self.assertIn("metadata_changed_during_check", json.dumps(result))
        self.assertIsNone(result["observations"]["counts"]["local_branches"])

    def test_session_gaps_never_establish_recoverability(self):
        sessions = Path(self.plan["sessions"][0]["path"])
        (sessions / "alias").symlink_to(self.project, target_is_directory=True)
        (sessions / ".env").write_text("SYNTHETIC=not-read")
        (sessions / ".git").mkdir()
        os.mkfifo(sessions / "pipe")
        with patch("beforewipe.fs.Root.open_file", side_effect=AssertionError("no session content read")):
            # Assess only sessions so the forbidden-open guard is exact.
            result = assess(dict(projects=[], recoveries=[], sessions=self.plan["sessions"]))["items"][0]
        scan = result["observations"]["inventory"]
        self.assertEqual((scan["excluded"], scan["symlinks"], scan["special"], scan["git_entries_skipped"]), (1, 1, 1, 1))
        self.assertEqual(result["observations"]["regular_files"], 1)
        self.assertEqual(result["observations"]["recoverability"], "unknown")

    @unittest.skipIf(os.geteuid() == 0, "root bypasses filesystem permission checks")
    def test_real_inaccessible_session_subdirectory_is_counted(self):
        sessions = Path(self.plan["sessions"][0]["path"])
        inaccessible = sessions / "unreadable"
        inaccessible.mkdir()
        (inaccessible / "session.jsonl").write_text("synthetic not read")
        inaccessible.chmod(0)
        try:
            result = assess(self.plan)["items"][1]
        finally:
            inaccessible.chmod(0o700)
        self.assertEqual(result["observations"]["inventory"]["errors"], 1)
        self.assertEqual(result["observations"]["regular_files"], 1)
        self.assertEqual(result["observations"]["recoverability"], "unknown")

    def test_depth_limit_is_explicit(self):
        with patch("beforewipe.fs.MAX_DEPTH", 0):
            result = assess(self.plan)["items"][0]
        self.assertTrue(result["observations"]["inventory"]["limited"])
        self.assertIn("coverage_gaps", {f["code"] for f in result["findings"]})

    def test_actual_linked_worktree_is_refused_without_pointer_read(self):
        linked = self.base / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        plan = dict(projects=[dict(id="linked", path=str(linked))], sessions=[], recoveries=[])
        with patch("os.read", side_effect=AssertionError("must not read worktree pointer")):
            result = assess(plan)["items"][0]
        self.assertEqual(result["reason"], "linked_worktree_or_gitfile_unsupported")

    def test_actual_sha256_repository_is_unknown(self):
        project = self.base / "sha256"
        try:
            self.git("init", "--object-format=sha256", "-b", "main", str(project))
        except subprocess.CalledProcessError:
            self.skipTest("fixture Git does not support SHA-256 repositories")
        self.project = project
        (project / "notes.md").write_text("synthetic SHA-256 staged work")
        self.git("add", "notes.md")
        self.git("commit", "-m", "synthetic initial work")
        plan = dict(projects=[dict(id="sha256", path=str(project))], sessions=[], recoveries=[])
        result = assess(plan)["items"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertIn("reason", result)

    def test_bare_repository_is_unknown(self):
        bare = self.base / "bare"
        self.git("init", "--bare", str(bare))
        plan = dict(projects=[dict(id="bare", path=str(bare))], sessions=[], recoveries=[])
        result = assess(plan)["items"][0]
        self.assertEqual(result["reason"], "not_a_git_root")
        self.assertEqual(result["status"], "unknown")

    def test_tracked_symlink_is_explicitly_unchecked(self):
        (self.project / "shortcut").symlink_to("notes.md")
        self.git("add", "shortcut")
        result = assess(self.plan)["items"][0]
        self.assertEqual(result["observations"]["counts"]["unchecked_entries"], 1)
        self.assertEqual(result["observations"]["inventory"]["symlinks"], 1)

    def test_tracked_sensitive_file_is_not_opened(self):
        self.git("add", "-f", ".env")
        identity = (self.project / ".env").stat().st_ino
        original_read = os.read

        def guarded(fd, size):
            self.assertNotEqual(os.fstat(fd).st_ino, identity)
            return original_read(fd, size)

        with patch("os.read", side_effect=guarded):
            result = assess(self.plan)["items"][0]
        self.assertEqual(result["observations"]["counts"]["unchecked_entries"], 1)
        self.assertEqual(result["observations"]["inventory"]["excluded"], 1)


if __name__ == "__main__":
    unittest.main()
