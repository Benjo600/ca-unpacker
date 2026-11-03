"""Step 1 gate: decisions are saved, survive a re-run, and new rows are flagged.

The plan says: decide the problem rows, run the same month again, every
decision must still be there unchanged, the rupee figures must not move, and
only genuinely new rows may be marked new.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.fixtures_stage5 import GOOD_GSTIN, invoice_lines, write_invoice_pdf

MATCH_INV = "GATE/26-27/0101"
MISMATCH_INV = "GATE/26-27/0102"
PORTAL_INV = "PORTAL-ONLY-GATE"
NEW_INV = "PORTAL-NEW-GATE"


def _gstr2b_json(path: Path, invoices: list[dict]) -> Path:
    import json

    payload = {
        "gstin": "29ABCDE1234F1Z5",
        "rtnprd": "072026",
        "data": {
            "docdata": {
                "b2b": [
                    {
                        "ctin": inv.get("gstin", GOOD_GSTIN),
                        "trdnm": "Gate Traders",
                        "inv": [
                            {
                                "inum": inv["inum"],
                                "dt": inv.get("dt", "12-07-2026"),
                                "val": inv["val"],
                                "txval": 10000,
                                "iamt": 0,
                                "camt": 900,
                                "samt": 900,
                            }
                        ],
                    }
                    for inv in invoices
                ]
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _IsolatedApp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()
        self.inbox = Path(self._tmp.name) / "inbox"
        self.inbox.mkdir()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _period(self) -> dict:
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Gate firm")
        client = create_client("Gate client")
        return create_period(client["id"], "Jul 2026")

    def _bill(self, name: str, invoice_no: str, total: str) -> Path:
        return write_invoice_pdf(
            self.inbox / name,
            invoice_lines(
                invoice_no=invoice_no,
                date="12/07/2026",
                taxable="10000.00",
                cgst="900.00",
                sgst="900.00",
                total=total,
            ),
        )

    def _first_dump(self) -> tuple[dict, dict]:
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.pipeline import get_period_pack

        period = self._period()
        bill_match = self._bill("bill_match.pdf", MATCH_INV, "11800.00")
        bill_mismatch = self._bill("bill_mismatch.pdf", MISMATCH_INV, "11800.00")
        gstr = _gstr2b_json(
            self.inbox / "GSTR-2B_gate.json",
            [
                {"inum": MATCH_INV, "val": 11800},
                {"inum": MISMATCH_INV, "val": 11850},
                {"inum": PORTAL_INV, "val": 5900, "dt": "20-07-2026"},
            ],
        )
        job = start_job(period["id"])
        result = ingest_paths(job["id"], [str(bill_match), str(bill_mismatch), str(gstr)])
        self.assertNotEqual(result.get("status"), "failed", result)
        pack = get_period_pack(period["id"])
        self.assertIsNotNone(pack)
        return period, pack


class ReconDecisionMemoryGateTests(_IsolatedApp):
    def test_decisions_survive_a_rerun_and_only_new_rows_are_flagged(self) -> None:
        from apps.engine.dump import ingest_paths, reparse_period, start_job
        from apps.engine.pipeline import get_period_pack

        period, pack = self._first_dump()
        recon = pack["recon"]
        rows = recon["rows"]
        exceptions = {row["row_key"]: row for row in rows if row.get("needs_decision")}
        self.assertEqual(len(exceptions), 2, [(r["status"], r["row_key"]) for r in rows])
        by_status = {row["status"]: row for row in exceptions.values()}
        mismatch = by_status["amount_mismatch"]
        portal = by_status["portal_only"]

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        saved_pack = api.set_recon_decision(
            period["id"],
            mismatch["row_key"],
            "rejected",
            reason_code="rate_difference",
            note="Chasing the supplier for the ₹50",
        )
        self.assertTrue(saved_pack["ok"], saved_pack)
        # The row must show the decision immediately, without re-running the month.
        immediate = {
            row["row_key"]: row for row in (saved_pack["pack"] or {}).get("recon", {}).get("rows", [])
        }
        self.assertEqual(immediate[mismatch["row_key"]]["decision"], "rejected")
        self.assertEqual(immediate[mismatch["row_key"]]["decision_reason"], "Rate difference")

        noted = api.set_recon_decision(
            period["id"],
            portal["row_key"],
            "noted",
            reason_code="supplier_not_filed",
        )
        self.assertTrue(noted["ok"], noted)

        counts_before = dict(recon["counts"])
        totals_before = dict(recon["totals"])

        reparse_period(period["id"])
        pack2 = get_period_pack(period["id"])
        assert pack2 is not None
        recon2 = pack2["recon"]

        self.assertEqual(recon2["counts"], counts_before)
        self.assertEqual(recon2["totals"], totals_before)

        rows2 = {row["row_key"]: row for row in recon2["rows"]}
        kept = rows2[mismatch["row_key"]]
        self.assertEqual(kept["decision"], "rejected")
        self.assertEqual(kept["decision_reason"], "Rate difference")
        self.assertEqual(kept["decision_note"], "Chasing the supplier for the ₹50")
        self.assertEqual(kept["decision_by"], "Gate firm")
        self.assertTrue(kept["decision_at"])
        self.assertEqual(rows2[portal["row_key"]]["decision"], "noted")

        summary = recon2["decisions"]
        self.assertEqual(summary["counts"]["rejected"], 1)
        self.assertEqual(summary["counts"]["noted"], 1)
        self.assertEqual(summary["counts"]["undecided"], 0)
        self.assertEqual(summary["counts"]["new"], 0)
        self.assertFalse(any(row.get("is_new") for row in recon2["rows"]))

        extra = _gstr2b_json(
            self.inbox / "GSTR-2B_gate_extra.json", [{"inum": NEW_INV, "val": 2360, "dt": "22-07-2026"}]
        )
        job = start_job(period["id"])
        result = ingest_paths(job["id"], [str(extra)])
        self.assertNotEqual(result.get("status"), "failed", result)

        pack3 = get_period_pack(period["id"])
        assert pack3 is not None
        recon3 = pack3["recon"]
        rows3 = {row["row_key"]: row for row in recon3["rows"]}

        self.assertEqual(rows3[mismatch["row_key"]]["decision"], "rejected")
        self.assertEqual(rows3[portal["row_key"]]["decision"], "noted")
        new_rows = [row for row in recon3["rows"] if row.get("is_new")]
        self.assertEqual(len(new_rows), 1, [(r["status"], r["invoice_2b"]) for r in recon3["rows"]])
        self.assertEqual(new_rows[0]["invoice_2b"], NEW_INV)
        self.assertEqual(new_rows[0]["decision"], "")
        self.assertEqual(recon3["decisions"]["counts"]["new"], 1)
        self.assertEqual(recon3["decisions"]["counts"]["undecided"], 1)

    def test_master_excel_shows_the_decision_and_cover_counts(self) -> None:
        from openpyxl import load_workbook

        from apps.engine import decisions
        from apps.engine.db import get_session
        from apps.engine.pipeline import get_period_pack

        period, pack = self._first_dump()
        rows = [row for row in pack["recon"]["rows"] if row.get("needs_decision")]
        session = get_session()
        try:
            for row in rows:
                decisions.save(
                    session,
                    period["id"],
                    row["row_key"],
                    "accepted",
                    reason_code="credit_note_pending",
                    decided_by="Gate firm",
                )
            session.commit()
        finally:
            session.close()

        from apps.engine.dump import reparse_period

        reparse_period(period["id"])
        pack2 = get_period_pack(period["id"])
        assert pack2 is not None
        path = Path(pack2["path"]) / "Master_Reconciliation_Grid.xlsx"
        self.assertTrue(path.is_file(), path)
        book = load_workbook(path, data_only=True)
        grid = book["Grid"]
        headers = [str(cell.value or "") for cell in grid[1]]
        self.assertEqual(headers[headers.index("Why") + 1 : headers.index("Why") + 6], [
            "Decision",
            "Reason",
            "Note",
            "Decided by",
            "Decided on",
        ])
        decision_values = {
            str(grid.cell(row=index, column=headers.index("Decision") + 1).value or "")
            for index in range(2, grid.max_row + 1)
        }
        self.assertIn("Accepted", decision_values)
        cover = {
            str(cover_row[0] or "").strip(): cover_row[1]
            for cover_row in book["Cover"].iter_rows(values_only=True)
            if cover_row and cover_row[0]
        }
        self.assertEqual(cover.get("Rows accepted"), 2)
        self.assertEqual(cover.get("Still to decide"), 0)


if __name__ == "__main__":
    unittest.main()
