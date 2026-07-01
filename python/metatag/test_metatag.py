import json
import os
import struct
import tempfile
import unittest
import zlib
from io import StringIO
from unittest.mock import patch

import metatag


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _minimal_png(path: str) -> None:
    def crc(data):
        v = 0xFFFFFFFF
        for b in data:
            v ^= b
            for _ in range(8):
                v = (v >> 1) ^ 0xEDB88320 if v & 1 else v >> 1
        return v ^ 0xFFFFFFFF

    def chunk(ctype, data):
        raw = ctype + data
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", crc(raw))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")))
        f.write(chunk(b"IEND", b""))


# ---------------------------------------------------------------------------
# _encode_text / _decode_text
# ---------------------------------------------------------------------------


class EncodeDecodeTest(unittest.TestCase):
    def test_ascii_uses_tEXt(self):
        t, d = metatag._encode_text("Author", "Alice")
        self.assertEqual(t, "tEXt")
        k, v = metatag._decode_text(t, d)
        self.assertEqual((k, v), ("Author", "Alice"))

    def test_unicode_uses_iTXt(self):
        t, d = metatag._encode_text("note", "中文")
        self.assertEqual(t, "iTXt")
        k, v = metatag._decode_text(t, d)
        self.assertEqual((k, v), ("note", "中文"))

    def test_round_trip_ascii(self):
        t, d = metatag._encode_text("key", "value")
        k, v = metatag._decode_text(t, d)
        self.assertEqual((k, v), ("key", "value"))

    def test_round_trip_unicode(self):
        t, d = metatag._encode_text("标签", "值")
        k, v = metatag._decode_text(t, d)
        self.assertEqual((k, v), ("标签", "值"))


# ---------------------------------------------------------------------------
# _read_meta / _write_meta
# ---------------------------------------------------------------------------


class ReadWriteMetaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self.tmp.close()
        _minimal_png(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_read_empty(self):
        self.assertEqual(metatag._read_meta(self.tmp.name), {})

    def test_write_and_read(self):
        metatag._write_meta(self.tmp.name, {"a": "1", "b": "2"})
        self.assertEqual(metatag._read_meta(self.tmp.name), {"a": "1", "b": "2"})

    def test_write_replaces_all_text_chunks(self):
        metatag._write_meta(self.tmp.name, {"a": "1"})
        metatag._write_meta(self.tmp.name, {"b": "2"})
        self.assertEqual(metatag._read_meta(self.tmp.name), {"b": "2"})

    def test_set_preserves_via_merge(self):
        current = metatag._read_meta(self.tmp.name)
        current.update(a="1", b="2")
        metatag._write_meta(self.tmp.name, current)
        # Now set c, preserving a and b
        current = metatag._read_meta(self.tmp.name)
        current.update(c="3")
        metatag._write_meta(self.tmp.name, current)
        self.assertEqual(metatag._read_meta(self.tmp.name), {"a": "1", "b": "2", "c": "3"})

    def test_delete_via_merge(self):
        metatag._write_meta(self.tmp.name, {"a": "1", "b": "2", "c": "3"})
        current = metatag._read_meta(self.tmp.name)
        del current["b"]
        metatag._write_meta(self.tmp.name, current)
        self.assertEqual(metatag._read_meta(self.tmp.name), {"a": "1", "c": "3"})

    def test_unicode_round_trip(self):
        metatag._write_meta(self.tmp.name, {"note": "中文测试", "标签": "值"})
        self.assertEqual(metatag._read_meta(self.tmp.name), {"note": "中文测试", "标签": "值"})

    def test_output_to_different_file(self):
        metatag._write_meta(self.tmp.name, {"src": "original"})
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            f2.close()
            _minimal_png(f2.name)
            try:
                metatag._write_meta(self.tmp.name, {"src": "via-output"}, output=f2.name)
                self.assertEqual(metatag._read_meta(self.tmp.name), {"src": "original"})
                self.assertEqual(metatag._read_meta(f2.name), {"src": "via-output"})
            finally:
                os.unlink(f2.name)

    def test_rejects_invalid_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"not a png")
            f.close()
            try:
                with self.assertRaises(ValueError):
                    metatag._read_meta(f.name)
            finally:
                os.unlink(f.name)

    def test_output_has_all_required_chunks(self):
        metatag._write_meta(self.tmp.name, {"k": "v"})
        types = [c[0] for c in metatag._iter_chunks(self.tmp.name)]
        for required in ("IHDR", "IDAT", "IEND"):
            self.assertIn(required, types)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class CLITest(unittest.TestCase):
    def setUp(self):
        self.png = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self.png.close()
        _minimal_png(self.png.name)

    def tearDown(self):
        os.unlink(self.png.name)

    def test_read_empty(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "read", self.png.name]):
                metatag.main()
        self.assertIn("[metatag] (no metadata)", out.getvalue())

    def test_set_and_read(self):
        with patch("sys.argv", ["metatag", "set", self.png.name, "k=v"]):
            metatag.main()
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "read", self.png.name]):
                metatag.main()
        self.assertIn("k", out.getvalue())
        self.assertIn("v", out.getvalue())

    def test_set_warns_on_bad_pair(self):
        with patch("sys.stderr", new_callable=StringIO) as err:
            with patch("sys.argv", ["metatag", "set", self.png.name, "ok=v", "bad"]):
                metatag.main()
        self.assertIn("[metatag] Warning", err.getvalue())

    def test_read_single_key(self):
        metatag._write_meta(self.png.name, {"a": "1", "b": "2"})
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "read", self.png.name, "a"]):
                metatag.main()
        self.assertEqual(out.getvalue().strip(), "[metatag] 1")

    def test_read_missing_key_dies(self):
        with self.assertRaises(SystemExit):
            with patch("sys.argv", ["metatag", "read", self.png.name, "nonexistent"]):
                metatag.main()

    def test_read_raw(self):
        metatag._write_meta(self.png.name, {"a": "1", "b": "2"})
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "read", self.png.name, "--raw"]):
                metatag.main()
        lines = out.getvalue().strip().split("\n")
        self.assertIn("[metatag] a=1", lines)
        self.assertIn("[metatag] b=2", lines)

    def test_no_subcommand_dies(self):
        with self.assertRaises(SystemExit):
            with patch("sys.argv", ["metatag"]):
                metatag.main()

    def test_file_not_found_dies(self):
        with self.assertRaises(SystemExit):
            with patch("sys.argv", ["metatag", "read", "/no/such/file.png"]):
                metatag.main()

    def test_delete_nonexistent_key_warns(self):
        metatag._write_meta(self.png.name, {"x": "1"})
        with patch("sys.stderr", new_callable=StringIO) as err:
            with patch("sys.argv", ["metatag", "delete", self.png.name, "y"]):
                metatag.main()
        self.assertIn("[metatag] Warning", err.getvalue())

    def test_delete_partial_match(self):
        metatag._write_meta(self.png.name, {"a": "1", "b": "2"})
        with patch("sys.argv", ["metatag", "delete", self.png.name, "a", "c"]):
            metatag.main()
        self.assertEqual(metatag._read_meta(self.png.name), {"b": "2"})

    def test_set_from_json_file(self):
        json_path = self.png.name + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"author": "Alice", "year": 2025}, f)
        try:
            with patch("sys.argv", ["metatag", "set", self.png.name, "-f", json_path]):
                metatag.main()
            self.assertEqual(
                metatag._read_meta(self.png.name),
                {"author": "Alice", "year": "2025"},
            )
        finally:
            os.unlink(json_path)

    def test_set_json_and_pairs_merge(self):
        json_path = self.png.name + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"a": "1"}, f)
        try:
            with patch(
                "sys.argv",
                ["metatag", "set", self.png.name, "-f", json_path, "b=2"],
            ):
                metatag.main()
            self.assertEqual(metatag._read_meta(self.png.name), {"a": "1", "b": "2"})
        finally:
            os.unlink(json_path)

    def test_set_bad_json_file_dies(self):
        json_path = self.png.name + ".json"
        with open(json_path, "w") as f:
            f.write("not json")
        try:
            with self.assertRaises(SystemExit):
                with patch(
                    "sys.argv", ["metatag", "set", self.png.name, "-f", json_path]
                ):
                    metatag.main()
        finally:
            os.unlink(json_path)

    def test_read_quiet_suppresses_empty(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "read", self.png.name, "-q"]):
                metatag.main()
        self.assertEqual(out.getvalue().strip(), "")

    def test_quiet_suppresses_set_info(self):
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "set", "-q", self.png.name, "k=v"]):
                metatag.main()
        self.assertEqual(out.getvalue(), "")

    def test_quiet_suppresses_delete_info(self):
        metatag._write_meta(self.png.name, {"k": "v"})
        with patch("sys.stdout", new_callable=StringIO) as out:
            with patch("sys.argv", ["metatag", "delete", "-q", self.png.name, "k"]):
                metatag.main()
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
