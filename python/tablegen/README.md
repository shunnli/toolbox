# tablegen

A command-line table generator for numerical experiments in Python.

It reads JSON data and generates aligned plain-text tables or LaTeX tables. It can also compute convergence orders from a reference column.

This is a standalone script with no third-party dependencies.

## Quick start

```bash
python tablegen.py data.json
```

Generate LaTeX output:

```bash
python tablegen.py data.json --type latex --output table.tex
```

Print an example JSON file:

```bash
python tablegen.py --example
```

Read JSON from stdin:

```bash
cat data.json | python tablegen.py -
```

Compute convergence orders interactively:

```bash
python tablegen.py --interactive
```

## CLI reference

```text
python tablegen.py [input] [options]
```

| Option | Default | Description |
| --- | --- | --- |
| `input` | required unless `--example` or `--interactive` | JSON file path. Use `-` to read from stdin. |
| `--example` | off | Print an example JSON document and exit. |
| `--type {plain,latex}` | inferred | Override output type. |
| `--output PATH` | stdout | Write table to a file. A `.tex` extension implies LaTeX output unless `--type` is set. |
| `--transpose` | off | Transpose the generated table, including the header row. |
| `--no-latex-env` | off | For LaTeX output, emit only tabular rows instead of a full `table` environment. |
| `--quiet` | off | Suppress the "Written output" status message when writing to a file. |
| `-i`, `--interactive` | off | Prompt for values and reference values, then print a quick plain-text convergence table. |

Output type is chosen with this priority:

1. command-line `--type`
2. `--output` ending in `.tex`
3. top-level JSON field `"type"`
4. `plain`

## JSON format

Example JSON:

```json
{
    "type": "latex",
    "title": "Convergence Test",
    "note": "Order is computed with respect to N.",
    "data": [
        {"label": "N", "values": [10, 20, 40, 80], "format": "%d"},
        {
            "label": "err",
            "title": {"latex": "$L^2$ error", "plain": "L2 error"},
            "values": [0.1, 0.025, 0.00625, 0.0015625],
            "format": ["%.2e", "%.2f"],
            "order_ref": "N"
        }
    ]
}
```

Top-level fields:

| Field | Required | Description |
| --- | --- | --- |
| `data` | yes | Non-empty list of column definitions. |
| `type` | no | `plain` or `latex`. Can be overridden by CLI options. |
| `title` | no | Plain-text title or LaTeX caption text. |
| `note` | no | Extra note printed after plain output or as LaTeX comments. |

Each item in `data` describes one source column:

| Field | Required | Description |
| --- | --- | --- |
| `label` | yes | Unique internal column name. Used by `order_ref`. |
| `values` | yes | Non-empty scalar or list. All columns must have the same length after scalar normalization. |
| `title` | no | Display title. May be a string or an object such as `{"plain": "L2 error", "latex": "$L^2$ error"}`. |
| `format` | no | printf-style format string for values, or `[value_format, order_format]` when `order_ref` is used. |
| `order_ref` | no | Label of another numeric column used to compute convergence order. |
| `hidden` | no | Boolean. Hidden columns can still be used as `order_ref` references. |

The generated table contains the value column and an additional `order` column:

```text
-----------------
N  L2 error order
10 1.00e-01 -
20 2.50e-02 2.00
40 6.25e-03 2.00
80 1.56e-03 2.00
-----------------
```

## Convergence order

For a value column `v` with reference column `r`, the order between consecutive
rows is:

```text
-log(v_i / v_{i-1}) / log(r_i / r_{i-1})
```

This supports common cases where `r` is mesh size, time step, or a hidden inverse
resolution column. All values used in order computation must be finite positive
numbers, and consecutive reference values must differ.

The first order entry is printed as `-` because there is no previous row.

## LaTeX output

Normal LaTeX output emits a complete `table` environment. When the table is not
transposed, it uses `booktabs` commands:

```latex
\toprule
\midrule
\bottomrule
```

Include `\usepackage{booktabs}` in the document that consumes the generated
table. Use `--no-latex-env` when you only want rows for an existing tabular
environment.

## Validation

The script validates the JSON before generating output:

- top-level JSON must be an object
- `data` must be a non-empty list
- labels must be strings and unique
- all value lists must have the same length
- `title` must be a string or a string-to-string object
- `format` must be a string or a list of at most two strings
- `hidden` must be boolean
- `order_ref` must reference an existing, different label

Validation errors are printed to stderr and return a non-zero exit code.
