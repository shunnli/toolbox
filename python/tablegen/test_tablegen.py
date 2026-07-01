import unittest

import tablegen


class TestTablegenCore(unittest.TestCase):
    def test_resolve_title(self):
        item = {"label": "err", "title": {"latex": "$e$", "plain": "error"}}
        self.assertEqual(tablegen.resolve_title(item, "latex"), "$e$")
        self.assertEqual(tablegen.resolve_title(item, "plain"), "error")
        self.assertEqual(tablegen.resolve_title({"label": "x"}, "plain"), "x")

    def test_validate_json_rejects_duplicate_label(self):
        data = {
            "data": [
                {"label": "N", "values": [1, 2]},
                {"label": "N", "values": [3, 4]},
            ]
        }
        with self.assertRaises(ValueError):
            tablegen.validate_json(data)

    def test_compute_order(self):
        ref = [1.0, 2.0, 4.0]
        val = [0.5, 0.25, 0.125]
        order = tablegen.compute_order(ref, val)
        self.assertEqual([round(x, 6) for x in order], [1.0, 1.0])

    def test_process_data_with_order_column(self):
        data = {
            "data": [
                {"label": "N", "values": [10, 20], "format": "%d"},
                {"label": "err", "values": [0.1, 0.05], "order_ref": "N"},
            ]
        }
        headers, rows = tablegen.process_data(data, output_type="plain")
        self.assertEqual(headers, ["N", "err", "order"])
        self.assertEqual(rows[0][2], "-")

    def test_transpose_table(self):
        headers = ["A", "B"]
        rows = [["1", "2"], ["3", "4"]]
        t_headers, t_rows = tablegen.transpose_table(headers, rows)
        self.assertEqual(t_headers, ["A", "1", "3"])
        self.assertEqual(t_rows, [["B", "2", "4"]])


if __name__ == "__main__":
    unittest.main()
