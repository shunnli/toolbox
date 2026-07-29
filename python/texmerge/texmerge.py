#!/usr/bin/env python3
"""Merge a multi-file LaTeX project into a single self-contained .tex file.

Recursively expands \\input and \\include commands.
"""

import argparse
import re
import sys
import warnings
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERBATIM_ENVS = {
    "verbatim",
    "verbatim*",
    "lstlisting",
    "Verbatim",
    "Verbatim*",
    "comment",
}

BEGIN_ENV = re.compile(r"\\begin\{(\w+\*?)\}")
END_ENV = re.compile(r"\\end\{(\w+\*?)\}")

# \input{...}, \include{...}; DOTALL allows the argument to span lines.
INLINE_ONE_ARG = re.compile(
    r"\\(input|include)\b\s*\{([^}]+)\}",
    re.DOTALL,
)
INLINE_COMMAND_START = re.compile(r"\\(?:input|include)\b")
UNSUPPORTED_CMD = re.compile(r"\\(subfile|import)\b")

# \includeonly{...} — should be commented out or dropped
INCLUDEONLY_CMD = re.compile(r"\\includeonly\b")

# ---------------------------------------------------------------------------
# Comment detection
# ---------------------------------------------------------------------------


def _find_comment_start(line: str) -> int:
    """Return the index of the first unescaped '%' in *line*, or -1 if none.

    A '%' is escaped when preceded by an odd number of consecutive backslashes.
    """
    bs = 0
    for i, ch in enumerate(line):
        if ch == "\\":
            bs += 1
        elif ch == "%":
            if bs % 2 == 0:
                return i
            bs = 0
        else:
            bs = 0
    return -1


# ---------------------------------------------------------------------------
# Verbatim tracking
# ---------------------------------------------------------------------------


def _update_verbatim(line: str, stack: list[str]) -> None:
    """Update *stack* based on ``\\begin{env}`` / ``\\end{env}`` in *line*."""
    m_end = END_ENV.search(line)
    if m_end and stack and m_end.group(1) == stack[-1]:
        stack.pop()
        return
    m_begin = BEGIN_ENV.search(line)
    if m_begin and m_begin.group(1) in VERBATIM_ENVS:
        stack.append(m_begin.group(1))


# ---------------------------------------------------------------------------
# TexMerger
# ---------------------------------------------------------------------------


class CircularIncludeError(Exception):
    """Raised when an included file references an ancestor file."""


class TexMergeWarning(UserWarning):
    """Base class for non-fatal texmerge warnings."""


class UnsupportedCommandWarning(TexMergeWarning):
    """Warning emitted when an unsupported inclusion command is preserved."""


class PotentialMergeIssueWarning(TexMergeWarning):
    """Warning emitted when an expansion may not preserve LaTeX semantics."""


class TexMerger:
    def __init__(self, strip_comments: bool = False, no_markers: bool = False):
        self.strip_comments = strip_comments
        self.no_markers = no_markers
        self._active_stack: list[Path] = []
        self._main_dir: Path | None = None

    # -- public API ----------------------------------------------------------

    def merge(self, main_path: Path) -> str:
        """Return the fully merged content of *main_path*."""
        self._main_dir = main_path.resolve().parent
        return self._merge_file(main_path.resolve())

    # -- file processing -----------------------------------------------------

    def _merge_file(self, file_path: Path) -> str:
        abspath = file_path
        if not abspath.is_file():
            raise FileNotFoundError(f"File not found: {abspath}")

        # --- cycle detection ---
        if abspath in self._active_stack:
            chain = [p.name for p in self._active_stack] + [abspath.name]
            raise CircularIncludeError(" -> ".join(chain))

        self._active_stack.append(abspath)

        try:
            return self._merge_active_file(abspath)
        finally:
            popped = self._active_stack.pop()
            assert popped == abspath

    def _merge_active_file(self, abspath: Path) -> str:
        """Merge a file that has already been added to the active stack."""
        content = abspath.read_text(encoding="utf-8").replace("\r\n", "\n")
        lines = content.split("\n")
        output: list[str] = []
        prev_blank = False

        for active, comment, is_verbatim in self._logical_lines(lines):
            if is_verbatim:
                output.append(active)
                prev_blank = False
                continue

            self._warn_unsupported_commands(active, abspath)

            # --- \includeonly ---
            if INCLUDEONLY_CMD.search(active):
                warnings.warn(
                    f"\\includeonly in {abspath} is modified during merging; "
                    "verify that the merged document includes the intended files.",
                    PotentialMergeIssueWarning,
                    stacklevel=2,
                )
                if self.strip_comments:
                    continue
                output.append(f"% {active}{comment}".rstrip())
                prev_blank = False
                continue

            # --- try expand inlinable commands ---
            if "\n" in active and comment:
                warnings.warn(
                    f"A multiline inclusion command in {abspath} contains "
                    "comments; comment placement may change after expansion.",
                    PotentialMergeIssueWarning,
                    stacklevel=2,
                )
            expanded = self._try_expand(active, abspath.parent)
            if expanded is None:
                if INLINE_COMMAND_START.search(active):
                    warnings.warn(
                        f"An \\input or \\include command in {abspath} could "
                        "not be parsed and was left unchanged.",
                        PotentialMergeIssueWarning,
                        stacklevel=2,
                    )
                # No inlinable command — emit as-is
                if self.strip_comments:
                    stripped = active.rstrip()
                    if stripped:
                        output.append(stripped)
                        prev_blank = False
                    elif comment:
                        # Full-line comment stripped to nothing — drop it
                        pass
                    elif not prev_blank:
                        # Genuinely blank line — keep one
                        output.append("")
                        prev_blank = True
                else:
                    line_out = f"{active}{comment}".rstrip()
                    if line_out:
                        output.append(line_out)
                        prev_blank = False
                    elif not prev_blank:
                        output.append("")
                        prev_blank = True
            else:
                # Command was expanded — append comment to last line if keeping
                if comment and not self.strip_comments:
                    expanded[-1] = f"{expanded[-1]}{comment}"
                output.extend(expanded)
                prev_blank = False

        return "\n".join(output).rstrip() + "\n"

    # -- line splitting ------------------------------------------------------

    @staticmethod
    def _warn_unsupported_commands(active: str, file_path: Path) -> None:
        """Warn about unsupported inclusion commands in active LaTeX."""
        for match in UNSUPPORTED_CMD.finditer(active):
            command = match.group(1)
            warnings.warn(
                f"Unsupported LaTeX command \\{command} in {file_path}; "
                "left unchanged.",
                UnsupportedCommandWarning,
                stacklevel=2,
            )

    def _logical_lines(self, lines: list[str]) -> list[tuple[str, str, bool]]:
        """Return logical lines, joining multiline include commands.

        Each tuple is ``(active, comment, is_verbatim)``. Comments encountered
        inside a multiline command are retained and attached to its expansion.
        """
        result: list[tuple[str, str, bool]] = []
        verbatim_stack: list[str] = []
        pending_active: list[str] = []
        pending_comments: list[str] = []

        for line in lines:
            if pending_active:
                active, comment = self._split_line(line)
                pending_active.append(active)
                if comment:
                    pending_comments.append(comment)
                combined = "\n".join(pending_active)
                if INLINE_ONE_ARG.search(combined):
                    result.append((combined, " ".join(pending_comments), False))
                    pending_active.clear()
                    pending_comments.clear()
                continue

            _update_verbatim(line, verbatim_stack)
            if verbatim_stack:
                result.append((line, "", True))
                continue

            active, comment = self._split_line(line)
            if self._needs_continuation(active):
                pending_active.append(active)
                if comment:
                    pending_comments.append(comment)
                continue
            result.append((active, comment, False))

        if pending_active:
            result.append(
                (
                    "\n".join(pending_active),
                    " ".join(pending_comments),
                    False,
                )
            )
        return result

    @staticmethod
    def _needs_continuation(active: str) -> bool:
        """Return whether *active* starts an unfinished include command."""
        match = INLINE_COMMAND_START.search(active)
        if match is None or INLINE_ONE_ARG.search(active):
            return False
        remainder = active[match.end() :]
        stripped = remainder.lstrip()
        return not stripped or (stripped.startswith("{") and "}" not in stripped)

    def _split_line(self, line: str) -> tuple[str, str]:
        """Split *line* into (active, comment) at the first unescaped '%'.

        *comment* includes the '%' that starts it.
        """
        idx = _find_comment_start(line)
        if idx < 0:
            return line, ""
        return line[:idx], line[idx:]

    # -- command expansion ---------------------------------------------------

    def _try_expand(self, active: str, parent_dir: Path) -> list[str] | None:
        """If *active* contains an inlinable command, return the expanded lines.

        Returns ``None`` if no inlinable command is found.
        """
        assert self._main_dir is not None  # set by merge()
        # \input{...} / \include{...}
        # Standard LaTeX resolves these relative to the main file's directory.
        # Fall back to parent_dir when the file isn't found at the main level
        # (supports projects that use path-relative-to-current-file convention).
        m = INLINE_ONE_ARG.search(active)
        if m:
            if INLINE_ONE_ARG.search(active, m.end()):
                warnings.warn(
                    "Multiple \\input or \\include commands occur on one "
                    "logical line; only the first command will be expanded.",
                    PotentialMergeIssueWarning,
                    stacklevel=2,
                )
            raw = re.sub(r"\s*\n\s*", "", m.group(2)).strip()
            target = self._resolve_path(raw, self._main_dir, parent_dir)
            content = self._merge_file(target)
            return self._format_expansion(active, content, m.start(), m.end(), target)

        return None

    def _format_expansion(
        self,
        active: str,
        content: str,
        start: int,
        end: int,
        target: Path,
    ) -> list[str]:
        """Wrap expanded *content* with optional markers."""
        before = active[:start]
        after = active[end:]
        is_solo = not before.strip() and not after.strip()

        if is_solo:
            lines = content.rstrip("\n").split("\n")
            if self.no_markers:
                return lines
            rel = self._rel_path(target)
            marker_begin = self._marker("Begin", rel)
            marker_end = self._marker("End", rel)
            return [marker_begin, ""] + lines + ["", marker_end]
        else:
            # Mid-line command — inline without markers
            warnings.warn(
                f"Mid-line inclusion of {target} may change whitespace or "
                "line-sensitive LaTeX semantics; verify the merged output.",
                PotentialMergeIssueWarning,
                stacklevel=2,
            )
            inner = content.rstrip("\n").split("\n")
            if len(inner) == 1:
                return [f"{before}{inner[0]}{after}"]
            result = [f"{before}{inner[0]}"]
            result.extend(inner[1:-1])
            result.append(f"{inner[-1]}{after}")
            return result

    # -- path helpers --------------------------------------------------------

    def _resolve_path(
        self, raw_path: str, primary_dir: Path, fallback_dir: Path
    ) -> Path:
        """Resolve an included path.

        Tries *primary_dir* first, then *fallback_dir*.  Tries the raw path
        first, then with ``.tex`` appended if the raw path has no extension.
        """

        def find_in(base: Path) -> Path | None:
            candidate = (base / raw_path).resolve()
            if candidate.is_file():
                return candidate
            if not Path(raw_path).suffix:
                candidate_tex = (base / f"{raw_path}.tex").resolve()
                if candidate_tex.is_file():
                    return candidate_tex
            return None

        primary_target = find_in(primary_dir)
        fallback_target = find_in(fallback_dir)

        if primary_target is not None:
            if fallback_target is not None and fallback_target != primary_target:
                warnings.warn(
                    f"Included path {raw_path!r} is ambiguous: both "
                    f"{primary_target} and {fallback_target} exist; using "
                    f"{primary_target}.",
                    PotentialMergeIssueWarning,
                    stacklevel=2,
                )
            return primary_target

        if fallback_target is not None:
            if primary_dir.resolve() != fallback_dir.resolve():
                warnings.warn(
                    f"Included path {raw_path!r} was not found relative to "
                    f"the main file; using {fallback_target} relative to the "
                    "containing file.",
                    PotentialMergeIssueWarning,
                    stacklevel=2,
                )
            return fallback_target

        raise FileNotFoundError(
            f"Included file not found: {raw_path}\n"
            f"  looked in: {primary_dir}\n"
            f"  and:       {fallback_dir}"
        )

    def _rel_path(self, target: Path) -> str:
        """Return *target* as a POSIX path relative to the main file's dir."""
        main_dir = self._main_dir
        assert main_dir is not None  # set by merge()
        try:
            return target.relative_to(main_dir).as_posix()
        except ValueError:
            return target.as_posix()

    # -- marker formatting ---------------------------------------------------

    @staticmethod
    def _marker(label: str, rel_path: str, width: int = 72) -> str:
        """Build a marker comment line like::

        % ===== Begin path/to/file.tex =====
        """
        text = f" {label} {rel_path} "
        left = (width - len(text)) // 2
        right = width - len(text) - left
        return f"%{'=' * left}{text}{'=' * right}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="texmerge",
        description=(
            "Merge a multi-file LaTeX project into a single self-contained .tex file.\n"
            "Recursively expands \\input and \\include commands."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--main",
        default=Path("main.tex"),
        type=Path,
        help="Main LaTeX file.  [default: main.tex]",
    )
    parser.add_argument(
        "--output",
        default=Path("main-merged.tex"),
        type=Path,
        help="Output file.  [default: main-merged.tex]",
    )
    parser.add_argument(
        "--strip-comments",
        action="store_true",
        help="Strip LaTeX comments from the output (useful for arXiv source exposure).",
    )
    parser.add_argument(
        "--no-markers",
        action="store_true",
        help="Suppress begin/end comment markers around inlined files.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        print(f"Error: output file already exists: {args.output}", file=sys.stderr)
        print(
            "  Use -f/--force to overwrite, or delete the file first.", file=sys.stderr
        )
        sys.exit(1)

    merger = TexMerger(
        strip_comments=args.strip_comments,
        no_markers=args.no_markers,
    )
    try:
        output = merger.merge(args.main.resolve())
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except CircularIncludeError as e:
        print(f"Error: Circular include detected: {e}", file=sys.stderr)
        sys.exit(1)

    args.output.write_text(output, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
