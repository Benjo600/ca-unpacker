"""Approval decisions on inferred rows must survive a pack rebuild."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook


def _inferred_row() -> dict:
    return {
        "date": "2026-07-05",
        "description": "Inferred from the balance gap — not in the statement",
        "cheque_ref": None,
        "debit": 3800.0,
        "credit": None,
        "balance": 211.71,
        "source_page": 1,
        "source_bbox": "0,0,1,1",
        "source": "statement.pdf#p1@0,0,1,1",
        "raw_text": "",
        "flags": ["inferred_from_balance"],
        "needs_approval": True,
        "approval": "pending",
    }


class RowKeyTests(unittest.TestCase):
    def test_key_ignores_unrelated_fields_and_keeps_the_money(self) -> None:
        from apps.engine.row_approvals import row_key

        row = _inferred_row()
        same = dict(row, raw_text="changed", approval="approved", source_page=9)
        other = dict(row, debit=3900.0)

        self.assertEqual(row_key(7, "bank", row), row_key(7, "bank", same))
        self.assertNotEqual(row_key(7, "bank", row), row_key(7, "bank", other))
        self.assertNotEqual(row_key(7, "bank", row), row_key(8, "bank", row))

    def test_key_fits_the_column(self) -> None:
        from apps.engine.row_approvals import row_key

        row = _inferred_row()
        row["description"] = "x" * 400
        self.assertLessEqual(len(row_key(1, "bank", row)), 320)


class ApprovedRowsLeaveTheApprovalSheetTests(unittest.TestCase):
    def _files(self, row: dict) -> list[dict]:
        return [
            {
                "file_id": 1,
                "kind": "bank",
                "meta": {"filename": "statement.pdf"},
                "rows": [row],
                "currency": {"code": "INR", "source": "stated"},
                "check": {
                    "status": "unverified",
                    "row_count": 1,
                    "opening_balance": None,
                    "stated_closing": None,
                    "computed_closing": None,
                    "broken_at_row": None,
                    "flags": [],
                },
            }
        ]

    def test_approved_row_is_not_reported_as_pending(self) -> None:
        from apps.engine.pack.bank_xlsx import _pending_approval_rows

        row = _inferred_row()
        self.assertEqual(len(_pending_approval_rows([row])), 1)
        row["approval"] = "approved"
        self.assertEqual(_pending_approval_rows([row]), [])

    def test_pack_has_no_approval_sheet_once_approved(self) -> None:
        from apps.engine.pack.bank_xlsx import write_bank_workbook

        row = _inferred_row()
        row["approval"] = "approved"
        with tempfile.TemporaryDirectory() as folder:
            path = write_bank_workbook(Path(folder) / "pack.xlsx", self._files(row))
            book = load_workbook(path)
            self.assertEqual([n for n in book.sheetnames if "approve" in n.lower()], [])


class DecisionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        import os
        from apps.engine.db import reset_engine

        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        reset_engine()
        from apps.engine.clients import create_client
        from apps.engine.dump import start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        self.client = create_client("Acme")
        self.period = create_period(self.client["id"], "Jul 2026")
        self.job = start_job(self.period["id"])

    def tearDown(self) -> None:
        import os
        from apps.engine.db import reset_engine

        reset_engine()
        if self._old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old
        self._tmp.cleanup()

    def _store_row(self, row: dict) -> int:
        import json

        from apps.engine.db import ExtractedRow, StoredFile, get_session

        session = get_session()
        try:
            stored = StoredFile(
                job_id=self.job["id"],
                period_id=self.period["id"],
                original_name="statement.pdf",
                storage_key="files/statement.pdf",
                detected_kind="bank",
            )
            session.add(stored)
            session.commit()
            session.refresh(stored)
            extracted = ExtractedRow(
                file_id=stored.id,
                period_id=self.period["id"],
                kind="bank",
                payload_json=json.dumps(row),
                source_page=1,
                source_bbox="0,0,1,1",
                validation_flags=json.dumps(row.get("flags") or []),
            )
            session.add(extracted)
            session.commit()
            session.refresh(extracted)
            return extracted.id
        finally:
            session.close()

    def test_approving_a_stored_row_is_remembered(self) -> None:
        from apps.engine.row_approvals import decide_row, decisions_for

        row = _inferred_row()
        row_id = self._store_row(row)
        result = decide_row(row_id, "approved")

        self.assertTrue(result["ok"])
        self.assertEqual(decisions_for(self.period["id"]).get(result["row_key"]), "approved")

    def test_decision_applies_to_the_rebuilt_row(self) -> None:
        from apps.engine.row_approvals import apply_decisions, decide_row

        row_id = self._store_row(_inferred_row())
        decide_row(row_id, "approved")
        stored_file_id = self._file_id()

        # The pack is rebuilt from scratch, so the decision has to be matched to
        # the fresh row by fingerprint, not by database id.
        files = [{"file_id": stored_file_id, "kind": "bank", "rows": [_inferred_row()]}]
        self.assertEqual(apply_decisions(self.period["id"], files), 1)
        self.assertEqual(files[0]["rows"][0]["approval"], "approved")

    def test_a_different_file_is_not_approved_by_a_neighbouring_decision(self) -> None:
        from apps.engine.row_approvals import apply_decisions, decide_row

        row_id = self._store_row(_inferred_row())
        decide_row(row_id, "approved")
        other_file = [{"file_id": self._file_id() + 999, "kind": "bank", "rows": [_inferred_row()]}]
        self.assertEqual(apply_decisions(self.period["id"], other_file), 0)
        self.assertEqual(other_file[0]["rows"][0]["approval"], "pending")

    def test_unknown_decision_is_refused(self) -> None:
        from apps.engine.row_approvals import set_decision

        with self.assertRaises(ValueError):
            set_decision(self.period["id"], "some-key", "maybe")

    def _file_id(self) -> int:
        from apps.engine.db import StoredFile, get_session

        session = get_session()
        try:
            stored = session.query(StoredFile).first()
            return stored.id
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
