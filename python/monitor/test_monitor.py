import sys
import unittest
from unittest.mock import patch

import monitor


class TestMonitorHelpers(unittest.TestCase):
    def test_color_wrappers(self):
        self.assertIn("ok", monitor.active_msg("ok"))
        self.assertIn("err", monitor.err_msg("err"))
        self.assertIn("info", monitor.info_msg("info"))
        self.assertIn("warn", monitor.warn_msg("warn"))

    def test_format_size(self):
        self.assertEqual(monitor.format_size(100), "100 B")
        self.assertEqual(monitor.format_size(2048), "2.00 KB")

    @patch.object(sys, "argv", ["monitor", "a.log", "-i", "0.5", "--idle-timeout", "3"])
    def test_parse_args(self):
        args = monitor.parse_args()
        self.assertEqual(args.path, ["a.log"])
        self.assertEqual(args.interval, 0.5)
        self.assertEqual(args.idle_timeout, 3)

    @patch("monitor.os.name", "nt")
    def test_read_key_nonblocking_windows_no_hit(self):
        with patch.dict(
            sys.modules, {"msvcrt": type("M", (), {"kbhit": lambda: False})}
        ):
            self.assertIsNone(monitor.read_key_nonblocking())

    @patch("monitor.os.name", "posix")
    def test_read_key_nonblocking_posix_no_input(self):
        fake_select = type("S", (), {"select": staticmethod(lambda *_: ([], [], []))})
        with patch.dict(sys.modules, {"select": fake_select}):
            self.assertIsNone(monitor.read_key_nonblocking())


if __name__ == "__main__":
    unittest.main()
