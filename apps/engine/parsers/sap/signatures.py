from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

# Canonical SAP field -> exported header aliases.  SAP exports differ between
# ALV layouts, Fiori apps and technical field-name exports, so aliases are
# matched after normalising case and punctuation.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "company_code": (
        "company code",
        "co code",
        "cocd",
        "bukrs",
        "company code id",
    ),
    "gl_account": (
        "g/l account",
        "gl account",
        "g l account",
        "g/l acct",
        "gl acct",
        "g/l account number",
        "general ledger account",
        "hkont",
        "saknr",
        "racct",
    ),
    "account_name": (
        "account name",
        "g/l account name",
        "gl account name",
        "account description",
        "account text",
        "name of gl account",
    ),
    "account_number": (
        "account",
        "account number",
        "account no",
        "acct",
        "acct no",
        "account id",
    ),
    "document_number": (
        "document number",
        "document no",
        "doc no",
        "doc number",
        "accounting document",
        "accounting document number",
        "journal entry",
        "journal entry number",
        "voucher number",
        "voucher no",
        "belnr",
    ),
    "document_type": (
        "document type",
        "doc type",
        "voucher type",
        "blart",
        "document category",
    ),
    "posting_date": (
        "posting date",
        "post date",
        "posting dt",
        "budat",
        "date",
    ),
    "document_date": (
        "document date",
        "doc date",
        "bldat",
        "invoice date",
    ),
    "entry_date": (
        "entry date",
        "created on",
        "cpudt",
    ),
    "due_date": (
        "due date",
        "net due date",
        "payment due date",
        "due on",
        "net due",
        "faedt",
    ),
    "baseline_date": (
        "baseline date",
        "baseline",
        "zfbdt",
    ),
    "clearing_date": (
        "clearing date",
        "clearing doc date",
        "augdt",
    ),
    "clearing_document": (
        "clearing document",
        "clearing doc",
        "clearing document no",
        "augbl",
    ),
    "posting_key": (
        "posting key",
        "post key",
        "bschl",
        "pk",
    ),
    "reference": (
        "reference",
        "reference document",
        "reference no",
        "ref",
        "ref no",
        "xblnr",
    ),
    "assignment": (
        "assignment",
        "allocation",
        "zuonr",
    ),
    "description": (
        "description",
        "text",
        "item text",
        "line text",
        "narration",
        "particulars",
        "details",
        "document text",
        "sgtxt",
    ),
    "party_name": (
        "party name",
        "vendor name",
        "supplier name",
        "customer name",
        "debtor name",
        "creditor name",
        "name",
        "name 1",
        "name 2",
    ),
    "vendor_number": (
        "vendor",
        "vendor no",
        "vendor number",
        "vendor id",
        "supplier",
        "supplier no",
        "supplier number",
        "supplier id",
        "creditor",
        "creditor no",
        "lifnr",
    ),
    "customer_number": (
        "customer",
        "customer no",
        "customer number",
        "customer id",
        "debtor",
        "debtor no",
        "kunnr",
    ),
    "party_code": (
        "party code",
        "party number",
        "party no",
        "party id",
    ),
    "debit": (
        "debit",
        "debit amount",
        "debit amt",
        "debit in local currency",
        "debit local",
        "debit total",
        "dr",
        "dr amount",
        "soll",
    ),
    "credit": (
        "credit",
        "credit amount",
        "credit amt",
        "credit in local currency",
        "credit local",
        "credit total",
        "cr",
        "cr amount",
        "haben",
    ),
    "amount": (
        "amount",
        "amount in local currency",
        "amount in document currency",
        "local amount",
        "document amount",
        "doc amount",
        "transaction amount",
        "lc amount",
        "dc amount",
        "value",
        "amt",
        "dmbtr",
        "wrbtr",
    ),
    "balance": (
        "balance",
        "balance amount",
        "running balance",
        "cumulative balance",
        "balance in local currency",
        "balance lc",
        "balance dc",
        "outstanding",
        "outstanding amount",
        "open amount",
        "open balance",
    ),
    "opening_balance": (
        "opening balance",
        "opening bal",
        "balance brought forward",
        "brought forward",
        "b/f",
        "bf",
        "opening",
    ),
    "closing_balance": (
        "closing balance",
        "closing bal",
        "balance carried forward",
        "carried forward",
        "c/f",
        "cf",
        "closing",
    ),
    "currency": (
        "currency",
        "curr",
        "waers",
        "currency code",
        "document currency",
        "doc currency",
        "local currency",
    ),
    "fiscal_year": (
        "fiscal year",
        "fy",
        "gjahr",
        "year",
    ),
    "period": (
        "period",
        "fiscal period",
        "month",
        "poper",
    ),
    "debit_credit_indicator": (
        "debit/credit",
        "debit credit",
        "debit credit indicator",
        "debit or credit",
        "dr/cr",
        "db/cr",
        "d/c",
        "indicator",
        "shkzg",
    ),
    "invoice_number": (
        "invoice",
        "invoice no",
        "invoice number",
        "bill no",
        "bill number",
        "billing document",
        "invoice id",
        "sales document",
    ),
    "gstin": (
        "gstin",
        "gst no",
        "gst identification number",
    ),
    "tax_code": ("tax code", "tax", "mwskz"),
    "cost_center": ("cost center", "cost centre", "kostl"),
    "profit_center": ("profit center", "profit centre", "prctr"),
    "business_area": ("business area", "gsber"),
    "chart_of_accounts": ("chart of accounts", "coa", "ktopl"),
    "controlling_area": ("controlling area", "kokrs"),
    "special_gl_indicator": (
        "special g/l indicator",
        "special gl indicator",
        "umskz",
    ),
    "aging_current": ("current", "not due", "not due amount", "0 days"),
    "aging_1_30": ("1 30", "1 30 days", "0 30", "0 30 days"),
    "aging_31_60": ("31 60", "31 60 days"),
    "aging_61_90": ("61 90", "61 90 days"),
    "aging_91_120": ("91 120", "91 120 days"),
    "aging_over_120": (
        "over 120",
        "over 120 days",
        "120+",
        "above 120",
        "more than 120",
    ),
}

REPORT_LABELS = {
    "general_ledger": "General Ledger",
    "journal_entries": "Journal Entries",
    "trial_balance": "Trial Balance",
    "vendor": "Vendor / Supplier",
    "customer": "Customer",
    "accounts_payable": "Accounts Payable",
    "accounts_receivable": "Accounts Receivable",
    "other": "SAP financial ledger",
}

CORE_FIELDS = frozenset(
    {
        "company_code",
        "gl_account",
        "posting_key",
        "fiscal_year",
        "clearing_document",
        "chart_of_accounts",
        "controlling_area",
        "special_gl_indicator",
    }
)
STRONG_FIELDS = frozenset(
    {
        *CORE_FIELDS,
        "posting_date",
        "document_type",
        "cost_center",
        "profit_center",
        "business_area",
    }
)
FINANCIAL_FIELDS = frozenset(
    {
        "debit",
        "credit",
        "amount",
        "balance",
        "opening_balance",
        "closing_balance",
        "posting_date",
        "document_date",
        "due_date",
        "gl_account",
        "account_number",
        "vendor_number",
        "customer_number",
        "party_name",
        "invoice_number",
    }
)
AGING_FIELDS = frozenset(
    {
        "aging_current",
        "aging_1_30",
        "aging_31_60",
        "aging_61_90",
        "aging_91_120",
        "aging_over_120",
    }
)

# These aliases are too generic to promote a header on a prefix/contains match.
_GENERIC_ALIASES = frozenset(
    {
        "account",
        "acct",
        "date",
        "year",
        "month",
        "amount",
        "value",
        "balance",
        "name",
        "text",
        "reference",
        "ref",
        "indicator",
        "currency",
        "tax",
    }
)

_ALIAS_INDEX: dict[str, str] = {}
_ALIAS_ORDER: list[tuple[str, str]] = []
for _field, _aliases in FIELD_ALIASES.items():
    for _alias in _aliases:
        _normalised = " ".join(_alias.replace("/", " ").replace("-", " ").split())
        _ALIAS_INDEX.setdefault(_normalised, _field)
        if _normalised not in {item[0] for item in _ALIAS_ORDER}:
            _ALIAS_ORDER.append((_normalised, _field))
_ALIAS_ORDER.sort(key=lambda item: (-len(item[0].split()), -len(item[0])))

_SAP_BRAND_RE = re.compile(r"\b(?:sap|s/4hana|sap business one|sap fiori)\b", re.I)


@dataclass(frozen=True)
class SapSignature:
    confidence: float
    reason: str
    report_type: str


def normalize_header(value) -> str:
    text = "" if value is None else str(value)
    text = (
        text.replace("\u00a0", " ")
        .replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
        .lower()
    )
    text = re.sub(r"[^a-z0-9+ ]+", " ", text)
    return " ".join(text.split())


def normalize_context(value) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u00a0", " ").replace("[", " ").replace("]", " ")
    text = re.sub(r"[^A-Za-z0-9/+. ]+", " ", text)
    return " ".join(text.split())


def field_for_header(value) -> str | None:
    header = normalize_header(value)
    if not header:
        return None
    field = _ALIAS_INDEX.get(header)
    if field:
        return field
    # Headers such as "Posting Date (BUDAT)" or "Debit Amount LC" are common.
    for alias, candidate in _ALIAS_ORDER:
        if alias in _GENERIC_ALIASES:
            continue
        if header == alias:
            return candidate
        if header.startswith(alias + " ") or header.endswith(" " + alias):
            return candidate
    return None


def header_field_map(headers: Sequence) -> dict[int, str]:
    mapped: dict[int, str] = {}
    seen: set[str] = set()
    for index, header in enumerate(headers):
        field = field_for_header(header)
        if field is None or field in seen:
            continue
        mapped[index] = field
        seen.add(field)
    return mapped


def fields_for_headers(headers: Sequence) -> set[str]:
    return set(header_field_map(headers).values())


def score_header_fields(fields: Iterable[str]) -> int:
    values = set(fields)
    if len(values) < 2:
        return 0
    core = len(values & CORE_FIELDS)
    strong = len(values & STRONG_FIELDS)
    financial = len(values & FINANCIAL_FIELDS)
    if not core and strong < 2:
        return 0
    score = len(values) * 3 + core * 2 + strong * 2 + financial
    if not values & {"debit", "credit", "amount", "balance"}:
        score -= 4
    if not values & {"posting_date", "document_date", "due_date"}:
        score -= 2
    return score


def score_header_row(headers: Sequence) -> int:
    return score_header_fields(fields_for_headers(headers))


def detect_sap(
    headers: Sequence,
    *,
    context: str = "",
    filename: str = "",
) -> SapSignature | None:
    return _signature_from_fields(
        fields_for_headers(headers),
        context=context,
        filename=filename,
    )


def detect_sap_text(text: str, *, filename: str = "") -> SapSignature | None:
    context = normalize_context(text)
    fields: set[str] = set()
    for field, aliases in FIELD_ALIASES.items():
        specific = [
            alias
            for alias in aliases
            if normalize_header(alias) not in _GENERIC_ALIASES
        ]
        if field in CORE_FIELDS:
            # "Year" or "account" in prose must not imply an SAP core field.
            matched = any(_alias_in_text(context, alias) for alias in specific)
        else:
            matched = any(_alias_in_text(context, alias) for alias in aliases)
        if matched:
            fields.add(field)
    return _signature_from_fields(fields, context=text, filename=filename)


def _signature_from_fields(
    fields: set[str],
    *,
    context: str,
    filename: str,
) -> SapSignature | None:
    if not fields:
        return None
    core = len(fields & CORE_FIELDS)
    strong = len(fields & STRONG_FIELDS)
    financial = len(fields & FINANCIAL_FIELDS)
    combined_context = normalize_context(f"{context} {filename}")
    brand = bool(_SAP_BRAND_RE.search(combined_context))
    report_type = detect_report_type(fields, context=context, filename=filename)[0]
    titled = report_type != "other"

    if brand and core >= 1 and financial >= 2:
        confidence = 0.96
    elif core >= 2 and financial >= 2:
        confidence = 0.9
    elif core >= 1 and strong >= 3 and financial >= 3:
        confidence = 0.86
    elif titled and core >= 1 and financial >= 3:
        confidence = 0.84
    elif titled and core >= 1 and strong >= 2 and financial >= 2:
        confidence = 0.82
    else:
        return None

    reason_parts = [REPORT_LABELS.get(report_type, "SAP financial report")]
    if "gl_account" in fields:
        reason_parts.append("G/L account")
    elif "company_code" in fields:
        reason_parts.append("company code")
    if "posting_date" in fields:
        reason_parts.append("posting date")
    if {"debit", "credit"} <= fields:
        reason_parts.append("debit/credit")
    return SapSignature(
        confidence=confidence,
        reason="SAP export structure: " + ", ".join(reason_parts),
        report_type=report_type,
    )


def detect_report_type(
    fields: Iterable[str],
    *,
    context: str = "",
    filename: str = "",
) -> tuple[str, str]:
    values = set(fields)
    title = normalize_context(f"{context} {filename}").lower()

    if _has_any(title, ("accounts payable", "payable aging", "ap aging", "creditor aging")):
        return "accounts_payable", "title indicates accounts payable"
    if _has_any(
        title,
        ("accounts receivable", "receivable aging", "ar aging", "debtor aging"),
    ):
        return "accounts_receivable", "title indicates accounts receivable"
    if _has_any(title, ("trial balance", "closing balances")):
        return "trial_balance", "title indicates trial balance"
    if _has_any(
        title,
        ("journal entry", "journal entries", "journal line", "je line", "accounting document"),
    ):
        return "journal_entries", "title indicates journal entries"
    if _has_any(
        title,
        ("general ledger", "g/l line", "gl line", "ledger line", "line item display"),
    ):
        return "general_ledger", "title indicates general ledger"

    vendor = bool(values & {"vendor_number"})
    customer = bool(values & {"customer_number"})
    aging = bool(values & AGING_FIELDS)
    open_item = _has_any(title, ("open item", "open items", "due date", "aging"))
    if vendor and aging:
        return "accounts_payable", "vendor aging headers"
    if customer and aging:
        return "accounts_receivable", "customer aging headers"
    if vendor and open_item:
        return "accounts_payable", "vendor open-item headers"
    if customer and open_item:
        return "accounts_receivable", "customer open-item headers"
    if (
        "opening_balance" in values
        and ("closing_balance" in values or "balance" in values)
        and (values & {"gl_account", "account_number", "account_name"})
    ):
        return "trial_balance", "opening and closing balance headers"
    if vendor and (
        _has_any(title, ("vendor", "supplier", "creditor"))
        or values & {"debit", "credit", "balance", "amount"}
    ):
        return "vendor", "vendor account headers"
    if customer and (
        _has_any(title, ("customer", "debtor"))
        or values & {"debit", "credit", "balance", "amount"}
    ):
        return "customer", "customer account headers"
    if "gl_account" in values and (
        "posting_date" in values
        or "document_date" in values
        or "document_number" in values
        or values & {"debit", "credit", "amount", "balance"}
    ):
        return "general_ledger", "G/L account line-item headers"
    if "account_number" in values and values & {"debit", "credit", "balance"}:
        return "general_ledger", "ledger account headers"
    return "other", "SAP financial headers without a recognised report title"


def report_label(report_type: str) -> str:
    return REPORT_LABELS.get(report_type, REPORT_LABELS["other"])


def _alias_in_text(text: str, alias: str) -> bool:
    needle = normalize_header(alias)
    if not needle:
        return False
    haystack = normalize_header(text)
    return f" {needle} " in f" {haystack} "


def _has_any(text: str, needles: Iterable[str]) -> bool:
    padded = f" {text} "
    return any(f" {needle} " in padded for needle in needles)
