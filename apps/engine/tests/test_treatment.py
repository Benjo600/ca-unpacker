from __future__ import annotations

import unittest

from apps.engine.profiles import resolve_profile
from apps.engine.treatment import evaluate_treatment


def make_profile(**overrides) -> dict:
    base = {
        "name": "Client",
        "gstin": None,
        "profession_key": "lawyer",
        "entity_type": "proprietorship",
        "gst_registered": True,
        "profile_json": "{}",
    }
    base.update(overrides)
    return resolve_profile(base)


def bank_payment(amount, text, *, date="2026-07-05", party=None):
    return {
        "date": date,
        "description": text,
        "party_name": party or text,
        "debit": amount,
        "credit": None,
        "source": "bank.pdf#p1",
    }


def invoice(amount, description, *, tax=0.0, date="2026-07-05", party="Vendor"):
    return {
        "date": date,
        "invoice_date": date,
        "supplier_name": party,
        "description": description,
        "invoice_value": amount,
        "taxable_value": amount - tax,
        "amount": amount,
        "tax": tax,
        "source": "invoice.pdf#p1",
    }


def codes(treatment: dict) -> set[str]:
    return {flag["code"] for flag in treatment["flags"]}


class TdsRuleTests(unittest.TestCase):
    def test_professional_fee_payment_above_the_limit_is_flagged(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            bank_rows=[bank_payment(75000, "NEFT DR PROFESSIONAL FEES ADVOCATE")],
        )
        self.assertIn("tds_194j", codes(treatment))
        flag = next(item for item in treatment["flags"] if item["code"] == "tds_194j")
        self.assertEqual(flag["severity"], "review")
        self.assertEqual(flag["observed"]["total"], 75000)
        self.assertTrue(flag["threshold"]["amount"])

    def test_small_payment_below_the_limit_is_not_flagged(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            bank_rows=[bank_payment(10000, "PROFESSIONAL FEES")],
        )
        self.assertNotIn("tds_194j", codes(treatment))

    def test_contractor_payments_aggregate_to_the_annual_limit(self) -> None:
        rows = [
            bank_payment(25000, "LABOUR CONTRACTOR PAYMENT", party=f"Contractor {index}")
            for index in range(5)
        ]
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="manufacturer"), bank_rows=rows
        )
        self.assertIn("tds_194c", codes(treatment))

    def test_rent_is_grouped_by_month(self) -> None:
        same_month = [
            bank_payment(30000, "OFFICE RENT", date="2026-07-05"),
            bank_payment(30000, "OFFICE RENT", date="2026-07-20"),
        ]
        treatment = evaluate_treatment(profile=make_profile(), bank_rows=same_month)
        self.assertIn("tds_194i", codes(treatment))

        split_months = [
            bank_payment(30000, "OFFICE RENT", date="2026-07-05"),
            bank_payment(30000, "OFFICE RENT", date="2026-08-05"),
        ]
        treatment = evaluate_treatment(profile=make_profile(), bank_rows=split_months)
        self.assertNotIn("tds_194i", codes(treatment))

    def test_current_account_wording_does_not_look_like_rent(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            bank_rows=[bank_payment(60000, "TRF TO CURRENT ACCOUNT 50100222")],
        )
        self.assertNotIn("tds_194i", codes(treatment))

    def test_undated_rent_payments_are_not_pooled_into_one_month(self) -> None:
        rows = [bank_payment(30000, "OFFICE RENT", date="") for _ in range(3)]
        treatment = evaluate_treatment(profile=make_profile(), bank_rows=rows)
        self.assertNotIn("tds_194i", codes(treatment))

    def test_commission_above_the_limit_is_flagged(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="distributor"),
            bank_rows=[bank_payment(45000, "COMMISSION PAID TO SUB DEALER")],
        )
        self.assertIn("tds_194h", codes(treatment))

    def test_purchase_register_and_bank_rows_are_not_double_counted(self) -> None:
        row = bank_payment(60000, "PROFESSIONAL FEES", date="2026-07-05", party="Sharma & Co")
        purchase = invoice(60000, "PROFESSIONAL FEES", party="Sharma & Co", date="2026-07-05")
        treatment = evaluate_treatment(
            profile=make_profile(), bank_rows=[row], purchase_rows=[purchase]
        )
        flag = next(item for item in treatment["flags"] if item["code"] == "tds_194j")
        self.assertEqual(flag["observed"]["count"], 1)
        self.assertEqual(flag["observed"]["total"], 60000)


class GstRuleTests(unittest.TestCase):
    def test_exempt_profession_with_gst_on_an_invoice_is_flagged(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="doctor"),
            purchase_rows=[invoice(12000, "PROCEDURE PACKAGE", tax=1800)],
        )
        self.assertIn("gst_tax_on_exempt", codes(treatment))

    def test_unregistered_taxable_profession_with_sales_is_flagged(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(gst_registered=False),
            sales_rows=[invoice(100000, "LEGAL FEES", tax=18000)],
        )
        self.assertIn("gst_registration_review", codes(treatment))

    def test_sales_without_tax_are_a_note_not_a_finding(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            sales_rows=[invoice(50000, "LEGAL FEES", tax=0)],
        )
        flag = next(item for item in treatment["flags"] if item["code"] == "gst_no_tax_on_sales")
        self.assertEqual(flag["severity"], "info")


class PresumptiveRuleTests(unittest.TestCase):
    def test_turnover_below_the_limit_is_an_option_to_check(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="doctor"),
            sales_rows=[invoice(4000000, "CONSULTATION FEES")],
        )
        flag = next(item for item in treatment["flags"] if item["code"] == "presumptive_44ada_eligible")
        self.assertEqual(flag["severity"], "info")

    def test_turnover_above_the_limit_is_a_check(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="doctor"),
            sales_rows=[invoice(9000000, "CONSULTATION FEES")],
        )
        self.assertIn("presumptive_44ada_above", codes(treatment))

    def test_entity_type_gate_stops_the_scheme(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="doctor", entity_type="pvt_ltd"),
            sales_rows=[invoice(4000000, "CONSULTATION FEES")],
        )
        self.assertIn("presumptive_44ada_entity", codes(treatment))

    def test_missing_turnover_is_stated_rather_than_guessed(self) -> None:
        treatment = evaluate_treatment(profile=make_profile(profession_key="doctor"))
        self.assertIn("presumptive_44ada_no_turnover", codes(treatment))

    def test_transporter_gets_the_vehicle_note(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="transporter"),
            sales_rows=[invoice(2000000, "FREIGHT CHARGES")],
        )
        self.assertIn("presumptive_44ae_vehicles", codes(treatment))


class CapitalAndHeadTests(unittest.TestCase):
    def test_asset_like_purchase_is_listed_for_review(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            purchase_rows=[invoice(82000, "LAPTOP PURCHASE", party="Dell")],
        )
        flag = next(item for item in treatment["flags"] if item["code"] == "capital_candidates")
        self.assertEqual(flag["severity"], "review")
        self.assertEqual(flag["observed"]["count"], 1)

    def test_asset_word_inside_another_word_is_not_a_match(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            purchase_rows=[invoice(82000, "CAREER DEVELOPMENT PROGRAMME")],
        )
        self.assertNotIn("capital_candidates", codes(treatment))

    def test_small_asset_purchase_is_below_the_working_limit(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            purchase_rows=[invoice(9000, "LAPTOP MOUSE")],
        )
        self.assertNotIn("capital_candidates", codes(treatment))

    def test_expense_heads_map_lines_and_report_what_is_left(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="doctor"),
            line_item_rows=[
                {"description": "Surgical consumables", "amount": 12000, "date": "2026-07-02"},
                {"description": "Diesel for generator", "amount": 4000, "date": "2026-07-03"},
            ],
        )
        heads = {item["head"]: item for item in treatment["expense_heads"]}
        self.assertIn("Medical consumables", heads)
        self.assertEqual(heads["Medical consumables"]["count"], 1)
        self.assertEqual(treatment["unmapped"]["count"], 1)

    def test_expense_heads_fall_back_to_purchase_rows_without_line_items(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(profession_key="doctor"),
            purchase_rows=[invoice(15000, "Medical consumables", party="MedPlus")],
        )
        heads = {item["head"]: item for item in treatment["expense_heads"]}
        self.assertIn("Medical consumables", heads)
        self.assertEqual(heads["Medical consumables"]["amount"], 15000)

    def test_profile_conflict_is_a_data_check(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(gst_registered=False, gstin="27AAAAA0000A1Z5")
        )
        self.assertIn("profile_gst_conflict", codes(treatment))


class ReportShapeTests(unittest.TestCase):
    def test_report_keeps_the_disclaimer_and_counts(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(),
            bank_rows=[bank_payment(75000, "PROFESSIONAL FEES")],
        )
        self.assertTrue(treatment["disclaimer"])
        self.assertTrue(treatment["as_of"])
        self.assertEqual(treatment["counts"]["total"], len(treatment["flags"]))
        self.assertEqual(
            treatment["counts"]["review"] + treatment["counts"]["check"] + treatment["counts"]["info"],
            treatment["counts"]["total"],
        )

    def test_flags_are_ordered_review_first(self) -> None:
        treatment = evaluate_treatment(
            profile=make_profile(gstin="27AAAAA0000A1Z5", gst_registered=False),
            bank_rows=[bank_payment(75000, "PROFESSIONAL FEES")],
            sales_rows=[invoice(100000, "LEGAL FEES", tax=18000)],
        )
        severities = [flag["severity"] for flag in treatment["flags"]]
        order = {"review": 0, "check": 1, "info": 2}
        self.assertEqual(severities, sorted(severities, key=lambda item: order[item]))

    def test_empty_period_still_returns_a_report(self) -> None:
        treatment = evaluate_treatment(profile=make_profile())
        self.assertIn("flags", treatment)
        self.assertIn("expense_heads", treatment)
        self.assertEqual(treatment["unmapped"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
