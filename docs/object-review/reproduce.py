"""Run synthetic audit regressions against saved before or current implementation.

Usage: python3 -B docs/object-review/reproduce.py [--before]
A nonzero result with --before is expected: it reproduces the fixed defects.
"""
import pathlib
import shutil
import sys
import tempfile
import unittest

workspace = pathlib.Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='beforewipe-review-code-') as temporary:
    package = pathlib.Path(temporary) / 'beforewipe'
    shutil.copytree(workspace / 'beforewipe', package, ignore=shutil.ignore_patterns('__pycache__'))
    if '--before' in sys.argv:
        for original in (workspace / 'docs/object-review/before').glob('*.py'):
            shutil.copyfile(original, package / original.name)
    sys.path.insert(0, str(workspace / 'tests'))
    sys.path.insert(0, temporary)
    suite = unittest.defaultTestLoader.loadTestsFromName('test_object_review')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    success = result.wasSuccessful()
sys.exit(0 if success else 1)
