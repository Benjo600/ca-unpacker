from __future__ import annotations

import json
import unittest

from apps.engine.profiles import (
    CUSTOM_KEY,
    ENTITY_TYPES,
    PROFESSIONS,
    entity_type_options,
    normalize_profile,
    presumptive_allowed,
    profile_options,
    profession_options,
    resolve_profile,
)


class ProfileCatalogTests(unittest.TestCase):
    def test_catalog_keys_are_unique_and_slugged(self) -> None:
        keys = [profession.key for profession in PROFESSIONS]
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertRegex(key, r"^[a-z][a-z0-9_]*$")

    def test_every_profession_carries_a_usable_rule_pack(self) -> None:
        for profession in PROFESSIONS:
            with self.subTest(profession=profession.key):
                self.assertTrue(profession.summary)
                self.assertTrue(profession.expense_heads)
                self.assertTrue(profession.capital_hint)
                self.assertTrue(profession.watch)
                self.assertTrue(profession.gst.typical_rate)
                self.assertTrue(profession.gst.note)
                self.assertTrue(profession.tds)
                for rule in profession.tds:
                    self.assertIn(rule.code, {"194J", "194C", "194H", "194I"})
                    self.assertGreater(rule.threshold, 0)
                    self.assertTrue(rule.law_ref)

    def test_options_are_json_serialisable_for_the_desktop_bridge(self) -> None:
        payload = profile_options()
        json.dumps(payload)
        self.assertEqual(len(payload["professions"]), len(PROFESSIONS))
        self.assertEqual(len(payload["entity_types"]), len(ENTITY_TYPES))
        self.assertTrue(payload["as_of"])

    def test_option_helpers_match_the_catalog(self) -> None:
        self.assertEqual(len(profession_options()), len(PROFESSIONS))
        self.assertEqual(len(entity_type_options()), len(ENTITY_TYPES))


class NormalizeProfileTests(unittest.TestCase):
    def test_empty_profile_is_allowed(self) -> None:
        profile = normalize_profile(None)
        self.assertEqual(profile["profession_key"], "")
        self.assertIsNone(profile["gst_registered"])
        self.assertEqual(profile["banks"], [])

    def test_catalog_profession_takes_the_catalog_label(self) -> None:
        profile = normalize_profile(
            {"profession_key": "doctor", "profession_label": "ignored"}
        )
        self.assertEqual(profile["profession_key"], "doctor")
        self.assertEqual(profile["profession_label"], "Doctor / clinic")

    def test_unknown_profession_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not in the list"):
            normalize_profile({"profession_key": "astronaut"})

    def test_custom_profession_needs_a_label(self) -> None:
        with self.assertRaisesRegex(ValueError, "Describe the profession"):
            normalize_profile({"profession_key": CUSTOM_KEY})

    def test_custom_label_alone_becomes_a_custom_profile(self) -> None:
        profile = normalize_profile({"profession_label": "Veterinary practice"})
        self.assertEqual(profile["profession_key"], CUSTOM_KEY)
        self.assertEqual(profile["profession_label"], "Veterinary practice")

    def test_gst_flag_accepts_words_and_booleans(self) -> None:
        self.assertIs(normalize_profile({"gst_registered": "yes"})["gst_registered"], True)
        self.assertIs(normalize_profile({"gst_registered": "No"})["gst_registered"], False)
        self.assertIsNone(normalize_profile({"gst_registered": ""})["gst_registered"])
        with self.assertRaisesRegex(ValueError, "registered for GST"):
            normalize_profile({"gst_registered": "maybe"})

    def test_unknown_entity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "entity type"):
            normalize_profile({"entity_type": "cooperative"})

    def test_banks_are_cleaned_and_deduped(self) -> None:
        profile = normalize_profile({"banks": "HDFC, SBI; hdfc / ICICI"})
        self.assertEqual(profile["banks"], ["HDFC", "SBI", "ICICI"])

    def test_long_notes_are_cut_not_rejected(self) -> None:
        profile = normalize_profile({"notes": "x" * 900})
        self.assertEqual(len(profile["notes"]), 500)


class ResolveProfileTests(unittest.TestCase):
    def test_legacy_client_without_profile_fields_does_not_crash(self) -> None:
        resolved = resolve_profile({"id": 1, "name": "Acme", "gstin": None})
        self.assertFalse(resolved["is_set"])
        self.assertEqual(resolved["summary"], "No profile set")
        self.assertEqual(resolved["rules"]["key"], CUSTOM_KEY)

    def test_profile_summary_and_rules_are_built_from_columns(self) -> None:
        resolved = resolve_profile(
            {
                "id": 2,
                "name": "Dr Mehta",
                "gstin": None,
                "profession_key": "doctor",
                "profession_label": "Doctor / clinic",
                "entity_type": "proprietorship",
                "gst_registered": 0,
                "profile_json": '{"books": "Tally", "banks": ["HDFC"]}',
            }
        )
        self.assertTrue(resolved["is_set"])
        self.assertIn("Doctor / clinic", resolved["summary"])
        self.assertIn("Not GST registered", resolved["summary"])
        self.assertEqual(resolved["rules"]["presumptive"]["section"], "44ADA")
        self.assertEqual(resolved["details"]["books"], "Tally")

    def test_custom_profession_uses_the_generic_pack(self) -> None:
        resolved = resolve_profile(
            {"profession_key": CUSTOM_KEY, "profession_label": "Veterinary practice"}
        )
        self.assertTrue(resolved["custom"])
        self.assertEqual(resolved["rules"]["label"], "Veterinary practice")
        self.assertIsNone(resolved["rules"]["presumptive"])

    def test_broken_stored_json_falls_back_instead_of_raising(self) -> None:
        resolved = resolve_profile(
            {"profession_key": "doctor", "profile_json": "{not json"}
        )
        self.assertTrue(resolved["is_set"])
        self.assertEqual(resolved["details"]["banks"], [])

    def test_presumptive_gate_follows_entity_type(self) -> None:
        self.assertTrue(presumptive_allowed("proprietorship"))
        self.assertTrue(presumptive_allowed("partnership"))
        self.assertTrue(presumptive_allowed(""))
        self.assertFalse(presumptive_allowed("llp"))
        self.assertFalse(presumptive_allowed("pvt_ltd"))


if __name__ == "__main__":
    unittest.main()
