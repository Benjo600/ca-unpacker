from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.dump_paths import GSTR_1, GSTR_2B, GSTR_3B
GSTR_PY = ROOT / "apps" / "engine" / "parsers" / "gstr.py"


class Stage6GstrParserTests(unittest.TestCase):
    def test_dump_gstr2b_july(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        parsed = parse_gstr_file(GSTR_2B, "gstr_2b")
        self.assertEqual(len(parsed["rows"]), 1)
        row = parsed["rows"][0]
        self.assertEqual(row["document_type"], "B2B")
        self.assertEqual(row["invoice_number"], "ACME/26-27/0142")
        self.assertEqual(row["trade_name"], "Acme Traders")
        self.assertEqual(row["taxable"], 10000)
        self.assertEqual(row["match_status"], "")
        self.assertEqual(row["books_ref"], "")

    def test_gstr2b_b2b_and_cdnr(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        payload = {
            "gstin": "29ABCDE1234F1Z5",
            "rtnprd": "072026",
            "data": {
                "docdata": {
                    "b2b": [
                        {
                            "ctin": "27AAPFU0939F1ZV",
                            "trdnm": "Acme Traders",
                            "inv": [
                                {
                                    "inum": "INV-1",
                                    "dt": "01-07-2026",
                                    "val": 11800,
                                    "txval": 10000,
                                    "iamt": 0,
                                    "camt": 900,
                                    "samt": 900,
                                    "itcavl": "Y",
                                }
                            ],
                        }
                    ],
                    "cdnr": [
                        {
                            "ctin": "27AAPFU0939F1ZV",
                            "trdnm": "Acme Traders",
                            "nt": [
                                {
                                    "ntnum": "CN-9",
                                    "ntty": "C",
                                    "dt": "05-07-2026",
                                    "val": 1180,
                                    "txval": 1000,
                                    "iamt": 0,
                                    "camt": 90,
                                    "samt": 90,
                                    "itcavl": "Y",
                                }
                            ],
                        }
                    ],
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GSTR-2B_rich.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            parsed = parse_gstr_file(path, "gstr_2b")
        types = {row["document_type"] for row in parsed["rows"]}
        self.assertIn("B2B", types)
        self.assertIn("CDN", types)
        numbers = {row["invoice_number"] for row in parsed["rows"]}
        self.assertIn("INV-1", numbers)
        self.assertIn("CN-9", numbers)

    def test_dump_gstr1_july(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        parsed = parse_gstr_file(GSTR_1, "gstr_1")
        numbers = {row.get("invoice_number") for row in parsed["rows"]}
        self.assertIn("BN/101", numbers)
        hsn_rows = [
            row
            for row in parsed["rows"]
            if row.get("document_type") == "HSN" or row.get("hsn") == "9983"
        ]
        self.assertTrue(hsn_rows)
        self.assertTrue(
            any(row.get("hsn") == "9983" or row.get("invoice_number") == "9983" for row in hsn_rows)
        )
        for row in parsed["rows"]:
            self.assertEqual(row["match_status"], "")
            self.assertEqual(row["books_ref"], "")

    def test_gstr1_sums_itm_det_taxes(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        payload = {
            "gstin": "29ABCDE1234F1Z5",
            "fp": "072026",
            "b2b": [
                {
                    "ctin": "27AAPFU0939F1ZV",
                    "inv": [
                        {
                            "inum": "TX/1",
                            "idt": "01-07-2026",
                            "val": 23600,
                            "itms": [
                                {
                                    "num": 1,
                                    "itm_det": {"txval": 10000, "iamt": 1800, "camt": 0, "samt": 0, "csamt": 0},
                                },
                                {
                                    "num": 2,
                                    "itm_det": {"txval": 10000, "iamt": 0, "camt": 900, "samt": 900, "csamt": 10},
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GSTR1_itms.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            parsed = parse_gstr_file(path, "gstr_1")
        row = next(item for item in parsed["rows"] if item["invoice_number"] == "TX/1")
        self.assertEqual(row["igst"], 1800)
        self.assertEqual(row["cgst"], 900)
        self.assertEqual(row["sgst"], 900)
        self.assertEqual(row["cess"], 10)
        self.assertEqual(row["taxable"], 20000)

    def test_dump_gstr3b_july(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        parsed = parse_gstr_file(GSTR_3B, "gstr_3b")
        self.assertTrue(any(row.get("taxable") == 50000 for row in parsed["rows"]))

    def test_broken_json_returns_empty(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{not valid json", encoding="utf-8")
            parsed = parse_gstr_file(path, "gstr_2b")
        self.assertEqual(parsed["rows"], [])
        self.assertEqual(parsed["error"], "not valid JSON")
        self.assertEqual(parsed["kind"], "gstr_2b")

    def test_parser_is_offline(self) -> None:
        source = GSTR_PY.read_text(encoding="utf-8")
        self.assertNotIn("http://", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source)


if __name__ == "__main__":
    unittest.main()
