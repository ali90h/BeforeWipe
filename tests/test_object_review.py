"""Independent adversarial review. Only new synthetic repositories are used."""
import hashlib
import json
import os
import zlib
import unittest
from unittest.mock import patch

import test_staging as fixtures
from beforewipe.fs import Root, ScopeError
from beforewipe.staging import LooseObjects


class ObjectReviewCase(unittest.TestCase):
    setUp = fixtures.StagingCase.setUp
    tearDown = fixtures.StagingCase.tearDown
    git = fixtures.StagingCase.git
    staging = fixtures.StagingCase.staging
    result = fixtures.StagingCase.result
    oracle = fixtures.StagingCase.oracle
    write_object = fixtures.StagingCase.write_object
    object_path = fixtures.StagingCase.object_path

    def symbolic_shadow(self):
        self.git('pack-refs', '--all', '--prune')
        self.git('checkout', '-b', 'other')
        (self.project / 'notes.md').write_text('new synthetic committed version\n')
        self.git('add', 'notes.md')
        self.git('commit', '-m', 'other version')
        self.git('symbolic-ref', 'refs/heads/main', 'refs/heads/other')
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main')

    def test_symbolic_loose_ref_must_not_use_shadowed_packed_tip(self):
        self.symbolic_shadow()
        self.assertEqual(self.oracle(), dict(added=0, modified=0, deleted=0))
        result = self.staging()
        self.assertNotEqual(result['status'], 'confirmed_risk')
        self.assertNotEqual(result['coverage'], 'complete')

    def test_symbolic_loose_ref_must_not_hide_real_staging(self):
        self.symbolic_shadow()
        # Restore the old packed tip's tree into the index: it differs from actual HEAD.
        old = (self.project / '.git/packed-refs').read_text().splitlines()[-1].split()[0]
        self.git('read-tree', old)
        self.assertEqual(self.oracle(), dict(added=0, modified=1, deleted=0))
        self.assertNotEqual(self.staging()['status'], 'no_difference_observed')

    def test_malformed_commit_order_cannot_confirm_baseline(self):
        tree = self.git('rev-parse', 'HEAD^{tree}').strip()
        body = (b'tree ' + tree + b'\ncommitter Fixture <x@example.invalid> 1 +0000\n'
                b'author Fixture <x@example.invalid> 1 +0000\n\nsynthetic\n')
        oid = self.write_object(b'commit', body)
        (self.project / '.git/refs/heads/main').write_text(oid + '\n')
        # fsck, unlike the reviewed parser, checks the commit's mandatory ordering.
        import subprocess
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.git('fsck', '--strict', '--no-reflogs')
        self.assertIn(b'missingAuthor', failure.exception.stderr)
        self.assertEqual(self.staging()['status'], 'unknown')

    def test_failed_inflation_is_charged_to_total_budget(self):
        # Correct stream except Adler checksum: inflate performs work then raises.
        payload = bytearray(zlib.compress(b'x' * 900))
        payload[-1] ^= 1
        oid = bytes.fromhex('12' * 20)
        target = self.project / '.git/objects' / oid.hex()[:2] / oid.hex()[2:]
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(payload)
        with Root(self.project) as root, patch('beforewipe.staging.MAX_OBJECT_BYTES', 1024), \
                patch('beforewipe.staging.MAX_TOTAL_BYTES', 2048):
            reader = LooseObjects(root)
            for _ in range(3):
                with self.assertRaises(ScopeError):
                    reader.read(oid, b'tree')
            self.assertGreaterEqual(reader.total, 2048)

    def test_failed_metadata_reads_consume_compressed_budget(self):
        oid = bytes.fromhex('34' * 20)
        target = self.project / '.git/objects' / oid.hex()[:2] / oid.hex()[2:]
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b'x' * 900)
        inode = target.stat().st_ino
        original = os.read
        consumed = 0
        moved = target.with_name('temporarily-moved')
        mutation = 'timestamp'

        def racing_read(fd, size):
            nonlocal consumed
            data = original(fd, size)
            if os.fstat(fd).st_ino == inode and data:
                consumed += len(data)
                if mutation == 'rename':
                    target.rename(moved)
                else:
                    current = target.stat()
                    os.utime(target, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000000))
            return data

        with Root(self.project) as root, patch('beforewipe.staging.MAX_OBJECT_BYTES', 1024), \
                patch('beforewipe.staging.MAX_TOTAL_BYTES', 2048), patch('os.read', side_effect=racing_read):
            for mutation in ('timestamp', 'rename'):
                with self.subTest(mutation=mutation):
                    consumed = 0
                    reader = LooseObjects(root)
                    for _ in range(5):
                        with self.assertRaises(ScopeError):
                            reader.read(oid, b'tree')
                        if moved.exists():
                            moved.rename(target)
                    self.assertLessEqual(consumed, 2048)

    def test_valid_extended_commit_headers_still_compare(self):
        tree = self.git('rev-parse', 'HEAD^{tree}').strip()
        body = (b'tree ' + tree + b'\nauthor Fixture <x@example.invalid> 1 +0000\n'
                b'committer Fixture <x@example.invalid> 1 +0000\n'
                b'encoding UTF-8\ngpgsig synthetic signature\n continuation\n\nsynthetic message\n')
        oid = self.write_object(b'commit', body)
        (self.project / '.git/refs/heads/main').write_text(oid + '\n')
        self.assertEqual(self.oracle(), dict(added=0, modified=0, deleted=0))
        self.assertEqual(self.staging()['status'], 'no_difference_observed')

    def test_plan_cannot_grant_object_authorization(self):
        from beforewipe.core import load_plan
        plan = dict(self.plan, allow_git_object_read=True)
        target = self.base / 'plan.json'
        target.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ScopeError, 'invalid_plan_structure'):
            load_plan(target)

    def test_remote_symbolic_alias_does_not_block_comparison(self):
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        self.assertEqual(self.staging()['status'], 'no_difference_observed')

    def test_packed_tree_with_loose_head_remains_incomplete(self):
        head = self.object_path('HEAD')
        commit = head.read_bytes()
        self.git('gc', '--prune=now')
        head.parent.mkdir(exist_ok=True)
        head.write_bytes(commit)
        self.git('rm', 'notes.md')
        self.assertEqual(self.oracle(), dict(added=0, modified=0, deleted=1))
        result = self.staging()
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['coverage'], 'incomplete')

    def test_differential_multifile_changes_against_git(self):
        import random
        rng = random.Random(8675309)
        for n in range(30):
            name = 'generated/f%02d.txt' % n
            target = self.project / name
            target.parent.mkdir(exist_ok=True)
            target.write_text('synthetic baseline %d\n' % n)
        self.git('add', '.')
        self.git('commit', '-m', 'synthetic differential baseline')
        for round_number in range(8):
            self.git('reset', '--hard', 'HEAD')
            for n in rng.sample(range(30), 12):
                name = 'generated/f%02d.txt' % n
                action = rng.randrange(4)
                if action == 0:
                    self.git('rm', name)
                elif action == 1:
                    self.git('mv', name, name + '-renamed')
                elif action == 2:
                    (self.project / name).write_text('synthetic changed %d\n' % round_number)
                    self.git('add', name)
                else:
                    self.git('update-index', '--chmod=+x', name)
            self.assertEqual(self.staging()['changes'], self.oracle())
            self.assertEqual(self.staging()['coverage'], 'complete')
