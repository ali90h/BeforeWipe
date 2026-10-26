"""Staging regressions with isolated real Git repositories as an independent oracle.

Git is used only to construct/query synthetic fixtures, never by BeforeWipe.
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from beforewipe.__main__ import main
from beforewipe.core import assess, render_text
from beforewipe.fs import Root
from test_beforewipe import snapshot


class StagingCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="beforewipe-staging-")
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        home = self.base / "isolated-home"
        home.mkdir()
        self.env = {"PATH": os.defpath, "HOME": str(home), "XDG_CONFIG_HOME": str(home),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        self.git("init", "-b", "main")
        for name in ("notes.md", "src/app.py", "other/stable.txt"):
            path = self.project / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("synthetic initial work\n")
        self.git("add", ".")
        self.git("commit", "-m", "synthetic initial commit")
        self.restored = self.base / "restored"
        shutil.copytree(self.project, self.restored, ignore=shutil.ignore_patterns(".git"))
        self.plan = dict(version=1, projects=[dict(id="project", path=str(self.project))], sessions=[],
                         recoveries=[dict(id="copy", source=str(self.project), restored=str(self.restored), files=["notes.md"])])

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args, input=None):
        return subprocess.run([shutil.which("git"), "-c", "core.hooksPath=" + os.devnull,
                               "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false",
                               "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                              input=input, cwd=self.project, env=self.env, check=True,
                              capture_output=True, timeout=15).stdout

    def result(self):
        return assess(self.plan, allow_git_object_read=True)["items"][0]

    def staging(self):
        return self.result()["observations"]["staging"]

    def oracle(self):
        raw = self.git("diff", "--cached", "--no-renames", "--name-status", "-z").split(b"\0")
        counts = dict(added=0, modified=0, deleted=0)
        for status in raw[:-1:2]:
            counts[{b"A": "added", b"D": "deleted", b"M": "modified", b"T": "modified"}[status]] += 1
        return counts

    def object_path(self, revision):
        oid = self.git("rev-parse", revision).strip().decode("ascii")
        return self.project / ".git/objects" / oid[:2] / oid[2:]

    def write_object(self, kind, body):
        raw = kind + b" " + str(len(body)).encode() + b"\0" + body
        oid = hashlib.sha1(raw).hexdigest()
        target = self.project / ".git/objects" / oid[:2] / oid[2:]
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(zlib.compress(raw))
        return oid

    def set_tree(self, body):
        oid = self.write_object(b"tree", body)
        commit = (b"tree " + oid.encode() + b"\nauthor Fixture <test@example.invalid> 1 +0000\n"
                  b"committer Fixture <test@example.invalid> 1 +0000\n\nsynthetic commit\n")
        head = self.write_object(b"commit", commit)
        (self.project / ".git/refs/heads/main").write_text(head + "\n")

    def test_real_git_staged_scenarios(self):
        for variant in ("modified", "added", "deleted", "renamed", "index_only", "mode", "symlink", "gitlink"):
            with self.subTest(variant=variant):
                self.git("reset", "--hard", "HEAD")
                if variant in ("modified", "index_only"):
                    (self.project / "notes.md").write_text("synthetic staged-only version\n")
                    self.git("add", "notes.md")
                    if variant == "index_only":
                        self.git("restore", "--source=HEAD", "--worktree", "notes.md")
                elif variant == "added":
                    (self.project / "added.md").write_text("synthetic new work\n")
                    self.git("add", "added.md")
                elif variant == "deleted":
                    self.git("rm", "notes.md")
                elif variant == "renamed":
                    self.git("mv", "notes.md", "renamed.md")
                elif variant == "mode":
                    self.git("update-index", "--chmod=+x", "notes.md")
                elif variant == "symlink":
                    (self.project / "notes.md").unlink()
                    (self.project / "notes.md").symlink_to("src/app.py")
                    self.git("add", "notes.md")
                else:
                    oid = self.git("rev-parse", "HEAD").strip().decode()
                    self.git("update-index", "--add", "--cacheinfo", "160000," + oid + ",nested")
                expected = self.oracle()
                self.assertTrue(any(expected.values()))
                result = self.result()
                staging = result["observations"]["staging"]
                self.assertEqual(staging["changes"], expected)
                self.assertEqual(staging["status"], "confirmed_risk")
                self.assertEqual(staging["coverage"], "complete")
                if variant in {"modified", "added", "deleted"}:
                    self.assertEqual(result["observations"]["counts"]["metadata_changed"], 0)
                    self.assertEqual(result["observations"]["counts"]["tracked_missing"], 0)

    def test_original_loss_reproduction_with_matching_working_copy(self):
        (self.project / "notes.md").write_text("version present only in the staged blob\n")
        self.git("add", "notes.md")
        self.git("restore", "--source=HEAD", "--worktree", "notes.md")
        self.assertEqual(self.oracle(), dict(added=0, modified=1, deleted=0))
        self.assertNotEqual(self.git("show", ":notes.md"), (self.restored / "notes.md").read_bytes())
        report = assess(self.plan, verify=True, allow_git_object_read=True)
        project, recovery = report["items"]
        self.assertEqual(recovery["status"], "verified_content_match")
        self.assertEqual(project["status"], "attention")
        self.assertEqual(project["observations"]["staging_status"], "confirmed_risk")
        self.assertEqual(project["observations"]["recoverability"], "unknown")
        self.assertEqual(report["summary"]["attention"], 1)
        self.assertEqual(report["readiness"], "not_determined")
        text = render_text(report)
        self.assertIn("confirmed_risk", text)
        self.assertIn("does not preserve staged-only work", text)
        self.assertFalse((self.restored / ".git").exists())

    def test_empty_diff_is_narrow_observation(self):
        self.assertFalse(any(self.oracle().values()))
        staging = self.staging()
        self.assertEqual(staging["status"], "no_difference_observed")
        self.assertEqual(staging["coverage"], "complete")
        self.assertEqual(self.result()["observations"]["recoverability"], "unknown")

    def test_empty_index_detects_staged_deletions(self):
        self.git("read-tree", "--empty")
        self.assertEqual(self.staging()["changes"], self.oracle())
        self.assertEqual(self.staging()["changes"]["deleted"], 3)

    def test_detached_head_and_packed_refs(self):
        self.git("pack-refs", "--all", "--prune")
        self.assertEqual(self.staging()["status"], "no_difference_observed")
        self.git("checkout", "--detach")
        self.git("rm", "notes.md")
        self.assertEqual(self.staging()["changes"], self.oracle())

    def test_v3_assume_unchanged_and_skip_worktree_compare_ids(self):
        (self.project / "notes.md").write_text("staged\n")
        self.git("add", "notes.md")
        self.git("update-index", "--assume-unchanged", "notes.md")
        self.git("update-index", "--skip-worktree", "src/app.py")
        self.git("update-index", "--index-version", "3")
        self.assertEqual(self.staging()["changes"], self.oracle())
        self.assertEqual(self.staging()["coverage"], "complete")

    def test_intent_to_add_is_incomplete_not_confirmed_addition(self):
        (self.project / "intent.md").write_text("not staged yet\n")
        self.git("add", "-N", "intent.md")
        staging = self.staging()
        self.assertEqual(staging["status"], "unknown")
        self.assertEqual(staging["coverage"], "incomplete")
        self.assertFalse(any(staging["changes"].values()))

    def test_conflict_stages_do_not_appear_as_deletions(self):
        oid = self.git("rev-parse", "HEAD:notes.md").strip()
        data = b"".join(b"100644 " + oid + b" " + str(stage).encode() + b"\tnotes.md\n" for stage in (1, 2, 3))
        self.git("update-index", "--index-info", input=b"0 " + b"0" * 40 + b"\tnotes.md\n" + data)
        result = self.result()
        staging = result["observations"]["staging"]
        self.assertEqual(staging["coverage"], "incomplete")
        self.assertFalse(any(staging["changes"].values()))
        self.assertIn("unmerged_index", {f["code"] for f in result["findings"]})

    def test_missing_subtree_retains_independent_confirmed_difference(self):
        self.git("rm", "notes.md")
        self.object_path("HEAD:other").unlink()
        staging = self.staging()
        self.assertEqual(staging["status"], "confirmed_risk")
        self.assertEqual(staging["changes"]["deleted"], 1)
        self.assertEqual(staging["coverage"], "incomplete")
        self.assertTrue(staging["counts_are_lower_bounds"])

    def test_packed_objects_are_explicitly_unknown(self):
        self.git("gc", "--prune=now")
        self.git("rm", "notes.md")
        self.assertTrue(any(self.oracle().values()))
        staging = self.staging()
        self.assertEqual(staging["status"], "unknown")
        self.assertIn("loose_object_missing_packed_or_external_unsupported", staging["reason_codes"])

    def test_missing_blob_is_not_opened_or_claimed_recoverable(self):
        # ID comparison is useful even if a referenced blob has already been lost.
        self.git("rm", "notes.md")
        self.object_path("HEAD:notes.md").unlink()
        result = self.result()
        self.assertEqual(result["observations"]["staging_status"], "confirmed_risk")
        self.assertEqual(result["observations"]["recoverability"], "unknown")

    def test_default_and_content_consent_do_not_authorize_object_reads(self):
        original = Root.metadata

        def guarded(root, parts, limit):
            self.assertNotEqual(parts[:2], (".git", "objects"))
            return original(root, parts, limit)

        with patch.object(Root, "metadata", guarded):
            for verify in (False, True):
                result = assess(self.plan, verify=verify)["items"][0]
                self.assertEqual(result["observations"]["staging"]["coverage"], "not_inspected")

    def test_opt_in_read_audit_no_blobs_work_files_config_subprocess_network_or_writes(self):
        names = ("HEAD", "HEAD^{tree}", "HEAD:src", "HEAD:other")
        allowed = [self.object_path(n) for n in names]
        allowed += [self.project / ".git/index", self.project / ".git/HEAD", self.project / ".git/refs/heads/main"]
        identities = {(p.stat().st_dev, p.stat().st_ino) for p in allowed}
        original_read, original_open = os.read, os.open
        before = snapshot(self.base)

        def read(fd, size):
            info = os.fstat(fd)
            self.assertIn((info.st_dev, info.st_ino), identities)
            return original_read(fd, size)

        def open_readonly(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return original_open(path, flags, *args, **kwargs)

        with patch("os.read", side_effect=read), patch("os.open", side_effect=open_readonly), \
                patch("subprocess.run", side_effect=AssertionError("Git subprocess forbidden")), \
                patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.staging()["status"], "no_difference_observed")
        self.assertEqual(snapshot(self.base), before)

    def test_cli_object_consent_is_independent_of_selected_content_consent(self):
        plan = self.base / "plan.json"
        plan.write_text(json.dumps(self.plan))
        for flags, authorized in (([], False), (["--allow-git-object-read"], True)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["assess", "--plan", str(plan), "--format", "json"] + flags), 1)
            report = json.loads(output.getvalue())
            self.assertEqual(report["git_object_read_authorized"], authorized)
            self.assertEqual(report["items"][1]["reason"], "content_read_not_authorized")

    def test_reports_do_not_disclose_object_messages_names_ids_or_bytes(self):
        name = "PRIVATE_name\n\x1b[31m.md"
        (self.project / name).write_text("PRIVATE_PAYLOAD")
        self.git("add", name)
        self.git("commit", "-m", "PRIVATE_COMMIT_MESSAGE")
        self.git("rm", name)
        oid = self.git("rev-parse", "HEAD").strip().decode()
        report = assess(self.plan, allow_git_object_read=True)
        for output in (json.dumps(report), render_text(report)):
            self.assertNotIn("PRIVATE_", output)
            self.assertNotIn(oid, output)
            self.assertNotIn(str(self.base), output)

    def test_malformed_objects_are_unknown_and_content_free(self):
        target = self.object_path("HEAD")
        original = target.read_bytes()
        target.chmod(0o600)
        variants = (b"PRIVATE_invalid_zlib", zlib.compress(b"blob 7\0PRIVATE"),
                    original + b"PRIVATE_trailing", zlib.compress(b"commit 7\0PRIVATE"),
                    zlib.compress(zlib.decompress(original).replace(b"synthetic initial", b"synthetic altered")),
                    zlib.compress(b"commit 999999999\0" + b"x" * 100000))
        for raw in variants:
            with self.subTest(size=len(raw)):
                target.write_bytes(raw)
                staging = self.staging()
                self.assertEqual(staging["status"], "unknown")
                self.assertNotIn("PRIVATE", json.dumps(staging))
        target.write_bytes(original)
        with patch("beforewipe.staging.MAX_OBJECT_BYTES", 1000):
            target.write_bytes(zlib.compress(b"commit 999999999\0" + b"x" * 100000))
            self.assertIn("git_object_byte_limit", self.staging()["reason_codes"])

    def test_malformed_tree_paths_modes_order_and_duplicate_names(self):
        oid = bytes.fromhex(self.git("rev-parse", "HEAD:notes.md").strip().decode())
        for raw in (b"100644 ../escape\0" + oid, b"100644 .git\0" + oid,
                    b"100644 a/b\0" + oid, b"40000 a\0" + oid + b"100644 a\0" + oid,
                    (b"100644 a\0" + oid) * 2, b"100600 a\0" + oid,
                    b"100644 z\0" + oid + b"100644 a\0" + oid,
                    b"100644 a\0short", b"100644 a\0" + b"\0" * 20):
            with self.subTest(size=len(raw)):
                self.set_tree(raw)
                staging = self.staging()
                self.assertEqual(staging["status"], "unknown")
                self.assertEqual(staging["coverage"], "incomplete")
                self.assertFalse(any(staging["changes"].values()))

    def test_object_limits_report_incomplete(self):
        for name, value in (("MAX_OBJECTS", 1), ("MAX_TOTAL_BYTES", 1), ("MAX_TREE_ENTRIES", 1), ("MAX_TREE_DEPTH", 0)):
            with self.subTest(limit=name), patch("beforewipe.staging." + name, value):
                self.assertEqual(self.staging()["coverage"], "incomplete")

    def test_object_symlink_hardlink_and_fifo_refused_before_read(self):
        target = self.object_path("HEAD")
        original = target.read_bytes()
        sentinel = self.base / "outside-sentinel"
        sentinel.write_bytes(b"SYNTHETIC_PRIVATE_SENTINEL")
        inode = sentinel.stat().st_ino
        original_read = os.read

        def read(fd, size):
            self.assertNotEqual(os.fstat(fd).st_ino, inode)
            return original_read(fd, size)

        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                target.unlink()
                if kind == "symlink":
                    target.symlink_to(sentinel)
                elif kind == "hardlink":
                    os.link(sentinel, target)
                else:
                    os.mkfifo(target)
                with patch("os.read", side_effect=read):
                    self.assertEqual(self.staging()["status"], "unknown")
                target.unlink()
                target.write_bytes(original)

    def test_object_hardlink_substitution_during_open_rejected_before_read(self):
        target = self.object_path("HEAD")
        sentinel = self.base / "outside-sentinel"
        sentinel.write_bytes(b"SYNTHETIC_PRIVATE_SENTINEL")
        inode = sentinel.stat().st_ino
        original_open, original_read = os.open, os.read
        changed = False

        def open_substitute(path, flags, *args, **kwargs):
            nonlocal changed
            if path == target.name and not flags & os.O_DIRECTORY and not changed:
                changed = True
                target.unlink()
                os.link(sentinel, target)
            return original_open(path, flags, *args, **kwargs)

        def read(fd, size):
            self.assertNotEqual(os.fstat(fd).st_ino, inode)
            return original_read(fd, size)

        with patch("os.open", side_effect=open_substitute), patch("os.read", side_effect=read):
            self.assertIn("hardlinked_metadata_refused", self.staging()["reason_codes"])
        self.assertTrue(changed)

    def test_symlinked_object_directory_cannot_escape_scope(self):
        target = self.object_path("HEAD")
        external = self.base / "external-objects"
        target.parent.rename(external)
        target.parent.symlink_to(external, target_is_directory=True)
        original = Root.metadata

        def guarded(root, parts, limit):
            self.assertEqual(root.path, self.project)
            return original(root, parts, limit)

        with patch.object(Root, "metadata", guarded):
            self.assertEqual(self.staging()["status"], "unknown")

    def test_alternates_and_config_are_not_followed(self):
        target = self.object_path("HEAD")
        target.unlink()
        (self.project / ".git/objects/info/alternates").write_text(str(self.base / "outside"))
        original = Root.metadata

        def guarded(root, parts, limit):
            self.assertNotIn("alternates", parts)
            self.assertNotIn("config", parts)
            self.assertEqual(root.path, self.project)
            return original(root, parts, limit)

        with patch.object(Root, "metadata", guarded):
            self.assertEqual(self.staging()["status"], "unknown")

    def test_changed_index_or_head_during_comparison_invalidates_confirmation(self):
        self.git("rm", "notes.md")
        for kind in ("index", "HEAD", "refs"):
            with self.subTest(kind=kind):
                original = Root.metadata
                reads = 0
                target = (".git", "refs", "heads", "main") if kind == "refs" else (".git", kind)

                def mutate(root, parts, limit):
                    nonlocal reads
                    raw = original(root, parts, limit)
                    if parts == target:
                        reads += 1
                        if reads == 2:
                            return raw + b" " if kind == "index" else b"0" * 40
                    return raw

                with patch.object(Root, "metadata", mutate):
                    staging = self.staging()
                self.assertEqual(staging["status"], "unknown")
                self.assertFalse(any(staging["changes"].values()))

    def test_unborn_head_and_missing_index_not_treated_as_empty_baseline(self):
        (self.project / ".git/refs/heads/main").unlink()
        self.assertEqual(self.staging()["coverage"], "unsupported")
        (self.project / ".git/index").unlink()
        self.assertIn("index_absent", self.staging()["reason_codes"])

    def test_replace_refs_refused(self):
        self.git("replace", "HEAD", "HEAD")
        self.assertEqual(self.staging()["coverage"], "unsupported")

    def test_malformed_packed_refs_cannot_supply_committed_baseline(self):
        self.git("pack-refs", "--all", "--prune")
        self.git("rm", "notes.md")
        packed = self.project / ".git/packed-refs"
        original = packed.read_bytes()
        for extra in (b"0" * 40 + b" refs/heads/main\n", b"^PRIVATE_invalid_peeled_ref\n"):
            with self.subTest(extra_length=len(extra)):
                packed.write_bytes(original + extra)
                result = self.result()
                self.assertEqual(result["observations"]["staging_status"], "unknown")
                self.assertIn("git_refs_incomplete", result["observations"]["staging"]["reason_codes"])
                self.assertNotIn("PRIVATE", json.dumps(result))

    def test_unsupported_layouts_have_machine_readable_staging(self):
        self.git("update-index", "--index-version", "4")
        result = self.result()
        self.assertEqual(result["observations"]["staging"]["status"], "unsupported")
        self.assertIn("unsupported_git_index_version", result["observations"]["staging"]["reason_codes"])
        self.assertIn("unsupported", render_text(assess(self.plan, allow_git_object_read=True)))

    def test_real_split_and_sparse_indexes_remain_unsupported(self):
        self.git("update-index", "--split-index")
        self.assertEqual(self.result()["observations"]["staging"]["coverage"], "unsupported")
        self.git("update-index", "--no-split-index")
        self.git("sparse-checkout", "init", "--cone", "--sparse-index")
        self.git("sparse-checkout", "set", "src")
        self.assertEqual(self.result()["observations"]["staging"]["coverage"], "unsupported")

    def test_real_linked_worktree_does_not_read_pointer_even_with_consent(self):
        linked = self.base / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        self.plan["projects"][0]["path"] = str(linked)
        with patch("os.read", side_effect=AssertionError("pointer must not be read")):
            result = self.result()
        self.assertEqual(result["observations"]["staging"]["coverage"], "unsupported")

    def test_valid_checksum_does_not_hide_invalid_index_ids_modes_or_duplicates(self):
        index = self.project / ".git/index"
        original = index.read_bytes()
        for variant in ("zero_oid", "bad_mode", "duplicate"):
            with self.subTest(variant=variant):
                data = bytearray(original[:-20])
                if variant == "zero_oid":
                    data[52:72] = b"\0" * 20
                elif variant == "bad_mode":
                    struct.pack_into(">I", data, 36, 0o100600)
                else:
                    stop = data.index(0, 74)
                    end = 12 + ((stop + 1 - 12 + 7) // 8) * 8
                    data[end:end] = data[12:end]
                    struct.pack_into(">I", data, 8, 4)
                index.write_bytes(data + hashlib.sha1(data).digest())
                result = self.result()
                self.assertNotEqual(result["observations"]["staging"]["status"], "confirmed_risk")
                self.assertIn("reason", result)

    def test_valid_tree_sorting_and_non_utf8_names_against_git(self):
        # Directory ordering uses a trailing slash; filenames may contain arbitrary
        # non-NUL bytes. They must neither escape scope nor leak into reports.
        for name in ("other.c", "other0", "space name", "line\nname"):
            (self.project / name).write_text("synthetic\n")
        self.git("add", ".")
        # Some filesystems refuse non-UTF8 working names; Git can still hold
        # them in its index/tree. Stage through Git instead of inventing a tree.
        oid = self.git("rev-parse", "HEAD:notes.md").strip()
        self.git("update-index", "-z", "--index-info", input=b"100644 " + oid + b"\tnon_utf8_\xff\0")
        self.git("commit", "-m", "synthetic ordering fixture")
        self.assertEqual(self.staging()["status"], "no_difference_observed")
        self.git("rm", "other.c", "space name")
        self.assertEqual(self.staging()["changes"], self.oracle())

    def test_actual_root_replacement_invalidates_staging_evidence(self):
        self.git("rm", "notes.md")
        original = Root.metadata
        changed = False

        def substitute(root, parts, limit):
            nonlocal changed
            data = original(root, parts, limit)
            if parts[:2] == (".git", "objects") and not changed:
                changed = True
                self.project.rename(self.base / "old-project")
                self.project.mkdir()
            return data

        with patch.object(Root, "metadata", substitute):
            self.assertIn("root_replaced_during_check", self.staging()["reason_codes"])

    def test_recovery_only_plan_keeps_staging_limitation_visible(self):
        self.plan["projects"] = []
        result = assess(self.plan, verify=True)
        self.assertEqual(result["items"][0]["status"], "verified_content_match")
        self.assertIn("does not preserve staged-only work", render_text(result))


if __name__ == "__main__":
    unittest.main()
