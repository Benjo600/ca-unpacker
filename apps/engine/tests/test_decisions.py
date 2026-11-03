from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "29ABCDE1234F1Z5"


def _row(
    status: str,
    invoice: str,
    amount: float,
    gstin: str = GSTIN,
    party: str = "Acme Traders",
    when: str = "2026-07-12",
) -> dict:
    return {
        "status": status,
        "gstin": gstin,
        "party": party,
        "invoice_books": invoice,
        "invoice_2b": invoice,
        "date_books": when,
        "date_2b": when,
        "amount_books": amount,
        "amount_2b": amount,
    }


class DecisionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Mehta & Associates")
        client = create_client("Acme Traders", GSTIN)
        self.period = create_period(client["id"], "Jul 2026")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    # ---- store -------------------------------------------------------

    def test_save_then_load_keeps_reason_note_by_and_time(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import get_session

        session = get_session()
        try:
            stored = decisions.save(
                session,
                self.period["id"],
                f"{GSTIN}|INV-1",
                decisions.DECISION_ACCEPTED,
                reason_code="rate_difference",
                note="Agreed with the supplier over the phone.",
                decided_by="Mehta & Associates",
            )
            session.commit()
            self.assertEqual(stored["decision"], "accepted")
            self.assertEqual(stored["reason_label"], "Rate difference")
            self.assertTrue(stored["decided_at"])

            loaded = decisions.load(session, self.period["id"])
        finally:
            session.close()

        record = loaded[f"{GSTIN}|INV-1"]
        self.assertEqual(record["decision"], "accepted")
        self.assertEqual(record["reason_code"], "rate_difference")
        self.assertEqual(record["reason_label"], "Rate difference")
        self.assertEqual(record["note"], "Agreed with the supplier over the phone.")
        self.assertEqual(record["decided_by"], "Mehta & Associates")
        self.assertTrue(record["decided_at"])
        self.assertTrue(record["first_seen_at"])

    def test_saving_same_row_twice_updates_instead_of_duplicating(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import ReconDecision, get_session

        session = get_session()
        try:
            key = f"{GSTIN}|INV-2"
            decisions.save(session, self.period["id"], key, decisions.DECISION_ACCEPTED)
            session.commit()
            decisions.save(
                session,
                self.period["id"],
                key,
                decisions.DECISION_REJECTED,
                reason_code="supplier_not_filed",
                note="Waiting on the supplier.",
                decided_by="Mehta & Associates",
            )
            session.commit()

            rows = (
                session.query(ReconDecision)
                .filter(ReconDecision.period_id == self.period["id"])
                .all()
            )
            self.assertEqual(len(rows), 1)
            loaded = decisions.load(session, self.period["id"])
        finally:
            session.close()

        record = loaded[key]
        self.assertEqual(record["decision"], "rejected")
        self.assertEqual(record["reason_code"], "supplier_not_filed")
        self.assertEqual(record["note"], "Waiting on the supplier.")

    def test_empty_decision_clears_the_saved_choice(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import get_session

        key = f"{GSTIN}|INV-3"
        session = get_session()
        try:
            decisions.save(
                session,
                self.period["id"],
                key,
                decisions.DECISION_NOTED,
                reason_code="other",
                note="Chase later.",
                decided_by="Mehta & Associates",
            )
            session.commit()
            cleared = decisions.save(session, self.period["id"], key, "")
            session.commit()
            loaded = decisions.load(session, self.period["id"])
        finally:
            session.close()

        self.assertEqual(cleared["decision"], "")
        record = loaded[key]
        self.assertEqual(record["decision"], "")
        self.assertEqual(record["reason_code"], "")
        self.assertEqual(record["note"], "")
        self.assertEqual(record["decided_by"], "")
        self.assertEqual(record["decided_at"], "")

    def test_unknown_reason_code_is_refused(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import get_session

        session = get_session()
        try:
            with self.assertRaises(ValueError):
                decisions.save(
                    session,
                    self.period["id"],
                    f"{GSTIN}|INV-4",
                    decisions.DECISION_ACCEPTED,
                    reason_code="because i said so",
                )
        finally:
            session.close()

    def test_unknown_decision_is_refused(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import get_session

        session = get_session()
        try:
            with self.assertRaises(ValueError):
                decisions.save(
                    session, self.period["id"], f"{GSTIN}|INV-5", "maybe"
                )
        finally:
            session.close()

    # ---- remember ----------------------------------------------------

    def test_remember_reports_new_keys_once_only(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import get_session

        keys = [f"{GSTIN}|A", f"{GSTIN}|B"]
        session = get_session()
        try:
            first = decisions.remember(session, self.period["id"], keys)
            session.commit()
            second = decisions.remember(session, self.period["id"], keys)
            session.commit()
        finally:
            session.close()

        self.assertEqual(first, set(keys))
        self.assertEqual(second, set())

    def test_keys_that_vanish_then_return_are_not_new_again(self) -> None:
        from apps.engine import decisions
        from apps.engine.db import get_session

        a, b = f"{GSTIN}|A", f"{GSTIN}|B"
        session = get_session()
        try:
            decisions.remember(session, self.period["id"], [a, b])
            session.commit()
            # Only one row comes back this run: nothing new.
            only_a = decisions.remember(session, self.period["id"], [a])
            session.commit()
            # The missing row returns in a later run: still not new.
            back = decisions.remember(session, self.period["id"], [a, b])
            session.commit()
        finally:
            session.close()

        self.assertEqual(only_a, set())
        self.assertEqual(back, set())

    # ---- apply + summarize -------------------------------------------

    def _sample_rows(self) -> list[dict]:
        return [
            _row("matched", "M-0", 1180.0),
            _row("books_only", "B-1", 1000.0),
            _row("portal_only", "P-1", 2000.0),
            _row("amount_mismatch", "A-1", 3000.0),
            _row("likely", "L-1", 4000.0),
        ]

    def _saved_for(self, rows: list[dict]) -> dict[str, dict]:
        from apps.engine import decisions

        keys = decisions.row_keys(rows)
        return {
            keys[1]: {
                "decision": "accepted",
                "reason_code": "rate_difference",
                "reason_label": "Rate difference",
                "note": "ok",
                "decided_by": "Mehta & Associates",
                "decided_at": "2026-07-20T10:00:00",
            },
            keys[2]: {"decision": "rejected", "reason_label": ""},
            keys[3]: {"decision": "noted", "reason_code": "other"},
        }

    def test_apply_attaches_decisions_and_summary_counts_exceptions(self) -> None:
        from apps.engine import decisions

        rows = self._sample_rows()
        saved = self._saved_for(rows)
        keys = decisions.row_keys(rows)
        summary = decisions.apply(rows, saved, {keys[4]})

        self.assertEqual(summary["counts"]["exceptions"], 4)
        self.assertEqual(summary["counts"]["accepted"], 1)
        self.assertEqual(summary["counts"]["rejected"], 1)
        self.assertEqual(summary["counts"]["noted"], 1)
        self.assertEqual(summary["counts"]["undecided"], 1)
        self.assertEqual(summary["counts"]["new"], 1)
        self.assertAlmostEqual(summary["money"]["at_stake"], 10000.0)
        self.assertAlmostEqual(summary["money"]["accepted"], 1000.0)
        self.assertAlmostEqual(summary["money"]["rejected"], 2000.0)
        self.assertAlmostEqual(summary["money"]["noted"], 3000.0)
        self.assertAlmostEqual(summary["money"]["undecided"], 4000.0)
        self.assertEqual(summary["by_reason"].get("other"), 1)

        # The matched row is ignored, not counted.
        self.assertFalse(rows[0]["needs_decision"])
        self.assertEqual(rows[0]["decision"], "")
        # Every row still carries its own identity and decision fields.
        self.assertEqual(rows[0]["row_key"], keys[0])
        self.assertEqual(rows[1]["decision"], "accepted")
        self.assertEqual(rows[1]["decision_label"], "Accepted")
        self.assertEqual(rows[1]["decision_reason"], "Rate difference")
        self.assertEqual(rows[1]["decision_note"], "ok")
        self.assertEqual(rows[1]["decision_by"], "Mehta & Associates")
        self.assertTrue(rows[1]["needs_decision"])
        self.assertFalse(rows[1]["is_new"])
        self.assertTrue(rows[4]["is_new"])
        self.assertEqual(rows[4]["decision_label"], "Not decided")

    def test_duplicate_invoices_get_numbered_keys(self) -> None:
        from apps.engine import decisions

        rows = [_row("books_only", "DUP-1", 500.0), _row("books_only", "DUP-1", 500.0)]
        keys = decisions.row_keys(rows)

        single = decisions.row_keys([_row("books_only", "DUP-1", 500.0)])[0]
        self.assertEqual(keys[0], single)
        self.assertEqual(keys[1], f"{single}#1")
        self.assertTrue(keys[0].startswith(GSTIN))
        self.assertTrue(keys[0].endswith("DUP1"))

        decisions.apply(rows, {}, set())
        self.assertEqual(rows[0]["row_key"], keys[0])
        self.assertEqual(rows[1]["row_key"], keys[1])

    def test_row_key_survives_a_status_change_between_runs(self) -> None:
        from apps.engine import decisions

        before = [_row("books_only", "STABLE-1", 1180.0)]
        after = [_row("matched", "STABLE-1", 1180.0)]

        self.assertEqual(decisions.row_keys(before), decisions.row_keys(after))
        key = decisions.row_keys(before)[0]
        self.assertTrue(key.startswith(GSTIN))
        self.assertTrue(key.endswith("STABLE1"))
        self.assertNotEqual(key, "")


if __name__ == "__main__":
    unittest.main()
