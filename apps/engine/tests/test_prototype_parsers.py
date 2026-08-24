from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DUMP = ROOT / "test-dump"


class GstrTallyZohoTests(unittest.TestCase):
    def test_gstr2b(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        parsed = parse_gstr_file(DUMP / "GSTR-2B_July.json", "gstr_2b")
        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(parsed["rows"][0]["invoice_number"], "ACME/26-27/0142")

    def test_gstr1_and_3b(self) -> None:
        from apps.engine.parsers.gstr import parse_gstr_file

        one = parse_gstr_file(DUMP / "GSTR1_July.json", "gstr_1")
        three = parse_gstr_file(DUMP / "GSTR3B_July.json", "gstr_3b")
        self.assertGreaterEqual(len(one["rows"]), 1)
        self.assertGreaterEqual(len(three["rows"]), 1)

    def test_tally_xml_and_zip(self) -> None:
        from apps.engine.parsers.tally import parse_tally_file

        xml = parse_tally_file(DUMP / "Tally_Daybook.xml")
        zipped = parse_tally_file(DUMP / "Tally_Backup.zip")
        self.assertEqual(xml["rows"][0]["voucher_number"], "PUR-88")
        self.assertEqual(zipped["rows"][0]["party_name"], "Acme Traders")

    def test_zoho_csv(self) -> None:
        from apps.engine.parsers.zoho import parse_zoho_file

        parsed = parse_zoho_file(DUMP / "Zoho_Books_Invoices.csv")
        self.assertEqual(parsed["rows"][0]["invoice_number"], "INV-204")

    def test_invoice_pdf(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file
        from apps.engine.tests.fixtures_stage5 import invoice_lines, write_invoice_pdf

        with tempfile.TemporaryDirectory() as tmp:
            path = write_invoice_pdf(Path(tmp) / "Tax_Invoice_Acme.pdf", invoice_lines(invoice_no="ACME/26-27/0142"))
            parsed = parse_invoice_file(path)
        self.assertFalse(parsed["unreadable"])
        row = parsed["rows"][0]
        self.assertTrue(row["supplier_gstin"])
        self.assertTrue(row["invoice_number"])
        self.assertGreaterEqual(len(parsed.get("line_items") or []), 1)


class MixedDumpPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_mixed_test_dump_writes_several_excels(self) -> None:
        from apps.engine.clients import create_client
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period
        from apps.engine.pipeline import get_period_pack

        save_firm("Test firm")
        client = create_client("Acme")
        period = create_period(client["id"], "Jul 2026")
        job = start_job(period["id"])
        mixed = [
            DUMP / "HDFC_Statement_Jul2026.pdf",
            DUMP / "Tax_Invoice_Acme.pdf",
            DUMP / "GSTR-2B_July.json",
            DUMP / "GSTR1_July.json",
            DUMP / "GSTR3B_July.json",
            DUMP / "Tally_Daybook.xml",
            DUMP / "Zoho_Books_Invoices.csv",
        ]
        ingest_paths(job["id"], [str(path) for path in mixed])
        pack = get_period_pack(period["id"])
        self.assertIsNotNone(pack)
        keys = {item["key"] for item in pack["outputs"]}
        self.assertIn("bank", keys)
        self.assertIn("purchase", keys)
        self.assertIn("gstr_2b", keys)
        self.assertIn("gstr_1", keys)
        self.assertIn("gstr_3b", keys)
        self.assertIn("books", keys)
        self.assertIn("sales", keys)
        for item in pack["outputs"]:
            self.assertTrue(Path(item["path"]).exists(), item["label"])


if __name__ == "__main__":
    unittest.main()
