# archive

A small command-line archiving utility for Python.

It packs selected files and directories into a `zip` or `tar.gz` archive, with optional extension filtering and timestamped output names.

This is a standalone script with no third-party dependencies.

## Quick start

```bash
python archive.py \
  --targets project notes.md \
  --output outputs \
  --name backup \
  --ext py md \
  --format auto
```

On Windows, `--format auto` creates a `zip` file. On other platforms, it creates a `tar.gz` file.

## CLI reference

```text
python archive.py --targets PATH [PATH ...] --output DIR --name NAME [options]
```

| Option | Default | Description |
| --- | --- | --- |
| `--targets PATH ...` | required | Files and/or directories to archive. |
| `--output DIR` | required | Directory where the archive is written. It must not be inside a target directory. |
| `--name NAME` | required | Archive base name, without `.zip` or `.tar.gz`. |
| `--ext EXT ...` | all files | Include only files with these extensions. Leading dots are optional. |
| `--format {auto,zip,tar.gz}` | `auto` | Archive format. `auto` selects `zip` on Windows and `tar.gz` elsewhere. |
| `--no-timestamp` | off | Do not append `YYYYMMDD-HHMMSS` to the archive name. |
| `--dry-run` | off | Print the archive path and member list without creating directories or files. |

## Examples

Archive a project directory and a single notes file:

```bash
python archive.py --targets project notes.md --output outputs --name backup
```

Archive only TeX-related files:

```bash
python archive.py --targets paper --output outputs --name paper-source --ext tex bib cls sty
```

Create a deterministic archive name:

```bash
python archive.py --targets project --output outputs --name backup --no-timestamp
```

To preview the archive contents without creating files, use `--dry-run`:

```bash
python archive.py \
  --targets project \
  --output outputs \
  --name backup \
  --dry-run
```

By default, the archive name includes a timestamp:

```text
backup-20260101-010203.zip
backup-20260101-010203.tar.gz
```

Use `--no-timestamp` to create a deterministic archive name.

## Archive layout

Directory targets keep the top-level directory name inside the archive:

```text
project/src/main.py
project/README.md
```

File targets are stored at archive root:

```text
notes.md
```

Entries are sorted for stable output order.

## Validation and ignored files

The script rejects unsafe or ambiguous directory layouts:

- the output directory must not be inside a target directory
- target directories must not contain each other
- every target must already exist
- the final archive path must not already exist

The following generated directories are skipped while walking directory targets:

```text
.git
.svn
__pycache__
.mypy_cache
.pytest_cache
.cache
```

The following common system files are skipped:

```text
.DS_Store
Thumbs.db
```

## Exit codes

- `0`: archive created successfully, or dry-run completed
- `1`: invalid paths, archive creation failure, or output file already exists
- `2`: no files matched the selected targets and extension filter
