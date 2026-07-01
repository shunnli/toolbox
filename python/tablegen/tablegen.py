#! /usr/bin/env python3

import json
import math
import argparse
import os
import sys


EXAMPLE_JSON = {
    "type": "latex",
    "title": "Convergence Test for Example Scheme",
    "note": "Order is computed with respect to the first column.\nAll values are L2 errors.",
    "data": [
        {"label": "N", "values": [10, 20, 40, 80], "format": "%d"},
        {"label": "invN", "values": [0.1, 0.05, 0.025, 0.0125], "hidden": True},
        {
            "label": "errA",
            "title": "Error (A)",
            "values": [0.123, 0.031, 0.0078, 0.00195],
            "format": ["%.2e", "%.2f"],
            "order_ref": "N",
        },
        {
            "label": "errB",
            "title": {"latex": "$L^2$ Error(B)", "plain": "L2 Error (B)"},
            "values": [0.098, 0.024, 0.0061, 0.0015],
            "format": ["%.2e", "%.2f"],
            "order_ref": "N",
        },
        {
            "label": "CPU time (s)",
            "values": [10, 40, 160, 640],
            "format": "%.2f",
            "order_ref": "invN",
        },
    ],
}


def resolve_title(item, output_type: str):
    """
    Resolve display title depending on output type ('plain' or 'latex').
    Priority:
      1. title[output_type]
      2. title (string)
      3. label
    """
    title = item.get("title")
    label = item["label"]

    if isinstance(title, dict):
        if output_type in title and isinstance(title[output_type], str):
            return title[output_type]
        return label

    if isinstance(title, str):
        return title

    return label


def validate_json(data_json):
    if not isinstance(data_json, dict):
        raise ValueError("Top-level JSON must be an object.")

    if "data" not in data_json:
        raise ValueError("Missing required field: 'data'.")

    data = data_json["data"]
    if not isinstance(data, list) or not data:
        raise ValueError("'data' must be a non-empty list.")

    labels = []
    value_lengths = []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"data[{i}] must be an object.")

        # label (unique)
        label = item.get("label")
        if not isinstance(label, str):
            raise ValueError(f"data[{i}]: 'label' must be a string.")
        if label in labels:
            raise ValueError(f"Duplicate label '{label}'.")
        labels.append(label)

        # title (display name, optional, NOT unique)
        if "title" in item:
            t = item["title"]
            if isinstance(t, dict):
                for k, v in t.items():
                    if not isinstance(k, str) or not isinstance(v, str):
                        raise ValueError(
                            f"data[{i}]: 'title' dict must map strings to strings."
                        )
            elif isinstance(t, str):
                pass
            else:
                raise ValueError(f"data[{i}]: 'title' must be a string or a dict.")

        # values
        values = item.get("values")

        # scalar: x -> [x]
        if isinstance(values, (int, float)):
            values = [values]
            item["values"] = values

        if not isinstance(values, list) or not values:
            raise ValueError(f"data[{i}]: 'values' must be a non-empty list.")
        value_lengths.append(len(values))

        # format
        fmt = item.get("format")
        if fmt is not None:
            if isinstance(fmt, list):
                if not all(isinstance(f, str) for f in fmt):
                    raise ValueError(
                        f"data[{i}]: all entries in 'format' list must be strings."
                    )
                if len(fmt) > 2:
                    raise ValueError(
                        f"data[{i}]: 'format' list can have at most 2 elements."
                    )
            elif not isinstance(fmt, str):
                raise ValueError(
                    f"data[{i}]: 'format' must be a string or list of strings."
                )

        # hidden
        hidden = item.get("hidden", False)
        if not isinstance(hidden, bool):
            raise ValueError(f"data[{i}]: 'hidden' must be boolean if provided.")

    # check consistent row count
    if len(set(value_lengths)) != 1:
        raise ValueError("All 'values' lists must have the same length.")

    # check order_ref
    value_map = {item["label"]: item["values"] for item in data}
    for i, item in enumerate(data):
        if "order_ref" in item:
            ref = item["order_ref"]
            if not isinstance(ref, str):
                raise ValueError(f"data[{i}]: 'order_ref' must be a string.")
            if ref not in labels:
                raise ValueError(
                    f"data[{i}]: 'order_ref'='{ref}' does not match any label."
                )
            if ref == item["label"]:
                raise ValueError(f"data[{i}]: 'order_ref' cannot refer to itself.")

            values = item["values"]
            ref_values = value_map[ref]
            for row_idx in range(1, len(values)):
                try:
                    v_prev = float(values[row_idx - 1])
                    v_cur = float(values[row_idx])
                    r_prev = float(ref_values[row_idx - 1])
                    r_cur = float(ref_values[row_idx])
                except (TypeError, ValueError):
                    raise ValueError(
                        f"data[{i}]: 'order_ref' requires numeric values at row {row_idx + 1}."
                    )

                if (
                    not math.isfinite(v_prev)
                    or not math.isfinite(v_cur)
                    or not math.isfinite(r_prev)
                    or not math.isfinite(r_cur)
                ):
                    raise ValueError(
                        f"data[{i}]: non-finite number detected for 'order_ref' at row {row_idx + 1}."
                    )

                if v_prev <= 0 or v_cur <= 0:
                    raise ValueError(
                        f"data[{i}]: values must be > 0 for order computation (row {row_idx + 1})."
                    )
                if r_prev <= 0 or r_cur <= 0:
                    raise ValueError(
                        f"data[{i}]: reference '{ref}' must be > 0 for order computation (row {row_idx + 1})."
                    )
                if r_prev == r_cur:
                    raise ValueError(
                        f"data[{i}]: reference '{ref}' has equal consecutive values at rows {row_idx} and {row_idx + 1}."
                    )

    output_type = data_json.get("type")
    if output_type is not None and output_type not in ("plain", "latex"):
        raise ValueError("Top-level 'type' must be either 'plain' or 'latex'.")


def compute_order(ref: list[float], val: list[float]) -> list[float]:
    """
    Compute convergence order with respect to reference values.
    """
    orders = []
    for i in range(1, len(val)):
        try:
            v_prev = float(val[i - 1])
            v_cur = float(val[i])
            r_prev = float(ref[i - 1])
            r_cur = float(ref[i])
        except (TypeError, ValueError):
            raise ValueError(f"Non-numeric value for order computation at row {i + 1}.")

        if (
            not math.isfinite(v_prev)
            or not math.isfinite(v_cur)
            or not math.isfinite(r_prev)
            or not math.isfinite(r_cur)
        ):
            raise ValueError(f"Non-finite value for order computation at row {i + 1}.")
        if v_prev <= 0 or v_cur <= 0 or r_prev <= 0 or r_cur <= 0:
            raise ValueError(
                f"All values used in order computation must be > 0 (row {i + 1})."
            )
        if r_prev == r_cur:
            raise ValueError(
                f"Reference values at rows {i} and {i + 1} are equal; order is undefined."
            )

        denom = math.log(r_cur / r_prev)
        if denom == 0:
            raise ValueError(
                f"Reference ratio is 1 at row {i + 1}; order is undefined."
            )
        orders.append(-math.log(v_cur / v_prev) / denom)

    return orders


def format_value(x, fmt):
    """
    Format a single value using a printf-style format.
    """
    if fmt is None:
        return str(x)
    try:
        return fmt % x
    except Exception:
        return str(x)


def process_data(data_json, output_type: str) -> tuple[list[str], list[list[str]]]:
    """
    Process raw JSON data and return a string table.

    Returns:
        headers : list of column titles
        rows    : 2D list of strings
    """
    data = data_json["data"]
    n_rows = len(data[0]["values"])

    # Map label -> raw values (for order_ref lookup)
    value_map = {d["label"]: d["values"] for d in data}

    headers = []
    column_blocks = []

    for item in data:
        title = resolve_title(item, output_type)
        hidden = item.get("hidden", False)
        values = item["values"]
        fmt = item.get("format")

        # Normalize format definition
        if isinstance(fmt, list):
            value_fmt = fmt[0]
            order_fmt = fmt[1] if len(fmt) > 1 else None
        else:
            value_fmt = fmt
            order_fmt = None

        # Main column values
        formatted_values = [format_value(v, value_fmt) for v in values]

        if not hidden:
            headers.append(title)
            column_blocks.append(formatted_values)

        # Optional order column
        if "order_ref" in item:
            ref_values = value_map[item["order_ref"]]
            orders = compute_order(ref_values, values)

            order_strings = ["-"] + [format_value(o, order_fmt) for o in orders]

            if not hidden:
                headers.append("order")
                column_blocks.append(order_strings)

    # Assemble row-wise table
    if not column_blocks:
        raise ValueError(
            "No visible columns to output. At least one data column must not be hidden."
        )
    rows = [
        [column_blocks[j][i] for j in range(len(column_blocks))] for i in range(n_rows)
    ]

    return headers, rows


def transpose_table(headers, rows):
    """
    Transpose a table including header.
    """
    full = [headers] + rows
    transposed = list(map(list, zip(*full)))
    return transposed[0], transposed[1:]


def format_plain(headers, rows, title=None, note=None) -> str:
    """
    Format table as aligned plain text.
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(v))

    lines = []

    if title:
        lines.append(title)

    lines.append("-" * (sum(widths) + len(widths) - 1))

    lines.append(" ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    for row in rows:
        lines.append(" ".join(v.ljust(widths[i]) for i, v in enumerate(row)))

    lines.append("-" * (sum(widths) + len(widths) - 1))

    if note:
        for line in note.splitlines():
            lines.append(f"# {line}")

    return "\n".join(lines)


def format_latex(
    headers,
    rows,
    use_latex_env: bool,
    use_booktabs: bool,
    title=None,
    note=None,
) -> str:
    """
    Format table as LaTeX.
    """

    col_widths = [len(h) for h in headers]
    for row in rows:
        for j, v in enumerate(row):
            col_widths[j] = max(col_widths[j], len(v))

    lines = []

    if use_latex_env:
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"    \centering")

        if title:
            lines.append(r"    \caption{" + title + r"} % \label{tab:XXX}")
        else:
            lines.append(r"    % \caption{XXX} % \label{tab:XXX}")

        if use_booktabs:
            lines.append(f"    \\begin{{tabular}}{{{'c' * len(headers)}}}")
        else:
            lines.append(f"    \\begin{{tabular}}{{{'c|' + 'c' * (len(headers)-1)}}}")

        if use_booktabs:
            lines.append(r"        \toprule")
        else:
            lines.append(r"        \hline")

    else:
        if title:
            lines.append(r"% \caption{" + title + r"} % \label{tab:XXX}")

    indent = (" " * 8) if use_latex_env else ""

    lines.append(
        indent
        + " & ".join(headers[j].ljust(col_widths[j]) for j in range(len(headers)))
        + r" \\"
    )

    if use_latex_env:
        if use_booktabs:
            lines.append(indent + r"\midrule")
        else:
            lines.append(indent + r"\hline")

    for row in rows:
        lines.append(
            indent
            + " & ".join(row[j].ljust(col_widths[j]) for j in range(len(row)))
            + r" \\"
        )

        if use_latex_env and not use_booktabs:
            lines.append(indent + r"\hline")

    if use_latex_env:
        if use_booktabs:
            lines.append(indent + r"\bottomrule")

        lines.append(r"    \end{tabular}")

        if note:
            for line in note.splitlines():
                lines.append(f"    % {line}")

        lines.append(r"\end{table}")
    else:
        if note:
            for line in note.splitlines():
                lines.append(f"% {line}")

    return "\n".join(lines)


def interactive_mode():

    def parse_float_list(s: str) -> list[float]:
        tokens = s.replace(",", " ").split()
        values = []
        for t in tokens:
            try:
                v = float(t)
            except ValueError:
                raise ValueError(f"Invalid number: '{t}'")
            if not math.isfinite(v) or v <= 0:
                raise ValueError(f"Invalid value (must be positive): {v}")
            values.append(v)
        if len(values) < 2:
            raise ValueError("At least two values are required.")
        return values

    print("Interactive convergence order computation")
    print()

    # ---- read values ----
    while True:
        try:
            s = input("Enter values (space or comma separated):\n> ")
            values = parse_float_list(s)
            break
        except ValueError as e:
            print(f"Error: {e}")

    # ---- read N ----
    s = input(
        "Enter reference N values (same length), or press Enter to use doubling:\n> "
    ).strip()

    if s:
        N = parse_float_list(s)
        if len(N) != len(values):
            print("Error: N must have the same length as values.")
            sys.exit(1)
    else:
        N = [2**i for i in range(len(values))]

    orders = compute_order(N, values)

    headers = ["N", "value", "order"]
    rows = []

    for i in range(len(values)):
        if i == 0:
            rows.append([str(N[i]), f"{values[i]:.2e}", "-"])
        else:
            rows.append(
                [
                    str(N[i]),
                    f"{values[i]:.2e}",
                    f"{orders[i-1]:.2f}",
                ]
            )

    print()
    print(format_plain(headers, rows))


def parse_args():
    parser = argparse.ArgumentParser(
        prog="tablegen", description="Generate numerical tables from JSON data."
    )
    parser.add_argument("input", nargs="?", help="Input JSON file")
    parser.add_argument(
        "--example", action="store_true", help="Print an example JSON file and exit"
    )
    parser.add_argument(
        "--transpose", action="store_true", help="Transpose table output"
    )
    parser.add_argument(
        "--type", choices=["plain", "latex"], help="Override output type"
    )
    parser.add_argument(
        "--no-latex-env",
        action="store_true",
        help="Do NOT wrap LaTeX output in table environment",
    )
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--quiet", action="store_true", help="Suppress status messages")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactive mode for quick convergence order computation",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.interactive:
        try:
            interactive_mode()
        except KeyboardInterrupt:
            print("\n[tablegen] Interrupted by user.")
        return

    if args.example:
        print(json.dumps(EXAMPLE_JSON, indent=4))
        sys.exit(0)

    if not args.input:
        print(
            "Error: input JSON file is required (use '-' to read from stdin).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        if args.input == "-":
            # Read JSON from stdin
            data_json = json.load(sys.stdin)
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                data_json = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        validate_json(data_json)
    except ValueError as e:
        print(f"Invalid JSON format: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine output type with priority: ("latex", "plain")
    # 1. Command-line --type
    # 2. Output file extension (.tex)
    # 3. JSON "type" field
    if args.type:
        output_type = args.type
    elif args.output and args.output.lower().endswith(".tex"):
        output_type = "latex"
    else:
        output_type = data_json.get("type", "plain")

    try:
        headers, rows = process_data(data_json, output_type)
    except ValueError as e:
        print(f"Invalid data for table generation: {e}", file=sys.stderr)
        sys.exit(1)

    if args.transpose:
        headers, rows = transpose_table(headers, rows)

    title = data_json.get("title")
    note = data_json.get("note")

    if output_type == "plain":
        output_text = format_plain(headers, rows, title=title, note=note)
    else:
        use_latex_env = not args.no_latex_env
        use_booktabs = use_latex_env and (not args.transpose)

        output_text = format_latex(
            headers,
            rows,
            use_latex_env=use_latex_env,
            title=title,
            note=note,
            use_booktabs=use_booktabs,
        )

    if args.output:
        try:
            # Convert output path to absolute path
            output_path = os.path.abspath(args.output).replace("\\", "/")

            with open(output_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(output_text)
                if not args.quiet:
                    print(
                        f"[tablegen] Written output to {output_path}", file=sys.stderr
                    )
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            print(output_text)
            sys.exit(1)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
