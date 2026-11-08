from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"
OTHER_GSTIN = "29ABCDE1234F1Z5"


def invoice(**overrides):
    row = {
        "supplier_gstin": GSTIN,
        "invoice_number": "INV/001",
        "invoice_date": "2026-07-12",
        "taxable_value": 1000,
        "igst": 180,
        "invoice_value": 1180,
        "supplier_name": "Acme Traders",
        "currency": "INR",
        "source": "bill.pdf",
    }
    row.update(overrides)
    return row


def register(**overrides):
    row = {
        "gstin": GSTIN,
        "invoice_number": "INV-1",
        "invoice_date": "2026-07-12",
        "taxable_value": 1000,
        "igst": 180,
        "amount": 1180,
        "party_name": "Acme Traders",
        "voucher_type": "Purchase",
        "currency": "INR",
        "source": "Tally.xml",
    }
    row.update(overrides)
    return row


def bank(**overrides):
    row = {
        "date": "2026-07-14",
        "description": "NEFT ACME TRADERS INV/001",
        "debit": 1180,
        "credit": None,
        "source": "HDFC.pdf",
    }
    row.update(overrides)
    return row


def ledger(**overrides):
    row = {
        "date": "2026-07-12",
        "invoice_number": "INV/001",
        "party_name": "Acme Traders",
        "amount": 1180,
        "voucher_type": "Payment",
        "currency": "INR",
        "source": "Tally.xml",
    }
    row.update(overrides)
    return row


class NormalisationTests(unittest.TestCase):
    def test_reference_normalisation_handles_case_space_punctuation_and_leading_zeros(self) -> None:
        from apps.engine.recon_engine import normalize_reference

        self.assertEqual(normalize_reference(" inv/001 "), normalize_reference("INV-1"))
        self.assertEqual(normalize_reference("AB/0023/2026"), normalize_reference("ab 23 2026"))

    def test_gstin_and_currency_normalisation(self) -> None:
        from apps.engine.recon_engine import normalize_currency, normalize_gstin

        self.assertEqual(normalize_gstin(" 27aapfu0939f1zv "), GSTIN)
        self.assertEqual(normalize_currency("inr"), "INR")

    def test_reference_normalisation_can_be_disabled(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice()],
            [register()],
            {"normalize_references": False},
        )
        self.assertEqual(result["counts"]["matched"], 0)

    def test_rule_snapshot_is_complete_and_bounded(self) -> None:
        from apps.engine.recon_engine import normalise_rules

        rules = normalise_rules({"amount_tolerance": -3, "date_tolerance_days": -9, "max_allocation_items": 99})
        self.assertEqual(rules["amount_tolerance"], 0.0)
        self.assertEqual(rules["date_tolerance_days"], 0)
        self.assertEqual(rules["max_allocation_items"], 8)
        self.assertIn("weights", rules)


class InvoiceMatchingTests(unittest.TestCase):
    def test_exact_normalised_match(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records([invoice()], [register()])
        row = result["rows"][0]
        self.assertEqual(row["classification"], "exact")
        self.assertEqual(row["status"], "matched")
        self.assertGreaterEqual(row["confidence"], 90)
        self.assertEqual(result["counts"]["matched"], 1)

    def test_amount_tolerance_is_applied_and_explained(self) -> None:
        from apps.engine.recon_engine import match_records

        within = match_records([invoice()], [register(amount=1180.75)])
        self.assertEqual(within["rows"][0]["status"], "matched")
        self.assertTrue(any("tolerance" in note.lower() for note in within["rows"][0]["tolerances"]))
        outside = match_records([invoice()], [register(amount=1200)])
        self.assertEqual(outside["rows"][0]["classification"], "review")
        self.assertEqual(outside["rows"][0]["reason_code"], "amount_mismatch")
        self.assertIn("amount_mismatch", outside["rows"][0]["exception_categories"])

    def test_date_tolerance_controls_review(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice()],
            [register(invoice_date="2026-10-12")],
            {"date_tolerance_days": 10},
        )
        self.assertEqual(result["rows"][0]["classification"], "review")
        self.assertEqual(result["rows"][0]["reason_code"], "date_difference")

    def test_tax_difference_is_not_a_silent_match(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records([invoice()], [register(igst=200, amount=1180)])
        self.assertEqual(result["rows"][0]["classification"], "review")
        self.assertEqual(result["rows"][0]["reason_code"], "tax_difference")

    def test_currency_mismatch_is_flagged_without_conversion(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records([invoice(currency="USD")], [register(currency="INR")])
        row = result["rows"][0]
        self.assertEqual(row["classification"], "review")
        self.assertEqual(row["reason_code"], "currency_mismatch")
        self.assertTrue(any("no conversion" in item.lower() for item in row["tolerances"]))
        self.assertEqual(row["left"][0]["amount"], 1180.0)

    def test_invalid_gstin_structure_is_a_review_item(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(supplier_gstin="BADGSTIN", gstin=None)],
            [register(gstin="BADGSTIN")],
        )
        row = result["rows"][0]
        self.assertEqual(row["classification"], "review")
        self.assertEqual(row["reason_code"], "gstin_invalid")
        self.assertIn("gstin_invalid", row["exception_categories"])

    def test_place_of_supply_difference_requires_review_when_present(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(place_of_supply="27-Maharashtra")],
            [register(place_of_supply="29-Karnataka")],
        )
        row = result["rows"][0]
        self.assertEqual(row["classification"], "review")
        self.assertEqual(row["reason_code"], "place_of_supply_differs")
        self.assertIn("place_of_supply_mismatch", row["exception_categories"])

    def test_gstin_mismatch_requires_review(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records([invoice()], [register(gstin=OTHER_GSTIN)])
        self.assertEqual(result["rows"][0]["classification"], "review")
        self.assertEqual(result["rows"][0]["reason_code"], "gstin_mismatch")

    def test_shared_prefix_is_probable_not_auto_matched(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(invoice_number="AB12")],
            [register(invoice_number="AB12345")],
        )
        row = result["rows"][0]
        self.assertEqual(row["status"], "proposed")
        self.assertTrue(row["requires_review"])
        self.assertIn(row["classification"], {"probable", "review"})

    def test_amount_only_never_matches(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(gstin=OTHER_GSTIN, supplier_gstin=OTHER_GSTIN, invoice_number="AAA-1", supplier_name="Alpha")],
            [register(gstin=GSTIN, invoice_number="BBB-2", party_name="Beta")],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["unmatched"], 2)

    def test_duplicate_records_are_not_paired_arbitrarily(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(), invoice(source="copy.pdf")],
            [register()],
        )
        self.assertEqual(result["counts"]["duplicate"], 2)
        self.assertFalse(any(row["status"] == "matched" for row in result["rows"]))
        self.assertTrue(all("duplicate_records" in row["exception_categories"] for row in result["rows"] if row["status"] == "duplicate"))

    def test_one_to_many_allocation_is_proposed_with_allocations(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(invoice_number="INV-9", invoice_date="2026-07-12", invoice_value=1180)],
            [
                register(invoice_number="INV-9-A", invoice_date="2026-07-12", amount=600),
                register(invoice_number="INV-9-B", invoice_date="2026-07-13", amount=580),
            ],
        )
        proposed = [row for row in result["rows"] if row["match_type"] == "one_to_many"]
        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0]["status"], "proposed")
        self.assertTrue(proposed[0]["requires_review"])
        self.assertEqual(len(proposed[0]["allocations"]), 2)
        self.assertEqual(len(proposed[0]["left"]), 1)
        self.assertEqual(len(proposed[0]["right"]), 2)

    def test_many_to_one_aggregation_is_proposed(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [
                invoice(invoice_number="INV-8-A", invoice_value=500),
                invoice(invoice_number="INV-8-B", invoice_value=680),
            ],
            [register(invoice_number="INV-8", amount=1180)],
        )
        proposed = [row for row in result["rows"] if row["match_type"] == "many_to_one"]
        self.assertEqual(len(proposed), 1)
        self.assertEqual(len(proposed[0]["left"]), 2)
        self.assertEqual(len(proposed[0]["right"]), 1)
        self.assertEqual(proposed[0]["status"], "proposed")

    def test_ambiguous_candidates_are_kept_for_review(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(invoice_number="AMB-1", invoice_value=1180)],
            [
                register(invoice_number="AMB-1-A", amount=1180),
                register(invoice_number="AMB-1-B", amount=1180),
            ],
        )
        review = [row for row in result["rows"] if row["reason_code"] == "multiple_candidates"]
        self.assertEqual(len(review), 1)
        self.assertEqual(len(review[0]["candidates"]), 2)
        self.assertFalse(any(row["status"] == "matched" for row in result["rows"]))

    def test_reversal_candidate_requires_supporting_evidence(self) -> None:
        from apps.engine.recon_engine import match_records

        result = match_records(
            [invoice(invoice_number="CN-1", invoice_value=-1180, document_type="CREDIT NOTE")],
            [register(invoice_number="CN-1", amount=1180)],
        )
        reversal = [row for row in result["rows"] if row["status"] == "reversal_candidate"]
        self.assertEqual(len(reversal), 1)
        self.assertIn("not proof", reversal[0]["explanation"].lower())
        self.assertFalse(any(row["status"] == "matched" for row in result["rows"]))

    def test_deterministic_results(self) -> None:
        from apps.engine.recon_engine import match_records

        left = [invoice(), invoice(invoice_number="INV/002", invoice_value=590)]
        right = [register(), register(invoice_number="INV-2", amount=590)]
        first = match_records(left, right)
        second = match_records(left, right)
        self.assertEqual(
            [(row["status"], row["classification"], row["confidence"]) for row in first["rows"]],
            [(row["status"], row["classification"], row["confidence"]) for row in second["rows"]],
        )

    def test_large_dataset_completes_without_quadratic_freeze(self) -> None:
        from apps.engine.recon_engine import match_records

        left = [
            invoice(invoice_number=f"INV/{index:05d}", invoice_value=1000 + index)
            for index in range(600)
        ]
        right = [
            register(invoice_number=f"INV-{index:05d}", amount=1000 + index)
            for index in range(600)
        ]
        started = time.perf_counter()
        result = match_records(left, right)
        elapsed = time.perf_counter() - started
        self.assertEqual(result["counts"]["matched"], 600)
        self.assertLess(elapsed, 15.0, "600x600 matching should not hang the desktop")


class BankMatchingTests(unittest.TestCase):
    def test_bank_reference_and_amount_is_strong_match(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        result = match_bank_ledger([bank()], [ledger()])
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertGreaterEqual(result["rows"][0]["confidence"], 90)

    def test_duplicate_bank_lines_are_not_paired(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        result = match_bank_ledger(
            [bank(), bank(source="HDFC-copy.pdf")],
            [ledger()],
        )
        self.assertEqual(result["counts"]["duplicate"], 2)
        self.assertFalse(any(row["status"] == "matched" for row in result["rows"]))

    def test_partial_payment_calculates_outstanding(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        result = match_bank_ledger([bank(debit=500)], [ledger(amount=1180)])
        row = result["rows"][0]
        self.assertEqual(row["classification"], "partial")
        self.assertEqual(row["status"], "proposed")
        self.assertAlmostEqual(row["differences"]["outstanding"], 680.0)
        self.assertIn("partial_settlement", row["exception_categories"])

    def test_bank_line_can_be_split_across_multiple_vouchers(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        result = match_bank_ledger(
            [bank(description="NEFT ACME TRADERS INV-9A INV-9B", debit=1180)],
            [
                ledger(invoice_number="INV-9A", amount=600),
                ledger(invoice_number="INV-9B", amount=580, date="2026-07-14"),
            ],
        )
        split = [row for row in result["rows"] if row["match_type"] == "one_to_many"]
        self.assertEqual(len(split), 1)
        self.assertEqual(len(split[0]["allocations"]), 2)
        self.assertEqual(split[0]["status"], "proposed")

    def test_amount_only_bank_line_does_not_match(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        result = match_bank_ledger(
            [bank(description="CASH WITHDRAWAL")],
            [ledger(invoice_number="SOMETHING-ELSE", party_name="Different Party")],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["unmatched"], 2)

    def test_fuzzy_bank_candidate_is_review_only(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        result = match_bank_ledger(
            [bank(description="NEFT ACME TRADERS", debit=1180)],
            [ledger(invoice_number="UNRELATED")],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertTrue(any(row["status"] == "proposed" for row in result["rows"]))

    def test_bank_balance_check_only_passes_with_both_closings(self) -> None:
        from apps.engine.recon_engine import match_bank_ledger

        one_sided = match_bank_ledger(
            [bank(balance=11180, closing_balance=11180)],
            [ledger()],
        )
        checks = one_sided["checks"]
        closing = next(item for item in checks if item["name"] == "Closing balance")
        self.assertEqual(closing["status"], "insufficient_data")
        both = match_bank_ledger(
            [bank(balance=11180, closing_balance=11180)],
            [ledger(closing_balance=11180)],
        )
        closing = next(item for item in both["checks"] if item["name"] == "Closing balance")
        self.assertEqual(closing["status"], "calculated")


class BalanceMatchingTests(unittest.TestCase):
    def test_control_and_subledger_close_only_when_calculated(self) -> None:
        from apps.engine.recon_engine import compare_balances

        result = compare_balances(
            [{"gl_account": "2100", "account_name": "Creditors", "opening_balance": 1000, "debit": 500, "credit": 200, "closing_balance": 700}],
            [{"gl_account": "2100", "account_name": "Creditors", "opening_balance": 1000, "debit": 500, "credit": 200, "closing_balance": 700}],
        )
        self.assertEqual(result["counts"]["matched"], 1)
        row = result["rows"][0]
        self.assertEqual(row["status"], "matched")
        self.assertAlmostEqual(row["left"]["closing"], 700.0)

    def test_multiple_subledger_parties_are_summed_not_taken_as_last(self) -> None:
        from apps.engine.recon_engine import compare_balances

        result = compare_balances(
            [{"gl_account": "2100", "account_name": "Creditors", "opening_balance": 250000, "debit": 156000, "credit": 120000, "closing_balance": 222000}],
            [
                {"gl_account": "2100", "vendor_number": "V-1", "opening_balance": 140000, "debit": 80000, "credit": 60000, "closing_balance": 120000},
                {"gl_account": "2100", "vendor_number": "V-2", "opening_balance": 110000, "debit": 38000, "credit": 30000, "closing_balance": 102000},
            ],
        )
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertAlmostEqual(result["rows"][0]["right"]["closing"], 222000.0)


if __name__ == "__main__":
    unittest.main()
