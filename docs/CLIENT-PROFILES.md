# Client profiles and treatment checks

Each client can carry a profile: profession, entity type, GST status, and a few
free-text details. The profile decides **which checks run** on that client's
period packs. It never posts an entry, never nets anything and never concludes
that an amount is income, capital or a particular expense.

> Software finds evidence. The CA makes the accounting and tax call.

## What the profile changes

| Area | What the app does |
| --- | --- |
| TDS | Matches payments the client **made** against the sections the profession usually attracts (194J, 194C, 194H, 194I) and shows the observed amount beside a working limit. |
| GST | Checks the preset GST position (taxable / exempt / mixed / not applicable) against invoice tax, sales data and the saved GSTIN. |
| Presumptive | Compares the period's sales turnover with the 44AD / 44ADA / 44AE limit and states that a full-year figure is still needed. |
| Capital vs revenue | Lists asset-like purchases above a working limit for review. |
| Expense heads | Maps invoice lines to the profession's suggested heads and reports what did not match. |

Every flag carries: what was seen, why it was raised, the observed count and
amount, the working limit, the law reference, and what the CA should do. The
same content is written to `Treatment_Review.xlsx` in the period folder.

## What the profile must never do

- Decide that a bank credit is income.
- Post a journal, ledger or voucher.
- Present a threshold as a finding ("TDS short by ₹X"). Limits change and depend
  on the payee, the year and the contract.
- Hide an unmatched line. Unmatched lines are counted and sampled.

## Where it lives

`clients` columns:

```
profession_key    VARCHAR(60)   catalog key, or 'custom'
profession_label  VARCHAR(120)  display label
entity_type       VARCHAR(40)   proprietorship, partnership, llp, ...
gst_registered    INTEGER       NULL unknown, 1 yes, 0 no
profile_json      VARCHAR       books, banks, broker, notes
```

Schema version 3 adds these columns. Existing rows upgrade with
`profession_key = NULL` and `profile_json = '{}'`.

## Catalog

`apps/engine/profiles.py` holds the catalog. Each `Profession` has:

```python
Profession(
    key="doctor",
    label="Doctor / clinic",
    group="Professional services",
    summary="Medical practice, clinic or consulting room.",
    gst=GstRule(...),                 # exempt / taxable / mixed / not_applicable
    tds=(TDS_194J, TDS_194I, TDS_194C),  # sections this client pays out under
    presumptive=P_44ADA,              # or 44AD / 44AE / None
    expense_heads=(...),              # suggested heads, matched by keyword
    capital_hint="...",               # what usually looks capital here
    watch="...",                      # one practical line shown on the pack
)
```

### Adding a profession

1. Add a `Profession(...)` entry to `PROFESSIONS`. Keep `key` a lowercase slug.
2. Reuse the shared `TDS_*` and `P_*` constants unless the profession genuinely
   needs a different rule.
3. Run `python -m pytest apps/engine/tests/test_profiles.py`.
4. The UI picks it up automatically: `profile_options()` feeds both selects.

No database change is needed. The catalog is code, not user data, so a bad
profession cannot be created from the UI. Free text is only allowed through
`profession_key = "custom"`, which falls back to the generic rule pack.

## Thresholds

`RULES_AS_OF` in `profiles.py` is the year the limits were checked. Limits are
shown to the CA with that label and must be confirmed for the filing year. When
a limit changes, edit the `TDS_*` / `P_*` constants and bump `RULES_AS_OF`.

Current working limits in the catalog:

| Rule | Limit | Basis |
| --- | --- | --- |
| 194J | ₹50,000 | per payee per year |
| 194C | ₹30,000 | per contract, ₹1,00,000 a year |
| 194H | ₹20,000 | per payee per year |
| 194I | ₹50,000 | per month |
| 44ADA | ₹50 lakh / ₹75 lakh | 5% cash condition for the enhanced limit |
| 44AD | ₹2 crore / ₹3 crore | 5% cash condition for the enhanced limit |
| 44AE | 10 vehicles | per vehicle per month, not a turnover test |

## Engine flow

```
create/update client profile
        ↓
parse_period (files → rows)
        ↓
resolve_profile(client)            # columns + profile_json → rule pack
        ↓
evaluate_treatment(profile, rows)  # evidence flags, heads, unmapped
        ↓
Treatment_Review.xlsx + pack_summary.json["treatment"]
        ↓
desktop get_period_pack → treatment block in the dump tray
```

`Treatment_Review.xlsx` is only written when the client has a profile and the
period produced at least one other output. A pack with no data stays a pack
with no data.

After editing a profile, existing packs keep their old notes until the period
is re-parsed. The profile card says so.

## Tests

- `apps/engine/tests/test_profiles.py` — catalog shape, validation, resolution,
  legacy rows, broken JSON, JSON serialisability for the webview bridge.
- `apps/engine/tests/test_treatment.py` — each rule, thresholds, monthly rent
  buckets, entity gates, deduplication, report shape.
- `apps/engine/tests/test_client_profiles.py` — storage round-trip, clearing a
  profile, and an end-to-end pack with the treatment workbook.
- `apps/engine/tests/test_migrations.py` — v1 → v3 upgrade keeps client rows and
  adds the profile columns.
