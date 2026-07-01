#!/usr/bin/env python3
"""Tests for texmerge.py"""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import python.texmerge.texmerge as texmerge


class FixtureMixin:
    """Mixin that provides a temporary directory and file-writing helpers.

    Designed to be used alongside :class:`unittest.TestCase`, which supplies
    ``setUp``, ``addCleanup``, and assertion methods.
    """

    addCleanup: Any  # from unittest.TestCase

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _path(self, relpath: str) -> Path:
        return Path(self.tmp.name, relpath)

    def _write(self, relpath: str, content: str) -> Path:
        p = self._path(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        return p

    def _merge(self, main: str = "main.tex") -> str:
        m = texmerge.TexMerger()
        return m.merge(self._path(main))


# ---------------------------------------------------------------------------
# Basic inlining
# ---------------------------------------------------------------------------


class TestBasicInlining(FixtureMixin, unittest.TestCase):
    def test_input_with_ext(self) -> None:
        self._write("main.tex", r"\input{sections/intro.tex}")
        self._write("sections/intro.tex", "Introduction text.\n")
        out = self._merge()
        self.assertIn("Introduction text.", out)

    def test_input_without_ext(self) -> None:
        self._write("main.tex", r"\input{sections/intro}")
        self._write("sections/intro.tex", "Introduction text.\n")
        out = self._merge()
        self.assertIn("Introduction text.", out)

    def test_input_command_leaves_placeholder(self) -> None:
        """The \\input line itself should be replaced by the expanded content."""
        self._write("main.tex", r"\input{sections/intro.tex}")
        self._write("sections/intro.tex", "Hello\n")
        out = self._merge()
        self.assertNotIn(r"\input", out)

    def test_include_command_expanded(self) -> None:
        self._write("main.tex", r"\include{chapters/ch1}")
        self._write("chapters/ch1.tex", "Chapter one.\n")
        out = self._merge()
        self.assertIn("Chapter one.", out)
        self.assertNotIn(r"\include", out)

    def test_subfile_expanded(self) -> None:
        self._write("main.tex", r"\subfile{appendix}")
        self._write("appendix.tex", "Appendix content.\n")
        out = self._merge()
        self.assertIn("Appendix content.", out)
        self.assertNotIn(r"\subfile", out)

    def test_import_expanded(self) -> None:
        self._write("main.tex", r"\import{figures/}{diagram}")
        self._write("figures/diagram.tex", "TikZ diagram.\n")
        out = self._merge()
        self.assertIn("TikZ diagram.", out)
        self.assertNotIn(r"\import", out)

    def test_file_not_found_raises(self) -> None:
        self._write("main.tex", r"\input{missing.tex}")
        with self.assertRaises(FileNotFoundError):
            self._merge()

    def test_path_resolution_relative_to_containing_file(self) -> None:
        """Included paths resolve relative to the file containing the command."""
        self._write("main.tex", r"\input{chapters/ch1.tex}")
        self._write("chapters/ch1.tex", r"\input{section-a.tex}")
        self._write("chapters/section-a.tex", "Section A.\n")
        out = self._merge()
        self.assertIn("Section A.", out)

    def test_mid_line_input(self) -> None:
        self._write("main.tex", r"Prefix \input{inline} suffix")
        self._write("inline.tex", "inlined content")
        out = self._merge()
        self.assertIn("Prefix inlined content suffix", out)


# ---------------------------------------------------------------------------
# Recursive inlining
# ---------------------------------------------------------------------------


class TestRecursiveInlining(FixtureMixin, unittest.TestCase):
    def test_three_levels(self) -> None:
        self._write("main.tex", r"\input{a.tex}")
        self._write("a.tex", r"\input{b.tex}")
        self._write("b.tex", r"\input{c.tex}")
        self._write("c.tex", "Deep content.\n")
        out = self._merge()
        self.assertIn("Deep content.", out)
        # Only the deepest content should appear; all \\input are expanded
        self.assertNotIn(r"\input", out)

    def test_circular_detected(self) -> None:
        self._write("main.tex", r"\input{a.tex}")
        self._write("a.tex", r"\input{main.tex}")
        with self.assertRaises(texmerge.CircularIncludeError) as ctx:
            self._merge()
        self.assertIn("main.tex", str(ctx.exception))
        self.assertIn("a.tex", str(ctx.exception))

    def test_self_include_detected(self) -> None:
        self._write("main.tex", r"\input{main}")
        with self.assertRaises(texmerge.CircularIncludeError):
            self._merge()


# ---------------------------------------------------------------------------
# Comment handling
# ---------------------------------------------------------------------------


class TestCommentHandling(FixtureMixin, unittest.TestCase):
    def test_commented_out_input_ignored(self) -> None:
        self._write("main.tex", r"% \input{ghost.tex}")
        self._write("ghost.tex", "Should not appear.\n")
        out = self._merge()
        self.assertNotIn("Should not appear", out)

    def test_input_after_comment_mid_line_ignored(self) -> None:
        self._write("main.tex", r"visible % \input{ghost.tex}")
        self._write("ghost.tex", "Should not appear.\n")
        out = self._merge()
        self.assertNotIn("Should not appear", out)
        self.assertIn("visible", out)

    def test_input_before_comment_mid_line_expanded(self) -> None:
        self._write("main.tex", r"\input{real.tex} % trailing comment")
        self._write("real.tex", "expanded content")
        out = self._merge()
        self.assertIn("expanded content", out)

    def test_escaped_percent_not_comment(self) -> None:
        """\\% is an escaped percent sign, not a comment starter."""
        self._write("main.tex", r"100\% done \input{real.tex}")
        self._write("real.tex", "content")
        out = self._merge()
        self.assertIn("content", out)

    def test_double_backslash_then_comment(self) -> None:
        r"""\\% is a line break (\\), then % starts a comment."""
        self._write("main.tex", r"text \\% \input{ghost.tex}")
        self._write("ghost.tex", "Should not appear.\n")
        out = self._merge()
        self.assertNotIn("Should not appear", out)


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------


class TestCommentStripping(FixtureMixin, unittest.TestCase):
    def _merge_strip(self, main: str = "main.tex") -> str:
        m = texmerge.TexMerger(strip_comments=True)
        return m.merge(self._path(main))

    def test_full_line_comment_removed(self) -> None:
        self._write("main.tex", "Hello\n% This is a comment\nWorld\n")
        out = self._merge_strip()
        self.assertNotIn("comment", out)
        self.assertIn("Hello", out)
        self.assertIn("World", out)

    def test_trailing_comment_removed(self) -> None:
        self._write("main.tex", r"Hello % this is a comment")
        out = self._merge_strip()
        self.assertIn("Hello", out)
        self.assertNotIn("comment", out)

    def test_escaped_percent_preserved(self) -> None:
        self._write("main.tex", r"100\% complete")
        out = self._merge_strip()
        self.assertIn(r"100\%", out)

    def test_comments_stripped_recursively(self) -> None:
        self._write("main.tex", r"\input{sub.tex}")
        self._write("sub.tex", "Content % secret note\n")
        out = self._merge_strip()
        self.assertIn("Content", out)
        self.assertNotIn("secret", out)

    def test_verbatim_content_untouched_by_strip(self) -> None:
        self._write(
            "main.tex",
            "\\begin{verbatim}\n% not a comment\n\\end{verbatim}\n",
        )
        out = self._merge_strip()
        self.assertIn("% not a comment", out)


# ---------------------------------------------------------------------------
# Verbatim protection
# ---------------------------------------------------------------------------


class TestVerbatimProtection(FixtureMixin, unittest.TestCase):
    def test_input_inside_verbatim_not_expanded(self) -> None:
        self._write(
            "main.tex",
            "\\begin{verbatim}\n"
            r"\input{not-real.tex}" + "\n"
            "\\end{verbatim}\n",
        )
        self._write("not-real.tex", "Should not be included.\n")
        out = self._merge()
        self.assertNotIn("Should not be included", out)
        self.assertIn(r"\input{not-real.tex}", out)

    def test_comment_inside_verbatim_untouched(self) -> None:
        self._write(
            "main.tex",
            "\\begin{verbatim}\n% This % is % text\n\\end{verbatim}\n",
        )
        out = self._merge()
        self.assertIn("% This % is % text", out)

    def test_lstlisting_protected(self) -> None:
        self._write(
            "main.tex",
            "\\begin{lstlisting}\n"
            r"\input{code.tex}" + "\n"
            "\\end{lstlisting}\n",
        )
        self._write("code.tex", "Should not be included.\n")
        out = self._merge()
        self.assertNotIn("Should not be included", out)

    def test_comment_env_protected(self) -> None:
        self._write(
            "main.tex",
            "\\begin{comment}\n"
            r"\input{hidden.tex}" + "\n"
            "\\end{comment}\n",
        )
        self._write("hidden.tex", "Should not be included.\n")
        out = self._merge()
        self.assertNotIn("Should not be included", out)


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


class TestMarkers(FixtureMixin, unittest.TestCase):
    def test_markers_appear_by_default(self) -> None:
        self._write("main.tex", r"\input{sections/intro.tex}")
        self._write("sections/intro.tex", "Content.\n")
        out = self._merge()
        self.assertIn("Begin sections/intro.tex", out)
        self.assertIn("End sections/intro.tex", out)

    def test_no_markers_suppresses_them(self) -> None:
        self._write("main.tex", r"\input{sections/intro.tex}")
        self._write("sections/intro.tex", "Content.\n")
        m = texmerge.TexMerger(no_markers=True)
        out = m.merge(self._path("main.tex"))
        self.assertNotIn("Begin", out)
        self.assertNotIn("End", out)

    def test_marker_posix_separators(self) -> None:
        self._write("main.tex", r"\input{sections/intro.tex}")
        self._write("sections/intro.tex", "Content.\n")
        out = self._merge()
        self.assertIn("sections/intro.tex", out)
        self.assertNotIn("sections\\intro.tex", out)


# ---------------------------------------------------------------------------
# \includeonly
# ---------------------------------------------------------------------------


class TestIncludeonly(FixtureMixin, unittest.TestCase):
    def test_includeonly_commented_out(self) -> None:
        self._write("main.tex", r"\includeonly{ch1,ch2}")
        out = self._merge()
        self.assertIn(r"% \includeonly{ch1,ch2}", out)

    def test_includeonly_dropped_when_stripping(self) -> None:
        self._write("main.tex", r"\includeonly{ch1,ch2}")
        m = texmerge.TexMerger(strip_comments=True)
        out = m.merge(self._path("main.tex"))
        self.assertNotIn("includeonly", out)


# ---------------------------------------------------------------------------
# Command preservation
# ---------------------------------------------------------------------------


class TestCommandPreservation(FixtureMixin, unittest.TestCase):
    def test_bibliography_preserved(self) -> None:
        self._write("main.tex", r"\bibliography{refs}")
        out = self._merge()
        self.assertIn(r"\bibliography{refs}", out)

    def test_bibliographystyle_preserved(self) -> None:
        self._write("main.tex", r"\bibliographystyle{plain}")
        out = self._merge()
        self.assertIn(r"\bibliographystyle{plain}", out)

    def test_usepackage_preserved(self) -> None:
        self._write("main.tex", r"\usepackage{amsmath}")
        out = self._merge()
        self.assertIn(r"\usepackage{amsmath}", out)

    def test_documentclass_preserved(self) -> None:
        self._write("main.tex", r"\documentclass{article}")
        out = self._merge()
        self.assertIn(r"\documentclass{article}", out)

    def test_includegraphics_preserved(self) -> None:
        self._write("main.tex", r"\includegraphics{fig.pdf}")
        out = self._merge()
        self.assertIn(r"\includegraphics{fig.pdf}", out)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases(FixtureMixin, unittest.TestCase):
    def test_empty_included_file(self) -> None:
        self._write("main.tex", r"Before\input{empty.tex}After")
        self._write("empty.tex", "")
        out = self._merge()
        self.assertIn("Before", out)
        self.assertIn("After", out)

    def test_only_comments_file(self) -> None:
        self._write("main.tex", r"\input{comments.tex}")
        self._write("comments.tex", "% just a comment\n")
        out = self._merge()
        self.assertIn("just a comment", out)

    def test_only_comments_stripped(self) -> None:
        self._write("main.tex", r"\input{comments.tex}")
        self._write("comments.tex", "% just a secret\n")
        m = texmerge.TexMerger(strip_comments=True)
        out = m.merge(self._path("main.tex"))
        self.assertNotIn("secret", out)

    def test_blank_lines_preserved(self) -> None:
        self._write("main.tex", "Line 1\n\nLine 3\n")
        out = self._merge()
        self.assertIn("\n\n", out)

    def test_consecutive_blank_lines_collapsed(self) -> None:
        self._write("main.tex", "A\n\n\n\nB\n")
        out = self._merge()
        self.assertIn("A\n\nB", out)
        self.assertNotIn("\n\n\n", out)

    def test_consecutive_blank_lines_collapsed_when_stripping(self) -> None:
        self._write("main.tex", "A\n\n\n% comment\n\n\nB\n")
        m = texmerge.TexMerger(strip_comments=True)
        out = m.merge(self._path("main.tex"))
        self.assertIn("A\n\nB", out)
        self.assertNotIn("\n\n\n", out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI(FixtureMixin, unittest.TestCase):
    def _run_cli(self, *args: str) -> tuple[int, str, str]:
        """Run main() with given CLI args; return (exit_code, stdout, stderr)."""
        saved_argv = sys.argv
        saved_stdout = sys.stdout
        saved_stderr = sys.stderr
        try:
            sys.argv = ["texmerge"] + list(args)
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            try:
                texmerge.main()
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
            return code, sys.stdout.getvalue(), sys.stderr.getvalue()
        finally:
            sys.argv = saved_argv
            sys.stdout = saved_stdout
            sys.stderr = saved_stderr

    def _write_main(self, content: str = "Hello\n") -> None:
        self._write("main.tex", content)

    def _abs(self, relpath: str) -> str:
        return str(self._path(relpath))

    def test_default_main_and_output(self) -> None:
        self._write_main()
        code, out, err = self._run_cli("--main", self._abs("main.tex"),
                                       "--output", self._abs("main-merged.tex"))
        self.assertEqual(code, 0)
        result = self._path("main-merged.tex").read_text(encoding="utf-8")
        self.assertIn("Hello", result)

    def test_custom_main_and_output(self) -> None:
        self._write("paper.tex", "Content\n")
        code, out, err = self._run_cli(
            "--main", self._abs("paper.tex"),
            "--output", self._abs("out.tex"),
        )
        self.assertEqual(code, 0)
        result = self._path("out.tex").read_text(encoding="utf-8")
        self.assertIn("Content", result)

    def test_strip_comments_flag(self) -> None:
        self._write("main.tex", "Visible % hidden")
        code, out, err = self._run_cli(
            "--strip-comments",
            "--main", self._abs("main.tex"),
            "--output", self._abs("main-merged.tex"),
        )
        self.assertEqual(code, 0)
        result = self._path("main-merged.tex").read_text(encoding="utf-8")
        self.assertIn("Visible", result)
        self.assertNotIn("hidden", result)

    def test_no_markers_flag(self) -> None:
        self._write("main.tex", r"\input{sub.tex}")
        self._write("sub.tex", "Content.\n")
        code, out, err = self._run_cli(
            "--no-markers",
            "--main", self._abs("main.tex"),
            "--output", self._abs("main-merged.tex"),
        )
        self.assertEqual(code, 0)
        result = self._path("main-merged.tex").read_text(encoding="utf-8")
        self.assertIn("Content.", result)
        self.assertNotIn("Begin", result)

    def test_missing_main_file(self) -> None:
        code, out, err = self._run_cli("--main", self._abs("nonexistent.tex"))
        self.assertEqual(code, 1)
        self.assertIn("File not found", err)

    def test_circular_include_exit_code(self) -> None:
        self._write("main.tex", r"\input{sub.tex}")
        self._write("sub.tex", r"\input{main.tex}")
        code, out, err = self._run_cli(
            "--main", self._abs("main.tex"),
            "--output", self._abs("main-merged.tex"),
        )
        self.assertEqual(code, 1)
        self.assertIn("Circular", err)

    def test_refuses_overwrite_existing_output(self) -> None:
        self._write("main.tex", "Hello\n")
        self._write("main-merged.tex", "existing")
        code, out, err = self._run_cli(
            "--main", self._abs("main.tex"),
            "--output", self._abs("main-merged.tex"),
        )
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        # Existing file should be untouched
        result = self._path("main-merged.tex").read_text(encoding="utf-8")
        self.assertEqual(result, "existing")

    def test_force_overwrites_existing_output(self) -> None:
        self._write("main.tex", "Hello\n")
        self._write("main-merged.tex", "existing")
        code, out, err = self._run_cli(
            "--force",
            "--main", self._abs("main.tex"),
            "--output", self._abs("main-merged.tex"),
        )
        self.assertEqual(code, 0)
        result = self._path("main-merged.tex").read_text(encoding="utf-8")
        self.assertIn("Hello", result)


if __name__ == "__main__":
    unittest.main()
