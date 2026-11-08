from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class VendorStatementParserTests(unittest.TestCase):
    def test_vendor_statement_xlsx_is_classified_and_parsed(self) -> None:
        from apps.engine.classifier import classify_path
        from apps.engine.parsers.vendor_statement import parse_vendor_statement_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Acme_Vendor_Statement_Jul2026.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.append(["Vendor statement", "Acme Traders"])
            sheet.append(["Invoice No", "Date", "Party Name", "Debit", "Credit", "Balance", "Narration"])
            sheet.append(["INV/001", "12-07-2026", "Acme Traders", 11800, 0, 111800, "July purchase"])
            sheet.append(["INV/002", "14-07-2026", "Acme Traders", 0, 5900, 105900, "Credit note"])
            book.save(path)

            classification = classify_path(path)
            self.assertEqual(classification.kind, "vendor_statement")
            parsed = parse_vendor_statement_file(path)
            self.assertEqual(len(parsed["rows"]), 2)
            first = parsed["rows"][0]
            self.assertEqual(first["invoice_number"], "INV/001")
            self.assertEqual(first["party_name"], "Acme Traders")
            self.assertEqual(first["invoice_value"], 11800)
            self.assertEqual(first["invoice_date"], "2026-07-12")


if __name__ == "__main__":
    unittest.main()
