"""Client file review: what a client's month should contain, and whether the
documents agree with each other.

The checklist is driven by the client's profession: each profession names the
documents a clean monthly file usually has, graded essential or recommended.
The cross-checks compare documents against each other when both sides are in
the pack. Nothing is posted, netted or concluded: every item states what was
seen, why it was raised and what the CA should do.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from apps.engine.profiles import RULES_AS_OF, RULES_DISCLAIMER, resolve_profile
from apps.engine.treatment import (
    CHECK,
    INFO,
    REVIEW,
    _SEVERITY_ORDER,
    _amount,
    _keyword_pattern,
    _money,
    _row_date,
    _row_party,
    _row_source,
    _row_text,
)

VERIFIED = "verified"
ATTACHED = "attached"
MISSING = "missing"

ESSENTIAL = "essential"
RECOMMENDED = "recommended"

SALARY_WORDS = ("salary", "payroll", "stipend", "wages", "gross salary", "staff pay", "wages sheet")
SALARY_PATTERN = _keyword_pattern(SALARY_WORDS)

CASH_WORDS = ("cash", "atm", "self dra", "csh dep", "cash dep")
CASH_PATTERN = _keyword_pattern(CASH_WORDS)
CASH_PAYMENT_LIMIT = 10000.0
CASH_RECEIPT_LIMIT = 200000.0


@dataclass(frozen=True)
class DocNeed:
    """One document a clean monthly file should contain for a profession."""

    key: str
    label: str
    grade: str
    why: str
    read_kinds: tuple[str, ...] = ()
    row_tokens: tuple[str, ...] = ()
    name_words: tuple[str, ...] = ()
    escalate_on: tuple[str, ...] = (
        # treatment flag codes whose presence upgrades this document
    )


def _bank() -> DocNeed:
    return DocNeed(
        key="bank_statement",
        label="Bank statement",
        grade=ESSENTIAL,
        why=(
            "Money in and out for the month is the backbone of the file: it supports "
            "turnover, payments and the cash-receipt story."
        ),
        read_kinds=("bank",),
        row_tokens=("bank",),
    )


def _purchases(label: str) -> DocNeed:
    return DocNeed(
        key="expense_bills",
        label=label,
        grade=ESSENTIAL,
        why=(
            "Supporting bills for the money spent. Without them input credit and "
            "expense claims have no paper behind them."
        ),
        read_kinds=("invoice",),
        row_tokens=("purchase",),
    )


def _sales(label: str, why: str) -> DocNeed:
    return DocNeed(
        key="sales_record",
        label=label,
        grade=ESSENTIAL,
        why=why,
        row_tokens=("sales", "gstr_1"),
        name_words=("sales", "sale register", "day book", "daybook", "receipts", "collection register", "billing", "revenue"),
    )


def _books() -> DocNeed:
    return DocNeed(
        key="books_export",
        label="Books export (Tally / Zoho)",
        grade=RECOMMENDED,
        why=(
            "A books export lets purchases and sales be checked against the returns "
            "instead of checked by hand."
        ),
        read_kinds=("tally", "zoho"),
        row_tokens=("books",),
    )


def _tds() -> DocNeed:
    return DocNeed(
        key="tds_certificates",
        label="TDS certificates (Form 16A / 26AS)",
        grade=RECOMMENDED,
        why=(
            "Tax deducted at source on this client's receipts is only provable from "
            "the certificates or 26AS. The bank statement cannot show it."
        ),
        name_words=("form 16", "form16", "form 16a", "form16a", "form 26a", "form26a", "26as", "tds cert", "tax deduction", "tds summary", "traces"),
        escalate_on=("tds_194j", "tds_194c", "tds_194h", "tds_194i"),
    )


def _rent(label: str) -> DocNeed:
    return DocNeed(
        key="rent_agreement",
        label=label,
        grade=RECOMMENDED,
        why=(
            "Rent paid in the month needs a written agreement to sit behind the "
            "payment and the TDS call."
        ),
        name_words=("rent agreement", "lease agreement", "lease deed", "tenancy", "rent deed"),
        escalate_on=("tds_194i",),
    )


def _salary_register() -> DocNeed:
    return DocNeed(
        key="salary_register",
        label="Salary or wage register",
        grade=RECOMMENDED,
        why=(
            "Staff payments show in the bank every month. A register supports the "
            "salary split and the statutory dues behind it."
        ),
        name_words=("salary register", "payroll", "salary sheet", "wage sheet", "staff register"),
    )


def _stock() -> DocNeed:
    return DocNeed(
        key="stock_statement",
        label="Stock statement",
        grade=RECOMMENDED,
        why=(
            "For a trading business the stock position explains purchases against "
            "sales, and lenders usually require it."
        ),
        name_words=("stock statement", "inventory statement", "stock report"),
    )


def _labour(label: str) -> DocNeed:
    return DocNeed(
        key="labour_agreements",
        label=label,
        grade=RECOMMENDED,
        why=(
            "Labour and subcontractor payments need written terms to decide "
            "employee versus contractor, and the TDS behind them."
        ),
        name_words=("labour", "labor", "subcontract", "sub-contract", "works contract", "job work agreement", "wage agreement"),
        escalate_on=("tds_194c",),
    )


def _needs_for(profession_key: str) -> tuple[DocNeed, ...]:
    """Document packs. Four curated professions first; everything else generic."""
    if profession_key == "doctor":
        return (
            _bank(),
            _purchases("Expense bills (lab, pharmacy, equipment)"),
            _sales(
                "Receipts record",
                "Receivables and patient collections must add up to the money in the bank.",
            ),
            _tds(),
            _rent("Clinic rent agreement"),
            _salary_register(),
            _books(),
        )
    if profession_key in {"trader_wholesale", "trader_retail"}:
        return (
            _bank(),
            _purchases("Purchase bills"),
            _sales("Sales record", "Sales must add up against money in the bank and the returns."),
            _stock(),
            _tds(),
            _rent("Shop or godown rent agreement"),
            _salary_register(),
            _books(),
        )
    if profession_key == "consultant":
        return (
            _bank(),
            _purchases("Expense bills"),
            _sales("Client invoices", "Fee bills raised must add up against money received."),
            _tds(),
            _rent("Office rent agreement"),
            _salary_register(),
            _books(),
        )
    if profession_key == "contractor":
        return (
            _bank(),
            _purchases("Material and works bills"),
            _sales("Client bills (RA bills / invoices)", "Work bills raised must add up against money received."),
            _labour("Labour and subcontractor agreements"),
            _tds(),
            _rent("Site or office rent agreement"),
            _salary_register(),
            _books(),
        )
    return (
        _bank(),
        _purchases("Expense bills"),
        _sales("Sales record", "Sales and receipts must add up against money in the bank."),
        _tds(),
        _books(),
    )


_GST_NEEDS = (
    DocNeed(
        key="gstr_2b_download",
        label="GSTR-2B download",
        grade=ESSENTIAL,
        why=(
            "The portal's own list of bills against the client's GSTIN is what input "
            "credit is checked against."
        ),
        read_kinds=("gstr_2b",),
        row_tokens=("gstr_2b",),
    ),
    DocNeed(
        key="gstr_1_download",
        label="GSTR-1 download",
        grade=ESSENTIAL,
        why=(
            "The outward return fixes the declared sales for the month; the books "
            "must agree with it."
        ),
        read_kinds=("gstr_1",),
        row_tokens=("gstr_1",),
    ),
    DocNeed(
        key="gstr_3b_download",
        label="GSTR-3B acknowledgement",
        grade=ESSENTIAL,
        why=(
            "3B is what was actually paid to the treasury. 2B and the books can be "
            "perfect and 3B still disagree."
        ),
        read_kinds=("gstr_3b",),
        row_tokens=("gstr_3b",),
    ),
)


def _status_words_match(words: Sequence[str], filename: str) -> bool:
    pattern = _keyword_pattern(words)
    return bool(pattern and pattern.search(filename.lower()))


def _inventory(files: Sequence[Any]) -> dict[str, dict]:
    """Group the period's files by type with their parse outcome."""
    inventory: dict[str, dict] = {}
    for stored in files:
        kind = str(getattr(stored, "override_kind", None) or getattr(stored, "detected_kind", "unknown"))
        bucket = inventory.setdefault(
            kind,
            {"processed": [], "stuck": [], "names": []},
        )
        name = str(getattr(stored, "original_name", "") or "")
        outcome = str(getattr(stored, "parse_outcome", "") or "")
        if outcome == "processed":
            bucket["processed"].append(stored)
        else:
            bucket["stuck"].append(stored)
        bucket["names"].append(name)
    return inventory


def _attach_hint(inventory: Mapping[str, Mapping]) -> str:
    unknown = inventory.get("unknown") or {}
    count = len(unknown.get("names") or [])
    if not count:
        return ""
    return (
        f"{count} unrecognised file(s) sit in Needs review; "
        "one of them may be the missing document — label it and re-run."
    )


def _checklist_item(
    need: DocNeed,
    inventory: Mapping[str, Mapping],
    sources: Mapping[str, Sequence[Mapping]],
    escalated: str | None,
) -> dict:
    has_rows = any(list(sources.get(token) or ()) for token in need.row_tokens)
    has_processed = False
    attached_names: list[str] = []
    stuck_items: list[tuple[str, str]] = []
    for kind in need.read_kinds:
        bucket = inventory.get(kind) or {}
        for _stored in bucket.get("processed") or []:
            has_processed = True
        for stored in bucket.get("stuck") or []:
            outcome = str(getattr(stored, "parse_outcome", "") or "")
            name = str(getattr(stored, "original_name", "") or "")
            reason = str(getattr(stored, "parse_reason_message", "") or "")
            stuck_items.append((name, reason or outcome.replace("_", " ")))

    by_name: list[str] = []
    if not has_processed and not has_rows:
        for kind, bucket in inventory.items():
            for name in bucket.get("names") or []:
                if _status_words_match(need.name_words, name):
                    by_name.append(name)

    if has_processed or has_rows:
        status = VERIFIED
        evidence = "Read this period: the extracted rows are in the pack."
        action = "Spot-check the extracted values against the source crop before relying on them."
    elif attached_names or stuck_items:
        status = ATTACHED
        if stuck_items:
            details = "; ".join(f"{name} ({reason})" for name, reason in stuck_items[:3])
            evidence = f"Attached, but the app could not read it: {details}."
            action = "Open the attached file and read it by hand, or add the password and re-run."
        else:
            evidence = "Attached, but no rows could be extracted from it this period."
            action = "Open the attached file and read it by hand, then re-parse."
    elif by_name:
        status = ATTACHED
        evidence = (
            "Matched by file name only: " + ", ".join(by_name[:3]) + ". "
            "The app does not read this document type."
        )
        action = "Open the file once and confirm it is the right document."
    else:
        status = MISSING
        evidence = "No file of this type was added to the period."
        action = "Collect it from the client, or record why it is not applicable this month."
        hint = _attach_hint(inventory)
        if hint:
            evidence += " " + hint

    grade = need.grade
    if escalated:
        grade = ESSENTIAL
        why = f"{need.why} {escalated}"
    else:
        why = need.why

    return {
        "key": need.key,
        "label": need.label,
        "grade": grade,
        "status": status,
        "escalated": bool(escalated),
        "why": why,
        "evidence": evidence,
        "action": action,
    }


def _escalation(
    need: DocNeed,
    treatment_flags: Sequence[Mapping],
    sources: Mapping[str, Sequence[Mapping]],
) -> str | None:
    codes = {str(flag.get("code") or "") for flag in treatment_flags}
    serious = {
        str(flag.get("code") or "")
        for flag in treatment_flags
        if str(flag.get("severity") or "") in {REVIEW, CHECK}
    }
    if need.key == "salary_register":
        # Salary is escalated by looking at the money rows directly.
        for rows in (sources.get("bank") or (), sources.get("books") or ()):
            for row in rows:
                text = _row_text(row)
                debit = _amount(row.get("debit")) or abs(_amount(row.get("amount")) or 0)
                if debit and debit > 0 and _matches_any(SALARY_PATTERN, text):
                    return (
                        "Staff salary payment(s) were seen in this period's money rows, "
                        "so the register is now essential."
                    )
    for code in need.escalate_on:
        if code in serious or code in codes:
            return (
                "This document became essential because this period's payments matched "
                f"{code.replace('_', ' ').upper()} in the treatment checks and it is the cross-check for them."
            )
    return None


def _matches_any(pattern: re.Pattern[str] | None, text: str) -> bool:
    return bool(pattern and pattern.search(text))


def _finding(
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
        "samples": [
            {
                "date": _row_date(item),
                "party": _row_party(item),
                "amount": _amount(item.get("amount"))
                or _amount(item.get("invoice_value"))
                or _amount(item.get("taxable_value")),
                "narration": _row_text(item)[:140],
                "source": _row_source(item),
            }
            for item in list(samples)[:8]
        ],
    }


def _total(rows: Sequence[Mapping], *keys: str) -> float:
    total = 0.0
    count = 0
    for row in rows:
        for key in keys:
            value = _amount(row.get(key))
            if value is not None:
                total += value
                count += 1
                break
    return round(total, 2) + 0.0 * count


def _check_purchases_vs_2b(
    purchase_rows: Sequence[Mapping],
    gstr_2b_rows: Sequence[Mapping],
    recon_rows: Sequence[Mapping] | None,
) -> list[dict]:
    if not purchase_rows or not gstr_2b_rows:
        return []
    purchase_total = _total(purchase_rows, "invoice_value", "taxable_value")
    portal_total = _total(gstr_2b_rows, "invoice_value", "taxable")
    if purchase_total <= 0 and portal_total <= 0:
        return []
    larger = max(purchase_total, portal_total, 1.0)
    difference = round(purchase_total - portal_total, 2)
    ratio = abs(difference) / larger
    if ratio < 0.005:
        return []

    severity = REVIEW if ratio > 0.1 or abs(difference) > 100000 else CHECK
    direction = "less than" if difference < 0 else "more than"
    samples: list[Mapping] = []
    if recon_rows:
        unmatched = [
            row for row in recon_rows
            if str(row.get("status") or "") in {"books_only", "portal_only", "amount_mismatch"}
        ]
        samples = unmatched
    return [
        _finding(
            code="review_purchases_vs_2b",
            area="Purchases vs 2B",
            severity=severity,
            title="Purchase bills and GSTR-2B do not agree",
            detail=(
                f"The purchase register shows {_money(purchase_total)} across {len(purchase_rows)} line(s); "
                f"GSTR-2B shows {_money(portal_total)} across {len(gstr_2b_rows)} line(s). "
                f"The register is {_money(abs(difference))} {direction} the portal ({ratio:.0%})."
            ),
            action=(
                "Open Master_Reconciliation_Grid.xlsx, work the unmatched rows first and "
                "decide which figure stands."
            ),
            basis="Bill totals from the purchase register against the GSTR-2B download.",
            observed={
                "purchase_total": purchase_total,
                "portal_total": portal_total,
                "difference": difference,
                "purchase_lines": len(purchase_rows),
                "portal_lines": len(gstr_2b_rows),
            },
            threshold={"tolerance": "0.5% of the larger side", "as_of": RULES_AS_OF},
            samples=samples,
        )
    ]


def _check_sales_vs_gstr1(
    sales_rows: Sequence[Mapping],
    gstr_1_rows: Sequence[Mapping],
) -> list[dict]:
    if not sales_rows or not gstr_1_rows:
        return []
    books_total = _total(sales_rows, "invoice_value", "taxable_value")
    portal_total = _total(gstr_1_rows, "invoice_value", "taxable")
    if books_total <= 0 and portal_total <= 0:
        return []
    larger = max(books_total, portal_total, 1.0)
    difference = round(books_total - portal_total, 2)
    ratio = abs(difference) / larger
    if ratio < 0.005:
        return []

    severity = REVIEW if ratio > 0.1 or abs(difference) > 100000 else CHECK
    direction = "more than" if difference > 0 else "less than"
    return [
        _finding(
            code="review_sales_vs_gstr1",
            area="Sales vs GSTR-1",
            severity=severity,
            title="Books sales and GSTR-1 do not agree",
            detail=(
                f"The sales register shows {_money(books_total)} across {len(sales_rows)} line(s); "
                f"GSTR-1 shows {_money(portal_total)} across {len(gstr_1_rows)} line(s). "
                f"The register is {_money(abs(difference))} {direction} the return ({ratio:.0%})."
            ),
            action=(
                "Recheck the sales register against the outward return: look for bills "
                "raised but not filed, credit notes and timing differences."
            ),
            basis="Sales register totals against the GSTR-1 download.",
            observed={
                "books_total": books_total,
                "portal_total": portal_total,
                "difference": difference,
                "books_lines": len(sales_rows),
                "portal_lines": len(gstr_1_rows),
            },
            threshold={"tolerance": "0.5% of the larger side", "as_of": RULES_AS_OF},
        )
    ]


def _check_sales_vs_bank(
    sales_rows: Sequence[Mapping],
    bank_rows: Sequence[Mapping],
) -> list[dict]:
    if not sales_rows or not bank_rows:
        return []
    sales_total = _total(sales_rows, "invoice_value", "taxable_value")
    credits = 0.0
    for row in bank_rows:
        value = _amount(row.get("credit"))
        if value and value > 0:
            credits += value
    if sales_total <= 0 or credits <= 0:
        return []
    ratio = credits / max(sales_total, 1.0)
    if 0.5 <= ratio <= 2.0:
        return []
    detail = (
        f"Money coming into the bank this period is {_money(credits)}, while booked sales "
        f"are {_money(sales_total)}. Bank money includes loans, capital and personal "
        "deposits, so this is a prompt to explain the difference — not a finding."
    )
    return [
        _finding(
            code="check_sales_vs_bank",
            area="Sales vs bank",
            severity=CHECK,
            title="Bank receipts do not sit near booked sales",
            detail=detail,
            action=(
                "Walk the large bank credits and label each one: sale, loan, capital "
                "introduced or something else. Keep the labelling in the working notes."
            ),
            basis="Bank statement credits against the sales register, as a prompt only.",
            observed={"bank_credits": round(credits, 2), "sales_total": sales_total},
        )
    ]


def _normalise_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalise_gstin(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _check_supplier_gstin_conflicts(
    purchase_rows: Sequence[Mapping],
    gstr_2b_rows: Sequence[Mapping],
) -> list[dict]:
    by_name: dict[str, dict[str, str]] = {}
    by_gstin: dict[str, set[str]] = {}
    for row in list(purchase_rows) + list(gstr_2b_rows):
        name = _normalise_name(
            next((row.get(key) for key in ("supplier_name", "trade_name", "party_name") if row.get(key)), "")
        )
        gstin = _normalise_gstin(
            next((row.get(key) for key in ("supplier_gstin", "gstin") if row.get(key)), "")
        )
        if not name or not gstin:
            continue
        known = by_name.setdefault(name, {})
        known.setdefault(gstin, "")
        by_gstin.setdefault(gstin, set()).add(name)
        if len(known) > 1:
            by_name[name][gstin] = by_name[name].get(gstin) or "seen again"

    findings: list[dict] = []
    for name, gstins in by_name.items():
        if len(gstins) < 2:
            continue
        samples = [
            row
            for row in list(purchase_rows) + list(gstr_2b_rows)
            if _normalise_name(next((row.get(k) for k in ("supplier_name", "trade_name", "party_name") if row.get(k)), "")) == name
        ][:8]
        findings.append(
            _finding(
                code="check_supplier_gstin_conflict",
                area="Supplier identity",
                severity=CHECK,
                title="One supplier name carries two different GSTINs",
                detail=(
                    f"'{name.title()}' appears under {len(gstins)} different GSTINs across the "
                    "purchase register and/or GSTR-2B. Either they are two branches of the "
                    "same firm, an amended registration, or one entry is wrong."
                ),
                action=(
                    "Confirm the correct GSTIN with the supplier and hold the credit anyway "
                    "only on the GSTIN the portal shows."
                ),
                basis="Same supplier name mapped against the GSTINs recorded for it.",
                observed={"supplier": name, "gstin_count": len(gstins)},
                samples=samples,
            )
        )
    for gstin, names in by_gstin.items():
        if len(names) < 2:
            continue
        findings.append(
            _finding(
                code="check_gstin_multiple_names",
                area="Supplier identity",
                severity=CHECK,
                title="One GSTIN is written under different supplier names",
                detail=(
                    f"GSTIN {gstin} appears under {len(names)} different names: "
                    + ", ".join(sorted(names)[:4])
                    + ". Trade names vary, but the CA should confirm they are the same firm."
                ),
                action="Check the name on the invoice image against the portal trade name before taking credit.",
                basis="Same GSTIN mapped against the supplier names recorded for it.",
                observed={"gstin": gstin, "name_count": len(names)},
            )
        )
    return findings


def _check_duplicate_invoices(
    purchase_rows: Sequence[Mapping],
    gstr_2b_rows: Sequence[Mapping],
) -> list[dict]:
    findings: list[dict] = []

    def within(rows: Sequence[Mapping], label: str, severity: str) -> None:
        seen: dict[tuple[str, str], list[Mapping]] = {}
        for row in rows:
            supplier = _normalise_name(row.get("supplier_name") or row.get("gstin") or row.get("trade_name"))
            number = _normalise_name(row.get("invoice_number") or row.get("voucher_number"))
            if not supplier or not number:
                continue
            seen.setdefault((supplier, number), []).append(row)
        for (supplier, number), hits in seen.items():
            if len(hits) < 2:
                continue
            amounts = sorted({_total([hit], "invoice_value", "taxable_value") for hit in hits})
            same_amount = len(amounts) == 1
            findings.append(
                _finding(
                    code="check_duplicate_invoice",
                    area="Bill numbering",
                    severity=severity,
                    title=f"Bill {number} appears {len(hits)} times",
                    detail=(
                        f"Bill {number} from '{supplier.title()}' appears {len(hits)} times in {label}"
                        + (
                            " with the same amount, which usually means it was entered twice."
                            if same_amount
                            else " with different amounts, which means one of them is wrong."
                        )
                    ),
                    action="Open both documents and decide which entry is real; delete or flag the other.",
                    basis=f"Same supplier and bill number repeated within {label}.",
                    observed={"count": len(hits), "bill": number, "supplier": supplier},
                    samples=hits,
                )
            )

    within(purchase_rows, "the purchase register", REVIEW)
    within(gstr_2b_rows, "GSTR-2B", CHECK)
    return findings


def _check_statement_coverage(bank_rows: Sequence[Mapping]) -> list[dict]:
    """Statement files whose date ranges leave a hole between them."""
    dates: list[str] = []
    for row in bank_rows:
        value = _row_date(row)
        if value:
            dates.append(value)
    if len(dates) < 2:
        return []
    dates.sort()
    ordered = sorted(set(dates))
    longest_gap = 0
    gap_start = ""
    gap_end = ""
    for index in range(1, len(ordered)):
        previous = _date_value(ordered[index - 1])
        current = _date_value(ordered[index])
        if previous is None or current is None:
            continue
        gap = (current - previous).days - 1
        if gap > longest_gap:
            longest_gap = gap
            gap_start = ordered[index - 1]
            gap_end = ordered[index]
    if longest_gap < 25:
        return []
    return [
        _finding(
            code="check_statement_gap",
            area="Coverage",
            severity=CHECK,
            title=f"{longest_gap}-day hole in the bank rows",
            detail=(
                f"The bank rows jump from {gap_start} to {gap_end}. That usually means a "
                "statement month is missing, not that no transactions happened."
            ),
            action=(
                "Collect the statement for the missing stretch, or record why nothing "
                "was transacted (e.g. a dormant business month)."
            ),
            basis="Sorted transaction dates read from the bank statement rows.",
            observed={"missing_days": longest_gap, "after": gap_start, "before": gap_end},
            threshold={"gap_days": 25, "as_of": RULES_AS_OF},
        )
    ]


_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _date_value(text: str):
    match = _DATE_RE.match(text)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _check_cash(
    bank_rows: Sequence[Mapping],
) -> list[dict]:
    payments: list[Mapping] = []
    receipts: list[Mapping] = []
    for row in bank_rows:
        text = _row_text(row)
        if not _matches_any(CASH_PATTERN, text):
            continue
        debit = _amount(row.get("debit"))
        credit = _amount(row.get("credit"))
        if debit and debit >= CASH_PAYMENT_LIMIT:
            payments.append(row)
        if credit and credit >= CASH_RECEIPT_LIMIT:
            receipts.append(row)

    findings: list[dict] = []
    if payments:
        total = sum(_amount(row.get("debit")) or 0 for row in payments)
        findings.append(
            _finding(
                code="check_cash_payments",
                area="Cash",
                severity=CHECK,
                title="Large cash payments in the bank rows",
                detail=(
                    f"{len(payments)} bank row(s) totalling {_money(total)} match cash words and are "
                    "at or above the working limit of ₹10,000 in one cash payment."
                ),
                action=(
                    "Trace whether the money actually went out as cash, to whom, and whether "
                    "the payment is an expense. Whatever is not an expense is untouched."
                ),
                basis="Bank narrations matched cash words; amounts at or above the working limit.",
                law_ref="s.40A(3) — cash spending above ₹10,000 in one payment is disallowed for the payer, subject to exceptions.",
                observed={"count": len(payments), "total": round(total, 2)},
                threshold={"amount": CASH_PAYMENT_LIMIT, "basis": "per cash payment", "as_of": RULES_AS_OF},
                samples=payments,
            )
        )
    if receipts:
        findings.append(
            _finding(
                code="check_cash_receipts",
                area="Cash",
                severity=CHECK,
                title="Very large single cash receipts in the bank rows",
                detail=(
                    f"{len(receipts)} bank credit(s) of {_money(CASH_RECEIPT_LIMIT)} or more match cash words. "
                    "A single receipt at this size in cash is restricted."
                ),
                action="Identify the counterparty and the mode in, before treating any of it as business receipt.",
                basis="Bank narrations matched cash words; single credit at or above the restriction level.",
                law_ref="s.269ST — a single cash receipt of ₹2,00,000 or more is restricted, subject to exceptions.",
                observed={"count": len(receipts)},
                threshold={"amount": CASH_RECEIPT_LIMIT, "basis": "per single receipt", "as_of": RULES_AS_OF},
                samples=receipts,
            )
        )
    return findings


def evaluate_file_review(
    *,
    profile: Mapping,
    files: Sequence[Any] = (),
    bank_rows: Sequence[Mapping] = (),
    purchase_rows: Sequence[Mapping] = (),
    sales_rows: Sequence[Mapping] = (),
    books_rows: Sequence[Mapping] = (),
    gstr_1_rows: Sequence[Mapping] = (),
    gstr_2b_rows: Sequence[Mapping] = (),
    gstr_3b_rows: Sequence[Mapping] = (),
    recon_rows: Sequence[Mapping] | None = None,
    treatment_flags: Sequence[Mapping] = (),
) -> dict:
    """Build the completeness checklist and the cross-document checks."""
    rules = profile.get("rules") or {}
    profession_key = str(profile.get("profession_key") or "")
    gst_registered = profile.get("gst_registered")

    needs = list(_needs_for(profession_key))
    if gst_registered is True:
        needs.extend(_GST_NEEDS)

    inventory = _inventory(files)
    sources = {
        "bank": list(bank_rows),
        "purchase": list(purchase_rows),
        "sales": list(sales_rows),
        "books": list(books_rows),
        "gstr_1": list(gstr_1_rows),
        "gstr_2b": list(gstr_2b_rows),
        "gstr_3b": list(gstr_3b_rows),
    }

    checklist = []
    for need in needs:
        escalated = _escalation(need, treatment_flags, sources)
        checklist.append(_checklist_item(need, inventory, sources, escalated))

    flags: list[dict] = []
    flags.extend(_check_purchases_vs_2b(purchase_rows, gstr_2b_rows, recon_rows))
    flags.extend(_check_sales_vs_gstr1(sales_rows, gstr_1_rows))
    flags.extend(_check_sales_vs_bank(sales_rows, bank_rows))
    flags.extend(_check_supplier_gstin_conflicts(purchase_rows, gstr_2b_rows))
    flags.extend(_check_duplicate_invoices(purchase_rows, gstr_2b_rows))
    flags.extend(_check_statement_coverage(bank_rows))
    flags.extend(_check_cash(bank_rows))
    flags.sort(key=lambda item: (_SEVERITY_ORDER.get(item["severity"], 9), item["area"], item["code"]))

    counts = {
        "essential_missing": sum(
            1 for item in checklist if item["status"] == MISSING and item["grade"] == ESSENTIAL
        ),
        "recommended_missing": sum(
            1 for item in checklist if item["status"] == MISSING and item["grade"] == RECOMMENDED
        ),
        "attached_not_read": sum(
            1 for item in checklist
            if item["status"] == ATTACHED and "could not read" in str(item.get("evidence") or "").lower()
        ),
        "verified": sum(1 for item in checklist if item["status"] == VERIFIED),
        "review": sum(1 for flag in flags if flag["severity"] == REVIEW),
        "check": sum(1 for flag in flags if flag["severity"] == CHECK),
        "info": sum(1 for flag in flags if flag["severity"] == INFO),
    }
    counts["total"] = len(flags)

    if counts["essential_missing"] or counts["review"]:
        readiness = "gaps"
    elif counts["recommended_missing"] or counts["check"] or counts["attached_not_read"]:
        readiness = "check"
    else:
        readiness = "ready"

    return {
        "as_of": RULES_AS_OF,
        "disclaimer": RULES_DISCLAIMER,
        "readiness": readiness,
        "profile": {
            "summary": profile.get("summary") or "",
            "profession_key": profession_key,
            "profession_label": profile.get("profession_label") or "",
            "entity_type_label": profile.get("entity_type_label") or "",
            "gst_registered": gst_registered,
        },
        "checklist": checklist,
        "checks": flags,
        "counts": counts,
    }


def file_review_for_client(client: Any, **kwargs) -> dict | None:
    """Resolve the client's profile and run the review. Returns None without a profile."""
    resolved = resolve_profile(client)
    if not resolved.get("is_set"):
        return None
    return evaluate_file_review(profile=resolved, **kwargs)
