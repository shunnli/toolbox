#! /usr/bin/env python3
"""Insert, read, or delete metadata in PNG files.

Each key=value pair is stored as a standard tEXt or iTXt chunk — readable by
exiftool, pngcheck, ImageMagick, and Windows Explorer (for recognized keys).
"""

import argparse
import json
import os
import struct
import sys
from typing import NoReturn

# ======================================================================
# PNG chunk I/O
# ======================================================================

_SIG = b"\x89PNG\r\n\x1a\n"


def _crc(data: bytes) -> int:
    v = 0xFFFFFFFF
    for b in data:
        v ^= b
        for _ in range(8):
            if v & 1:
                v = (v >> 1) ^ 0xEDB88320
            else:
                v >>= 1
    return v ^ 0xFFFFFFFF


def _write_chunk(f, chunk_type: str, data: bytes) -> None:
    raw = chunk_type.encode("ascii") + data
    f.write(struct.pack(">I", len(data)))
    f.write(raw)
    f.write(struct.pack(">I", _crc(raw)))


def _iter_chunks(filepath: str):
    with open(filepath, "rb") as f:
        sig = f.read(8)
        if sig != _SIG:
            raise ValueError(f"Not a valid PNG file: {filepath}")
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            length = struct.unpack(">I", hdr[:4])[0]
            ctype = hdr[4:8].decode("ascii", errors="replace")
            data = f.read(length)
            f.read(4)  # CRC
            yield ctype, data
            if ctype == "IEND":
                break


def _decode_text(chunk_type: str, data: bytes) -> tuple[str, str]:
    if chunk_type == "tEXt":
        parts = data.split(b"\x00", 1)
        if len(parts) == 2:
            return parts[0].decode("latin-1"), parts[1].decode("latin-1")
    elif chunk_type == "iTXt":
        parts = data.split(b"\x00", 4)
        if len(parts) >= 5:
            return parts[0].decode("utf-8"), parts[4].decode("utf-8")
    return "", ""


def _encode_text(key: str, value: str) -> tuple[str, bytes]:
    if key.isascii() and value.isascii():
        return "tEXt", key.encode("ascii") + b"\x00" + value.encode("ascii")
    return "iTXt", key.encode("utf-8") + b"\x00\x00\x00\x00" + value.encode("utf-8")


def _read_meta(filepath: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for ctype, data in _iter_chunks(filepath):
        if ctype in ("tEXt", "iTXt"):
            k, v = _decode_text(ctype, data)
            if k:
                meta[k] = v
    return meta


def _write_meta(filepath: str, meta: dict[str, str], output: str | None = None) -> None:
    target = output or filepath
    chunks: list[tuple[str, bytes]] = []

    for ctype, data in _iter_chunks(filepath):
        if ctype in ("tEXt", "iTXt"):
            continue
        chunks.append((ctype, data))

    with open(target, "wb") as f:
        f.write(_SIG)
        inserted = False
        for ctype, data in chunks:
            if not inserted and ctype in ("IDAT", "PLTE"):
                for k, v in meta.items():
                    t, d = _encode_text(k, v)
                    _write_chunk(f, t, d)
                inserted = True
            _write_chunk(f, ctype, data)
        if not inserted and meta:
            for k, v in meta.items():
                t, d = _encode_text(k, v)
                _write_chunk(f, t, d)


# ======================================================================
# commands
# ======================================================================


def cmd_read(args) -> None:
    if not os.path.exists(args.file):
        _die(f"file not found: {args.file}")

    try:
        meta = _read_meta(args.file)
    except ValueError as e:
        _die(str(e))

    if args.keys:
        for k in args.keys:
            if k in meta:
                _info(meta[k])
            else:
                _die(f"key not found: {k}")
    elif meta:
        if args.raw:
            for k, v in meta.items():
                _info(f"{k}={v}")
        else:
            width = max(len(k) for k in meta)
            for k, v in meta.items():
                _info(f"{k:<{width}}  {v}")
    elif not args.quiet:
        _info("(no metadata)")


def cmd_set(args) -> None:
    if not os.path.exists(args.file):
        _die(f"file not found: {args.file}")

    new = {}
    if args.file_json:
        try:
            with open(args.file_json, encoding="utf-8") as fh:
                loaded = json.load(fh)
            for k, v in loaded.items():
                new[str(k)] = str(v)
        except (json.JSONDecodeError, OSError) as e:
            _die(f"failed to read JSON file: {e}")

    for item in args.pairs:
        if "=" in item:
            k, v = item.split("=", 1)
            new[k.strip()] = v.strip()
        else:
            _warn(f"ignoring invalid key=value pair: {item}")

    if not new:
        _die("no valid KEY=VALUE pairs provided")

    try:
        current = _read_meta(args.file)
        current.update(new)
        _write_meta(args.file, current, args.output)
    except (ValueError, OSError) as e:
        _die(str(e))

    if not args.quiet:
        target = args.output or args.file
        _info(f"{len(new)} key(s) set in {target}")


def cmd_delete(args) -> None:
    if not os.path.exists(args.file):
        _die(f"file not found: {args.file}")

    try:
        current = _read_meta(args.file)
    except ValueError as e:
        _die(str(e))

    for k in args.keys:
        if k not in current:
            _warn(f"key not found: {k}")

    removed = 0
    for k in args.keys:
        if k in current:
            del current[k]
            removed += 1

    if removed == 0:
        _warn("no keys were deleted")
        return

    try:
        _write_meta(args.file, current, args.output)
    except (ValueError, OSError) as e:
        _die(str(e))

    if not args.quiet:
        target = args.output or args.file
        _info(f"{removed} key(s) deleted from {target}")


_TAG = "[metatag]"


def _info(msg: str) -> None:
    print(f"{_TAG} {msg}")


def _warn(msg: str) -> None:
    print(f"{_TAG} Warning: {msg}", file=sys.stderr)


def _die(msg: str) -> NoReturn:
    print(f"{_TAG} Error: {msg}", file=sys.stderr)
    sys.exit(1)


# ======================================================================
# CLI
# ======================================================================


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="metatag",
        description="Insert, read, or delete metadata in PNG files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    r = sub.add_parser("read", help="Read metadata from a PNG file")
    r.add_argument("file", help="PNG file path")
    r.add_argument(
        "keys",
        nargs="*",
        metavar="KEY",
        help="Specific key(s) to read (omit to list all)",
    )
    r.add_argument(
        "--raw", action="store_true", help="Output as KEY=VALUE (one per line)"
    )
    r.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress informational output"
    )

    s = sub.add_parser("set", help="Insert or update metadata in a PNG file")
    s.add_argument("file", help="PNG file path")
    s.add_argument(
        "pairs", nargs="*", metavar="KEY=VALUE", help="Metadata key=value pair(s)"
    )
    s.add_argument(
        "-f",
        "--file-json",
        default=None,
        help="JSON file with key-value pairs to set",
    )
    s.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output file path (default: overwrite input)",
    )
    s.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress informational output"
    )

    d = sub.add_parser("delete", help="Delete metadata keys from a PNG file")
    d.add_argument("file", help="PNG file path")
    d.add_argument("keys", nargs="+", metavar="KEY", help="Metadata key(s) to delete")
    d.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output file path (default: overwrite input)",
    )
    d.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress informational output"
    )

    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.command is None:
        _die("a subcommand is required: read, set, delete")

    if args.command == "read":
        cmd_read(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "delete":
        cmd_delete(args)


if __name__ == "__main__":
    main()
