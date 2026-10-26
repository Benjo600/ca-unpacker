"""Evidence flags that differ by client profession.

Every function here reports what was found in the parsed rows and why it was
raised. Nothing is posted, netted or concluded. The CA reads the flag and
decides whether it is income, a loan, a capital purchase or something else.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from apps.engine.profiles import (
    RULES_AS_OF,
    RULES_DISCLAIMER,
    presumptive_allowed,
)

REVIEW = "review"
CHECK = "check"
INFO = "info"
_SEVERITY_ORDER = {REVIEW: 0, CHECK: 1, INFO: 2}

# A working threshold for the capital-versus-revenue prompt. The client's own
# capitalisation policy decides; this only decides what is worth showing.
CAPITAL_WORKING_THRESHOLD = 50000.0
CAPITAL_KEYWORDS = (
    "computer",
    "laptop",
    "desktop",
    "server",
    "printer",
    "scanner",
    "ups",
    "furniture",
    "chair",
    "table",
    "almirah",
    "air conditioner",
    "airconditioner",
    "ac unit",
    "machinery",
    "machine",
    "equipment",
    "vehicle",
    "car ",
    "bike",
    "scooter",
    "truck",
    "software licence",
    "software license",
    "cctv",
    "camera",
    "renovation",
    "interior work",
    "civil work",
    "building",
    "land ",
    "lift",
    "generator",
    "inverter",
    "solar",
    "plot",
)

_STOP_WORDS = {
    "and",
    "the",
    "for",
    "with",
    "other",
    "charges",
    "charge",
    "costs",
    "cost",
    "expenses",
    "expense",
    "payments",
    "payment",
    "fees",
}


def _keyword_pattern(words: Sequence[str]) -> re.Pattern[str] | None:
    """Word-boundary matcher, so "rent" does not fire on "CURRENT ACCOUNT"."""
    cleaned = [re.escape(str(word).strip()) for word in words if str(word).strip()]
    if not cleaned:
        return None
    alternatives = "|".join(sorted(cleaned, key=len, reverse=True))
    return re.compile(r"(?<![a-z0-9])(" + alternatives + r")(?![a-z0-9])")


CAPITAL_PATTERN = _keyword_pattern(CAPITAL_KEYWORDS)


def _matches(pattern: re.Pattern[str] | None, text: str) -> bool:
    return bool(pattern and pattern.search(text))


def _amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(float(value))
    text = f"{abs(rounded):,}"
    return f"₹{text}" if value >= 0 else f"-₹{text}"


def _row_text(row: Mapping) -> str:
    parts = [
        row.get("description"),
        row.get("narration"),
        row.get("particulars"),
        row.get("remarks"),
        row.get("party_name"),
        row.get("supplier_name"),
        row.get("trade_name"),
        row.get("raw_text"),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _row_party(row: Mapping) -> str:
    for key in ("party_name", "supplier_name", "trade_name", "vendor"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    text = str(row.get("description") or row.get("narration") or "").strip()
    return text[:60] or "Unnamed payee"


def _row_date(row: Mapping) -> str:
    for key in ("date", "invoice_date", "txn_date"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:10]
    return ""


def _row_source(row: Mapping) -> str:
    return str(row.get("source") or row.get("filename") or "").strip()


def _payment(row: Mapping, amount: float, origin: str) -> dict:
    return {
        "date": _row_date(row),
        "party": _row_party(row),
        "amount": round(float(amount), 2),
        "text": _row_text(row),
        "source": _row_source(row),
        "origin": origin,
    }


def _collect_payments(
    bank_rows: Sequence[Mapping],
    purchase_rows: Sequence[Mapping],
    books_rows: Sequence[Mapping],
) -> list[dict]:
    """Payments the client made. Credits are receipts and are not scanned."""
    items: list[dict] = []
    for row in bank_rows:
        amount = _amount(row.get("debit"))
        if amount and amount > 0:
            items.append(_payment(row, amount, "bank"))
    for row in purchase_rows:
        amount = _amount(row.get("invoice_value"))
        if amount is None:
            amount = _amount(row.get("taxable_value"))
        if amount and amount > 0:
            items.append(_payment(row, amount, "purchase register"))
    for row in books_rows:
        voucher = str(row.get("voucher_type") or "").lower()
        if "payment" not in voucher and "expense" not in voucher:
            continue
        amount = _amount(row.get("amount"))
        if amount and abs(amount) > 0:
            items.append(_payment(row, abs(amount), "books"))

    deduped: list[dict] = []
    seen: set[tuple[str, str, float]] = set()
    for item in items:
        key = (item["date"], item["party"].lower(), item["amount"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _sample(item: Mapping) -> dict:
    text = str(item.get("text") or _row_text(item))
    return {
        "date": item.get("date") or _row_date(item),
        "party": item.get("party") or _row_party(item),
        "amount": item.get("amount")
        if item.get("amount") is not None
        else _amount(item.get("invoice_value")) or _amount(item.get("taxable_value")),
        "narration": text[:140],
        "source": item.get("source") or _row_source(item),
    }


def _flag(
    *,
    code: str,
    area: str,
    severity: str,
    title: str,
    detail: str,
    action: str,
    basis: str = "",
    law_ref: str = "",
    observed: Mapping | None = None,
    threshold: Mapping | None = None,
    samples: Sequence[Mapping] = (),
) -> dict:
    return {
        "code": code,
        "area": area,
        "severity": severity,
        "title": title,
        "detail": detail,
        "action": action,
        "basis": basis,
        "law_ref": law_ref,
        "observed": dict(observed) if observed else None,
        "threshold": dict(threshold) if threshold else None,
        "samples": [_sample(item) for item in samples[:8]],
    }


def _tds_flags(profile: Mapping, payments: Sequence[Mapping]) -> list[dict]:
    rules = (profile.get("rules") or {}).get("tds") or []
    flags: list[dict] = []
    for rule in rules:
        keywords = tuple(rule.get("keywords") or ())
        pattern = _keyword_pattern(keywords)
        if pattern is None:
            continue
        matches = [item for item in payments if pattern.search(item["text"])]
        if not matches:
            continue

        threshold = float(rule.get("threshold") or 0)
        annual = rule.get("annual_threshold")
        largest = max(item["amount"] for item in matches)
        total = round(sum(item["amount"] for item in matches), 2)

        monthly = bool(rule.get("monthly"))
        if monthly:
            buckets: dict[tuple[str, str], float] = {}
            undated: list[float] = []
            for item in matches:
                month = (item["date"] or "")[:7]
                if not month:
                    undated.append(item["amount"])
                    continue
                key = (item["party"].lower(), month)
                buckets[key] = buckets.get(key, 0.0) + item["amount"]
            over_threshold = any(value >= threshold for value in buckets.values()) or any(
                value >= threshold for value in undated
            )
        else:
            by_party: dict[str, float] = {}
            for item in matches:
                by_party[item["party"].lower()] = by_party.get(item["party"].lower(), 0.0) + item["amount"]
            over_threshold = any(value >= threshold for value in by_party.values())
            if annual and total >= float(annual):
                over_threshold = True

        if not over_threshold and largest < threshold:
            continue

        word_patterns = {word: _keyword_pattern([word]) for word in keywords}
        basis_words = sorted(
            {
                word
                for word, word_pattern in word_patterns.items()
                if any(_matches(word_pattern, item["text"]) for item in matches)
            }
        )[:5]
        basis = "Matched words: " + ", ".join(basis_words) if basis_words else "Matched by description"
        label = str(rule.get("label") or "this section").lower()
        if len(matches) == 1:
            detail = (
                f"1 payment of {_money(total)} looks like {label}. "
                f"The working limit is a prompt, not a finding."
            )
        else:
            detail = (
                f"{len(matches)} payments totalling {_money(total)} look like {label}. "
                f"The largest single payment is {_money(largest)}."
            )
        flags.append(
            _flag(
                code=f"tds_{str(rule.get('code', '')).lower()}",
                area="TDS",
                severity=REVIEW,
                title=f"Possible {rule.get('code')} payments",
                detail=detail,
                action=(
                    "Check whether TDS was deducted and deposited, and whether the payee "
                    "gave a lower-deduction certificate. The working limit is a prompt, "
                    "not a finding."
                ),
                basis=basis,
                law_ref=str(rule.get("law_ref") or ""),
                observed={"count": len(matches), "total": total, "largest": largest},
                threshold={
                    "amount": threshold,
                    "basis": rule.get("threshold_basis") or "",
                    "rate": rule.get("rate") or "",
                    "as_of": RULES_AS_OF,
                },
                samples=matches,
            )
        )
    return flags


def _gst_flags(profile: Mapping, purchase_rows: Sequence[Mapping], sales_rows: Sequence[Mapping]) -> list[dict]:
    rules = profile.get("rules") or {}
    gst = rules.get("gst") or {}
    status = str(gst.get("status") or "")
    flags: list[dict] = []

    taxed = []
    for row in list(purchase_rows) + list(sales_rows):
        tax = _amount(row.get("tax"))
        if tax and tax > 0:
            taxed.append(row)

    if status == "exempt" and taxed:
        flags.append(
            _flag(
                code="gst_tax_on_exempt",
                area="GST",
                severity=REVIEW,
                title="GST charged on an exempt activity",
                detail=(
                    f"{len(taxed)} invoice line(s) carry GST even though this profession is "
                    "preset as exempt. Exemption is line-by-line, so mixed activity is possible."
                ),
                action="Read the invoices and confirm which line is exempt and which is taxable before taking credit.",
                basis="Profile preset is exempt; invoice rows carry a tax amount.",
                law_ref="GST rate notifications for this service",
                observed={"count": len(taxed)},
                samples=taxed,
            )
        )
    if status == "not_applicable" and taxed:
        flags.append(
            _flag(
                code="gst_tax_on_non_gst",
                area="GST",
                severity=REVIEW,
                title="GST charged where the profile says it does not apply",
                detail="The profile is set to non-GST income, but invoice lines carry GST.",
                action="Either the profile is wrong or a taxable activity has started. Fix whichever is true.",
                basis="Profile preset is not applicable; invoice rows carry a tax amount.",
                observed={"count": len(taxed)},
                samples=taxed,
            )
        )
    if status in {"taxable", "mixed"}:
        if profile.get("gst_registered") is False and (sales_rows or taxed):
            flags.append(
                _flag(
                    code="gst_registration_review",
                    area="GST",
                    severity=REVIEW,
                    title="Taxable activity but marked unregistered",
                    detail=(
                        "The profile says the client is not GST registered, but sales or GST-bearing "
                        "invoices were found in this period."
                    ),
                    action="Confirm turnover against the registration threshold and the client's registration status.",
                    basis="Profile GST status is unregistered; sales data present.",
                    law_ref="GST registration threshold for the state and category",
                    observed={"sales_lines": len(sales_rows)},
                )
            )
        if sales_rows and not any((_amount(row.get("tax")) or 0) > 0 for row in sales_rows):
            flags.append(
                _flag(
                    code="gst_no_tax_on_sales",
                    area="GST",
                    severity=INFO,
                    title="No GST charged on sales",
                    detail=(
                        f"{len(sales_rows)} sales line(s) show no tax. That is normal for exempt or "
                        "below-threshold supplies, and unusual for a registered taxable business."
                    ),
                    action="Confirm whether these sales are exempt, composite, or simply missing tax.",
                    basis="Profile is taxable; sales rows carry no tax amount.",
                    observed={"count": len(sales_rows)},
                )
            )
    return flags


def _presumptive_flags(
    profile: Mapping,
    sales_rows: Sequence[Mapping],
    gstr_1_rows: Sequence[Mapping],
) -> list[dict]:
    rule = (profile.get("rules") or {}).get("presumptive")
    if not rule:
        return []

    section = str(rule.get("section") or "")
    entity = str(profile.get("entity_type") or "")
    flags: list[dict] = []

    if not presumptive_allowed(entity):
        flags.append(
            _flag(
                code=f"presumptive_{section.lower()}_entity",
                area="Presumptive",
                severity=CHECK,
                title=f"{section} is not open to this entity type",
                detail=(
                    f"{section} is available to individuals, HUF and partnership firms. "
                    f"This client is set up as {profile.get('entity_type_label') or 'another entity type'}."
                ),
                action="Confirm the entity type. If it is correct, drop the presumptive line from the working papers.",
                basis="Entity type in the client profile.",
                law_ref=f"s.{section}, Income Tax Act 1961 (carried into the 2025 Act)",
            )
        )
        return flags

    if section == "44AE":
        flags.append(
            _flag(
                code="presumptive_44ae_vehicles",
                area="Presumptive",
                severity=INFO,
                title="44AE depends on vehicle count, not turnover",
                detail=(
                    "44AE presumes income per goods vehicle per month, up to 10 vehicles. "
                    "Turnover from the bank statement cannot confirm eligibility on its own."
                ),
                action="Count the goods vehicles held during the year and check tonnage for each.",
                basis="Profile profession is transporter.",
                law_ref="s.44AE; up to 10 goods vehicles",
            )
        )
        return flags

    turnover = 0.0
    for row in sales_rows:
        amount = _amount(row.get("invoice_value"))
        if amount is None:
            amount = _amount(row.get("taxable_value"))
        if amount:
            turnover += amount
    if turnover <= 0:
        for row in gstr_1_rows:
            amount = _amount(row.get("invoice_value"))
            if amount is None:
                amount = _amount(row.get("taxable"))
            if amount:
                turnover += amount
    if turnover <= 0:
        flags.append(
            _flag(
                code=f"presumptive_{section.lower()}_no_turnover",
                area="Presumptive",
                severity=INFO,
                title=f"{section} eligibility cannot be tested yet",
                detail="No sales register or GSTR-1 turnover was found for this period.",
                action="Add the sales register or GSTR-1, then re-check the presumptive limit.",
                basis="No sales rows in the pack.",
                law_ref=f"s.{section}",
            )
        )
        return flags

    limit = float(rule.get("limit") or 0)
    enhanced = float(rule.get("enhanced_limit") or 0)
    if enhanced > limit and turnover <= enhanced:
        within = f"the enhanced {_money(enhanced)} limit"
    elif turnover <= limit:
        within = f"the standard {_money(limit)} limit"
    else:
        within = ""
    if within:
        flags.append(
            _flag(
                code=f"presumptive_{section.lower()}_eligible",
                area="Presumptive",
                severity=INFO,
                title=f"{section} may be available",
                detail=(
                    f"Sales turnover in this period is {_money(turnover)}, within {within}. "
                    f"{rule.get('profit_note') or ''} The enhanced limit needs "
                    f"{rule.get('cash_condition') or 'the cash condition'}."
                ),
                action="Check the full-year turnover and cash receipts before deciding whether to opt in.",
                basis="Sales rows and GSTR-1 amounts in this period only.",
                law_ref=f"s.{section}; limits as of {RULES_AS_OF}",
                observed={"turnover": round(turnover, 2)},
                threshold={"amount": limit, "enhanced": enhanced, "as_of": RULES_AS_OF},
            )
        )
    else:
        flags.append(
            _flag(
                code=f"presumptive_{section.lower()}_above",
                area="Presumptive",
                severity=CHECK,
                title=f"Turnover above the {section} limit",
                detail=(
                    f"Sales turnover in this period is {_money(turnover)}, above the standard "
                    f"{_money(limit)} limit. A full-year figure is still needed."
                ),
                action="Add the remaining periods before ruling the scheme out, then check the audit position.",
                basis="Sales rows and GSTR-1 amounts in this period only.",
                law_ref=f"s.{section}; limits as of {RULES_AS_OF}",
                observed={"turnover": round(turnover, 2)},
            )
        )
    return flags


def _capital_flags(
    purchase_rows: Sequence[Mapping],
    line_item_rows: Sequence[Mapping],
    payments: Sequence[Mapping],
) -> list[dict]:
    candidates: list[Mapping] = []
    for row in list(purchase_rows) + list(line_item_rows):
        text = _row_text(row)
        amount = _amount(row.get("amount"))
        if amount is None:
            amount = _amount(row.get("invoice_value"))
        if amount is None:
            amount = _amount(row.get("taxable_value"))
        if (
            amount
            and amount >= CAPITAL_WORKING_THRESHOLD
            and _matches(CAPITAL_PATTERN, text)
        ):
            candidates.append(row)
    for item in payments:
        if item["amount"] >= CAPITAL_WORKING_THRESHOLD and _matches(
            CAPITAL_PATTERN, item["text"]
        ):
            candidates.append(
                {
                    "description": item["text"],
                    "party_name": item["party"],
                    "date": item["date"],
                    "amount": item["amount"],
                    "source": item["source"],
                }
            )
    if not candidates:
        return []

    seen: set[tuple[str, str, float]] = set()
    unique: list[Mapping] = []
    for row in candidates:
        key = (
            _row_date(row),
            str(row.get("supplier_name") or row.get("party_name") or "")[:40].lower(),
            round(float(_amount(row.get("amount")) or _amount(row.get("invoice_value")) or 0), 2),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    total = sum(
        _amount(row.get("amount"))
        or _amount(row.get("invoice_value"))
        or _amount(row.get("taxable_value"))
        or 0.0
        for row in unique
    )
    if len(unique) == 1:
        detail = (
            f"1 purchase of {_money(round(total, 2))} looks like a capital item "
            "by description and value."
        )
    else:
        detail = (
            f"{len(unique)} purchases totalling {_money(round(total, 2))} look like "
            "capital items by description and value."
        )
    return [
        _flag(
            code="capital_candidates",
            area="Capital vs revenue",
            severity=REVIEW,
            title="Asset-like purchases above the working limit",
            detail=detail,
            action=(
                "Confirm each item against the client's capitalisation policy. Description and "
                "value alone do not decide capital versus revenue."
            ),
            basis=f"Description matched an asset word and the amount is at least {_money(CAPITAL_WORKING_THRESHOLD)}.",
            observed={"count": len(unique), "total": round(total, 2)},
            threshold={"amount": CAPITAL_WORKING_THRESHOLD, "basis": "working limit, client policy decides"},
            samples=[
                {
                    "date": _row_date(row),
                    "party": _row_party(row),
                    "amount": _amount(row.get("amount"))
                    or _amount(row.get("invoice_value"))
                    or _amount(row.get("taxable_value")),
                    "text": _row_text(row),
                    "source": _row_source(row),
                }
                for row in unique
            ],
        )
    ]


def _line_amount(row: Mapping) -> float | None:
    for key in ("amount", "taxable", "invoice_value", "taxable_value"):
        value = _amount(row.get(key))
        if value is not None:
            return value
    return None


def _head_keywords(head: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z]{3,}", head.lower())
    expanded: list[str] = []
    for word in words:
        if word in _STOP_WORDS:
            continue
        expanded.append(word)
        if len(word) > 4 and word.endswith("s"):
            expanded.append(word[:-1])
    return tuple(dict.fromkeys(expanded))


def _expense_heads(
    profile: Mapping,
    line_item_rows: Sequence[Mapping],
    purchase_rows: Sequence[Mapping] = (),
) -> tuple[list[dict], dict]:
    heads = (profile.get("rules") or {}).get("expense_heads") or []
    rows = list(line_item_rows) or list(purchase_rows)
    used: set[int] = set()
    mapped: list[dict] = []
    for head in heads:
        keywords = _head_keywords(str(head))
        pattern = _keyword_pattern(keywords)
        if pattern is None:
            continue
        hits: list[tuple[int, Mapping]] = []
        for index, row in enumerate(rows):
            if index in used:
                continue
            if pattern.search(_row_text(row)):
                hits.append((index, row))
        if not hits:
            continue
        for index, _row in hits:
            used.add(index)
        total = sum(_line_amount(row) or 0.0 for _index, row in hits)
        mapped.append(
            {
                "head": str(head),
                "count": len(hits),
                "amount": round(total, 2),
                "keywords": list(keywords),
                "samples": [
                    {
                        "date": _row_date(row),
                        "party": _row_party(row),
                        "amount": _line_amount(row),
                        "narration": _row_text(row)[:140],
                    }
                    for _index, row in hits[:4]
                ],
            }
        )

    unmapped_rows = [row for index, row in enumerate(rows) if index not in used]
    unmapped = {
        "count": len(unmapped_rows),
        "amount": round(sum(_line_amount(row) or 0.0 for row in unmapped_rows), 2),
        "samples": [
            {
                "date": _row_date(row),
                "party": _row_party(row),
                "amount": _line_amount(row),
                "narration": _row_text(row)[:140],
            }
            for row in unmapped_rows[:6]
        ],
    }
    return mapped, unmapped


def _profile_flags(profile: Mapping) -> list[dict]:
    flags: list[dict] = []
    gstin = str(profile.get("gstin") or "").strip()
    registered = profile.get("gst_registered")
    if registered is True and not gstin:
        flags.append(
            _flag(
                code="profile_gstin_missing",
                area="Profile",
                severity=CHECK,
                title="GST registered but no GSTIN saved",
                detail="The profile says the client is registered, but no GSTIN is on the client record.",
                action="Add the GSTIN so invoices and returns can be tied back to the client.",
                basis="Profile fields on the client record.",
            )
        )
    if registered is False and gstin:
        flags.append(
            _flag(
                code="profile_gst_conflict",
                area="Profile",
                severity=CHECK,
                title="GSTIN on file but profile says unregistered",
                detail="One of the two is out of date.",
                action="Update the GSTIN or the registration flag so later checks are reliable.",
                basis="Profile fields on the client record.",
            )
        )
    return flags


def evaluate_treatment(
    *,
    profile: Mapping,
    bank_rows: Sequence[Mapping] = (),
    purchase_rows: Sequence[Mapping] = (),
    sales_rows: Sequence[Mapping] = (),
    books_rows: Sequence[Mapping] = (),
    line_item_rows: Sequence[Mapping] = (),
    gstr_1_rows: Sequence[Mapping] = (),
) -> dict:
    """Match the client's rule pack against the rows parsed for one period."""
    payments = _collect_payments(bank_rows, purchase_rows, books_rows)
    flags: list[dict] = []
    flags.extend(_profile_flags(profile))
    flags.extend(_tds_flags(profile, payments))
    flags.extend(_gst_flags(profile, purchase_rows, sales_rows))
    flags.extend(_presumptive_flags(profile, sales_rows, gstr_1_rows))
    flags.extend(_capital_flags(purchase_rows, line_item_rows, payments))

    flags.sort(key=lambda item: (_SEVERITY_ORDER.get(item["severity"], 9), item["area"], item["code"]))

    mapped_heads, unmapped = _expense_heads(profile, line_item_rows, purchase_rows)

    counts = {"total": len(flags), REVIEW: 0, CHECK: 0, INFO: 0}
    for flag in flags:
        counts[flag["severity"]] = counts.get(flag["severity"], 0) + 1

    rules = profile.get("rules") or {}
    return {
        "as_of": RULES_AS_OF,
        "disclaimer": RULES_DISCLAIMER,
        "profile": {
            "summary": profile.get("summary") or "",
            "profession_label": profile.get("profession_label") or "",
            "profession_group": profile.get("profession_group") or "",
            "entity_type_label": profile.get("entity_type_label") or "",
            "gst_registered": profile.get("gst_registered"),
            "gstin": profile.get("gstin") or "",
            "gst_rate": (rules.get("gst") or {}).get("typical_rate") or "",
            "gst_note": (rules.get("gst") or {}).get("note") or "",
            "watch": rules.get("watch") or "",
            "custom": bool(profile.get("custom")),
            "details": dict(profile.get("details") or {}),
        },
        "flags": flags,
        "expense_heads": mapped_heads,
        "unmapped": unmapped,
        "counts": counts,
    }
