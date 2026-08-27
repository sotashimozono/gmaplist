"""The declared version and the reported version must agree.

`pyproject.toml` is what the version-check gate reads, and `__version__` is
what `gmaplist --version` prints. Nothing enforced that they matched, and they
silently drifted three releases apart: the gate went green on every bump while
the CLI kept reporting the version it shipped with.
"""

import sys
import unittest
from pathlib import Path

import gmaplist
from gmaplist.cli import build_parser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from version_bump_check import read_version, sort_key

ROOT = Path(__file__).resolve().parent.parent


class TestVersionConsistency(unittest.TestCase):
    def test_dunder_version_matches_pyproject(self):
        self.assertEqual(gmaplist.__version__, read_version(ROOT / "pyproject.toml"))

    def test_version_is_orderable(self):
        # A version the gate cannot order would make every later bump ambiguous.
        self.assertTrue(sort_key(gmaplist.__version__))

    def test_cli_reports_the_same_version(self):
        action = next(
            a for a in build_parser()._actions if "--version" in a.option_strings
        )
        self.assertIn(gmaplist.__version__, action.version)
