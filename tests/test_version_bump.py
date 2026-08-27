"""Tests for the release gate helper."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from version_bump_check import (
    VersionError,
    extract_version,
    is_bumped,
    read_version,
    sort_key,
)


class TestOrdering(unittest.TestCase):
    def test_patch_minor_major(self):
        self.assertTrue(is_bumped("0.1.0", "0.1.1"))
        self.assertTrue(is_bumped("0.1.9", "0.2.0"))
        self.assertTrue(is_bumped("0.9.0", "1.0.0"))

    def test_equal_or_backwards_is_not_a_bump(self):
        self.assertFalse(is_bumped("0.2.0", "0.2.0"))
        self.assertFalse(is_bumped("0.2.0", "0.1.9"))
        self.assertFalse(is_bumped("1.0.0", "0.9.9"))

    def test_numeric_not_lexicographic(self):
        # "0.10.0" sorts before "0.9.0" as text, and after it as a version.
        self.assertTrue(is_bumped("0.9.0", "0.10.0"))
        self.assertFalse(is_bumped("0.10.0", "0.9.0"))

    def test_prerelease_sorts_below_its_release(self):
        self.assertTrue(is_bumped("0.2.0-beta.1", "0.2.0"))
        self.assertTrue(is_bumped("0.2.0-beta.1", "0.2.0-beta.2"))
        self.assertFalse(is_bumped("0.2.0", "0.2.0-beta.3"))

    def test_unsupported_shape_is_rejected(self):
        for bad in ("1.0.0+local", "v1.0.0", "1.0.0rc1", ""):
            with self.assertRaises(VersionError):
                sort_key(bad)


class TestExtractVersion(unittest.TestCase):
    def test_ignores_version_keys_in_other_tables(self):
        # A [tool.*] version must not be mistaken for the project version.
        text = "\n".join(
            [
                "[tool.poetry]",
                'version = "9.9.9"',
                "",
                "[project]",
                'name = "x"',
                'version = "1.2.3"',
            ]
        )
        self.assertEqual(extract_version(text), "1.2.3")

    def test_version_before_any_table_is_not_used(self):
        text = "\n".join(['version = "9.9.9"', "[tool.x]", 'name = "y"'])
        with self.assertRaises(VersionError):
            extract_version(text)

    def test_single_quoted_value(self):
        self.assertEqual(extract_version("[project]\nversion = '4.5.6'\n"), "4.5.6")

    def test_leaving_the_project_table_stops_the_scan(self):
        text = "\n".join(["[project]", 'name = "x"', "[tool.y]", 'version = "9.9.9"'])
        with self.assertRaises(VersionError):
            extract_version(text)


class TestReadVersion(unittest.TestCase):
    def _write(self, text):
        path = Path(tempfile.mkdtemp()) / "pyproject.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_project_version(self):
        path = self._write('[project]\nname = "x"\nversion = "1.2.3"\n')
        self.assertEqual(read_version(path), "1.2.3")

    def test_missing_version_is_an_error(self):
        path = self._write('[project]\nname = "x"\n')
        with self.assertRaises(VersionError):
            read_version(path)

    def test_this_repository_declares_a_readable_version(self):
        root = Path(__file__).resolve().parent.parent
        self.assertTrue(sort_key(read_version(root / "pyproject.toml")))


if __name__ == "__main__":
    unittest.main()
