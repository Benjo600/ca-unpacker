from __future__ import annotations

import ast
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.dump_paths import TALLY_XML, TALLY_ZIP
TALLY_PY = ROOT / "apps" / "engine" / "parsers" / "tally.py"

SALES_XML = """<?xml version="1.0"?>
<ENVELOPE>
 <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
 <BODY>
  <TALLYMESSAGE>
   <VOUCHER VCHTYPE="Sales">
    <DATE>20260715</DATE>
    <VOUCHERNUMBER>SAL-10</VOUCHERNUMBER>
    <PARTYLEDGERNAME>North Retail</PARTYLEDGERNAME>
    <AMOUNT>5900.00</AMOUNT>
   </VOUCHER>
  </TALLYMESSAGE>
 </BODY>
</ENVELOPE>
"""


class Stage7TallyParserTests(unittest.TestCase):
    def test_daybook_pur88_purchase_register(self) -> None:
        from apps.engine.parsers.tally import parse_tally_file

        parsed = parse_tally_file(TALLY_XML)
        self.assertEqual(len(parsed["rows"]), 1)
        row = parsed["rows"][0]
        self.assertEqual(row["register"], "purchase")
        self.assertEqual(row["invoice_number"], "PUR-88")
        self.assertEqual(row["supplier_name"], "Acme Traders")
        self.assertEqual(row["party_name"], "Acme Traders")
        self.assertEqual(row["invoice_value"], 11800)
        self.assertEqual(row["voucher_number"], "PUR-88")
        self.assertEqual(row["invoice_date"], "2026-07-12")

    def test_generated_sales_voucher_sal10(self) -> None:
        from apps.engine.parsers.tally import parse_tally_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sales.xml"
            path.write_text(SALES_XML, encoding="utf-8")
            parsed = parse_tally_file(path)
        self.assertEqual(len(parsed["rows"]), 1)
        row = parsed["rows"][0]
        self.assertEqual(row["register"], "sales")
        self.assertEqual(row["invoice_number"], "SAL-10")
        self.assertEqual(row["voucher_number"], "SAL-10")

    def test_zip_still_works(self) -> None:
        from apps.engine.parsers.tally import parse_tally_file

        parsed = parse_tally_file(TALLY_ZIP)
        self.assertGreaterEqual(len(parsed["rows"]), 1)
        row = parsed["rows"][0]
        self.assertEqual(row["invoice_number"], "PUR-88")
        self.assertEqual(row["party_name"], "Acme Traders")
        self.assertEqual(row["register"], "purchase")

    def test_garbage_zip_is_empty_not_an_exception(self) -> None:
        from apps.engine.parsers.tally import parse_tally_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "junk.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("hello.txt", "hello")
            parsed = parse_tally_file(path)
        self.assertEqual(parsed["rows"], [])

    def test_truncated_xml_is_empty_not_an_exception(self) -> None:
        from apps.engine.parsers.tally import parse_tally_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.xml"
            path.write_text("<?xml version='1.0'?><ENVELOPE><VOUCHER>", encoding="utf-8")
            parsed = parse_tally_file(path)
        self.assertEqual(parsed["rows"], [])

    def test_no_pyodbc_win32com_or_requests(self) -> None:
        source = TALLY_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        for banned in ("pyodbc", "win32com", "requests"):
            self.assertNotIn(banned, imported)
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
