from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _pack(folder: Path) -> dict:
    return {
        "id": 1,
        "period_id": 1,
        "path": str(folder),
        "exists": True,
        "outputs": [],
        "files": [],
        "recon": {
            "counts": {
                "matched": 1,
                "books_only": 0,
                "portal_only": 0,
                "amount_mismatch": 0,
                "likely": 0,
                "tax_mismatch": 0,
                "duplicate": 0,
                "split_merged": 0,
                "credit_note": 0,
            },
            "totals": {
                "portal_total": 100.0,
                "books_total": 100.0,
                "gap": 0.0,
                "credit_at_risk": 0.0,
                "unsupported_credit": 0.0,
                "credit_note_total": 0.0,
            },
            "tolerances": {"days": 0, "amount": 1.0},
            "decisions": {"counts": {}, "money": {}, "by_reason": {}},
            "rows": [
                {
                    "status": "books_only",
                    "reason": "Only in books",
                    "party": "Acme",
                    "gstin": "27AAPFU0939F1ZV",
                    "invoice_books": "INV/1",
                    "amount_books": 100.0,
                    "decision": "accepted",
                    "decision_label": "Accepted",
                    "decision_by": "Test firm",
                    "decision_at": "2026-11-03T10:00:00+00:00",
                }
            ],
        },
    }


class ReconExportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Export firm")
        client = create_client("Export client")
        self.period = create_period(client["id"], "Jul 2026")
        self.folder = Path(self._tmp.name) / "pack"
        self.folder.mkdir()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original

    def test_exceptions_export_writes_into_the_pack_folder(self) -> None:
        from apps.desktop.app import DesktopApi

        with patch("apps.desktop.app.get_period_pack", return_value=_pack(self.folder)), patch(
            "apps.desktop.app._open_path"
        ) as opener:
            result = DesktopApi().export_recon_exceptions(self.period["id"])

        self.assertTrue(result["ok"], result)
        path = Path(result["path"])
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.parent, self.folder)
        self.assertEqual(path.name, "Exceptions_Only.xlsx")
        opener.assert_called_once()

    def test_summary_export_writes_into_the_pack_folder(self) -> None:
        from apps.desktop.app import DesktopApi

        with patch("apps.desktop.app.get_period_pack", return_value=_pack(self.folder)), patch(
            "apps.desktop.app._open_path"
        ):
            result = DesktopApi().export_recon_audit_summary(self.period["id"])

        self.assertTrue(result["ok"], result)
        self.assertEqual(Path(result["path"]).name, "Reconciliation_Summary.xlsx")
        self.assertTrue(Path(result["path"]).is_file())

    def test_export_without_a_reconciliation_is_friendly(self) -> None:
        from apps.desktop.app import DesktopApi

        with patch("apps.desktop.app.get_period_pack", return_value=None), patch(
            "apps.desktop.app._open_path"
        ) as opener:
            result = DesktopApi().export_recon_exceptions(self.period["id"])

        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])
        opener.assert_not_called()

    def test_unknown_period_is_friendly(self) -> None:
        from apps.desktop.app import DesktopApi

        result = DesktopApi().export_recon_audit_summary(999999)
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
