# texmerge — LaTeX project merger

Merge a multi-file LaTeX project into a single self-contained `.tex` file by recursively inlining `\input` and `\include` commands.

## Quick start

```bash
uv run python texmerge.py --main main.tex --output main-merged.tex
```

For arXiv submission (strip comments to clean the exposed source):

```bash
uv run python texmerge.py --main main.tex --output arxiv.tex --strip-comments --no-markers
```

## CLI reference

| Flag               | Default           | Description                                     |
| ------------------ | ----------------- | ----------------------------------------------- |
| `--main PATH`      | `main.tex`        | Main LaTeX file                                 |
| `--output PATH`    | `main-merged.tex` | Output file                                     |
| `--strip-comments` | off               | Strip LaTeX comments from output                |
| `--no-markers`     | off               | Suppress begin/end markers around inlined files |
| `-f` `--force`     | off               | Overwrite output file if it already exists      |

## Supported commands

| Command                                   | Action                                          |
| ----------------------------------------- | ----------------------------------------------- |
| `\input{path}`                            | Recursively inline; argument may span lines     |
| `\include{path}`                          | Recursively inline; argument may span lines     |
| `\includeonly{...}`                       | Commented out (dropped with `--strip-comments`) |
| `\bibliography{...}`                      | Preserved as-is                                 |
| `\includegraphics{...}`                   | Preserved as-is                                 |
| `\usepackage{...}`, `\documentclass{...}` | Preserved as-is                                 |

Other inclusion commands, including `\subfile` and `\import`, are preserved
as-is and produce a warning explaining that they are unsupported.

## Warnings

The merger emits a warning, while continuing when possible, for constructs that
may need manual review:

- unsupported `\subfile` and `\import` commands;
- malformed or incomplete `\input` and `\include` commands;
- mid-line inclusion commands;
- multiple inclusion commands on one logical line (only the first is expanded);
- comments inside a multiline inclusion command;
- `\includeonly`, which is commented out or removed;
- paths resolved with the containing-file fallback;
- paths that exist relative to both the main file and the containing file.

## Path resolution

Included paths are resolved relative to the main file's directory, with a fallback to the directory of the file containing the command. Both `\input{sections/intro}` and `\input{sections/intro.tex}` are accepted.

## Output markers

By default, each inlined file is wrapped in markers:

```
% ====================== Begin sections/intro.tex ======================

... content ...

%======================= End sections/intro.tex =======================
```

Use `--no-markers` to suppress them.

## Demo

See `demo/` for a sample multi-file LaTeX project with pre-generated merged outputs:

- `demo/main-merged.tex` — merged with markers
- `demo/main-merged-stripped.tex` — merged with `--strip-comments --no-markers` (arXiv-ready)

## Limitations

- Inline `\verb|...|` and `\lstinline|...|` are not protected from comment stripping. If a `%` appears inside an inline verbatim on the same line as an `\input`, the `\input` may be incorrectly treated as commented. This is rare in practice.
- The tool does not expand `\bibliography{...}` (use `biber`/`bibtex` then `bbl` files separately).
- Non-UTF-8 files will raise a `UnicodeDecodeError`.
