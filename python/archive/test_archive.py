import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import archive


class TestArchiveHelpers(unittest.TestCase):
    def test_parse_exts(self):
        self.assertIsNone(archive.parse_exts(None))
        self.assertEqual(archive.parse_exts([".TeX", "bib"]), {"tex", "bib"})

    @patch("archive.sys.platform", "win32")
    def test_resolve_archive_format_auto_windows(self):
        self.assertEqual(archive.resolve_archive_format("auto"), "zip")

    @patch("archive.sys.platform", "linux")
    def test_resolve_archive_format_auto_linux(self):
        self.assertEqual(archive.resolve_archive_format("auto"), "tar.gz")

    def test_build_archive_name_without_timestamp(self):
        self.assertEqual(
            archive.build_archive_name("paper", "zip", no_timestamp=True),
            "paper.zip",
        )

    @patch("archive.datetime")
    def test_build_archive_name_with_timestamp(self, mock_datetime):
        mock_datetime.now.return_value.strftime.return_value = "20260101-010203"
        self.assertEqual(
            archive.build_archive_name("paper", "tar.gz", no_timestamp=False),
            "paper-20260101-010203.tar.gz",
        )


class TestArchiveCollection(unittest.TestCase):
    def test_collect_files_respects_ignore_and_ext_filter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            (root / "keep.tex").write_text("a", encoding="utf-8")
            (root / "keep.bib").write_text("b", encoding="utf-8")
            (root / ".DS_Store").write_text("x", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "ignore.pyc").write_text("x", encoding="utf-8")

            collected = archive.collect_files([root], [], {"tex", "bib"})
            names = [f.relative_to(root).as_posix() for _, f in collected]

            self.assertEqual(names, ["keep.bib", "keep.tex"])

    def test_validate_directories_detects_containment(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td) / "a"
            child = parent / "b"
            parent.mkdir()
            child.mkdir()
            with self.assertRaises(ValueError):
                archive.validate_directories([parent], child)


if __name__ == "__main__":
    unittest.main()
