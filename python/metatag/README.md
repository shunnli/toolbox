# metatag

Insert, read, or delete metadata in PNG files.

Each key=value pair is stored as a standard PNG text chunk — ASCII values use `tEXt`, Unicode values use `iTXt`. Metadata is readable by **exiftool**, **pngcheck**, **ImageMagick**, and any PNG-aware tool.

Cross-platform (Windows & Linux). Zero mandatory dependencies.

## Quick start

```bash
# Write metadata
python metatag.py set image.png "author=Alice" "date=2024-06-15" "note=中文测试"

# Write metadata from a JSON file
python metatag.py set image.png -f metadata.json

# Read metadata
python metatag.py read image.png

# Read a single key
python metatag.py read image.png author

# Delete a key
python metatag.py delete image.png date
```

## CLI

```
python metatag.py <command> [options]
```

### `read` — read metadata

```
python metatag.py read <file> [KEY ...] [--raw] [-q]
```

| Flag | Description |
|------|-------------|
| `file` | PNG file path |
| `KEY` | Specific key(s) to read (omit to list all) |
| `--raw` | Output as `KEY=VALUE` (one per line) |
| `-q`, `--quiet` | Suppress "(no metadata)" when file has no metadata |

### `set` — insert or update metadata

```
python metatag.py set <file> [KEY=VALUE ...] [-f JSON] [-o FILE] [-q]
```

| Flag | Default | Description |
|------|---------|-------------|
| `file` | (required) | PNG file path |
| `KEY=VALUE` | — | One or more key=value pairs |
| `-f`, `--file-json` | — | JSON file with key-value pairs to set |
| `-o`, `--output` | overwrite input | Write to a different file |
| `-q`, `--quiet` | off | Suppress informational output |

Set does a read-merge-write: new keys are added, existing keys are updated, other keys are preserved.  Pairs from `-f` and the command line are merged together; command-line pairs take precedence when keys collide.

### `delete` — remove metadata keys

```
python metatag.py delete <file> KEY [...] [-o FILE] [-q]
```

| Flag | Default | Description |
|------|---------|-------------|
| `file` | (required) | PNG file path |
| `KEY` | (required) | One or more keys to remove |
| `-o`, `--output` | overwrite input | Write to a different file |
| `-q`, `--quiet` | off | Suppress informational output |

## Storage format

Each key=value becomes a separate PNG text chunk. ASCII-only values use `tEXt`, anything else uses `iTXt` (UTF-8). The chunk keyword is the metadata key itself:

```
$ pngcheck -v image.png
  ...
  tEXt  author     Alice
  tEXt  date       2024-06-15
  iTXt  note       中文测试
  ...
```

### Value size

PNG chunk data is capped at 2 GiB. Practical text values (a few bytes to several MB) work fine. JSON and other structured data can be stored:

```bash
python metatag.py set image.png "config=$(cat config.json)"
```

## Naming conventions

The following keywords are used by common software. Avoid reusing them unless intentional:

| Keyword | Used by |
|---------|---------|
| `Title` | GIMP, Photoshop |
| `Author` | GIMP, Photoshop |
| `Description` | GIMP, Photoshop, ImageMagick |
| `Copyright` | GIMP, Photoshop |
| `Comment` | exiftool, GIMP |
| `Software` | GIMP, Photoshop, ImageMagick |
| `Creation Time` | GIMP, exiftool |
| `Source` | Scanners / cameras |
| `Make`, `Model` | Camera EXIF data |

Use namespaced keys (e.g. `project:author`, `app:version`) or Chinese keys (`项目`, `版本`) to stay clear of conflicts.

## Interoperability

Metadata written by metatag can be read by other tools, and vice versa:

```bash
# Read metatag metadata with exiftool
exiftool -PNG:all image.png

# Read metadata written by exiftool/GIMP/Photoshop
python metatag.py read image.png
```

`metatag read` returns all text chunks regardless of origin. `metatag set` reads everything, updates only the given keys, and writes back — it will preserve chunks from other tools as long as key names don't collide.
