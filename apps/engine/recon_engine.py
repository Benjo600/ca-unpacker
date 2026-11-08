"""Reusable, explainable reconciliation matching engine.

This module is deliberately free of database and UI imports.  It takes plain
row dictionaries, applies a versioned rule configuration, and returns match
proposals with evidence, confidence, tolerances and explanations.  Persistence
and workflow orchestration live in :mod:`apps.engine.recon_service`.

Design rules
------------
* A source record is allocated at most once per run.  One-to-many and
  many-to-one proposals are explicit allocations and are never auto-confirmed.
* Amount similarity on its own never creates a match.  A reference, GSTIN,
  counterparty or narration-reference signal must support it.
* Currencies are never converted.  A currency mismatch is a review item.
* Duplicate records are surfaced, never paired arbitrarily.
* Reversals are candidates only.  Opposite amounts are not proof of a reversal.
* Results are deterministic for the same inputs and rule snapshot.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

ENGINE_VERSION = "2.0"
ZERO = Decimal("0")
DEFAULT_RULES: dict[str, Any] = {
    "amount_tolerance": 1.0,
    "date_tolerance_days": 30,
    "reference_date_tolerance_days": 45,
    "bank_date_tolerance_days": 45,
    "fuzzy_date_tolerance_days": 3,
    "review_threshold": 60,
    "auto_accept_threshold": 85,
    "allow_one_to_many": True,
    "allow_many_to_one": True,
    "allow_partial": True,
    "detect_duplicates": True,
    "detect_reversals": True,
    "normalize_references": True,
    "gstin_validation": True,
    "max_allocation_items": 4,
    "weights": {
        "reference": 30,
        "gstin": 18,
        "amount": 25,
        "date": 10,
        "party": 9,
        "tax": 8,
    },
}

CLASSIFICATION_LABELS = {
    "exact": "Exact Match",
    "strong": "Strong Match",
    "probable": "Probable Match",
    "partial": "Partial Match",
    "review": "Requires Review",
    "unmatched": "Unmatched",
    "duplicate": "Duplicate",
    "reversal_candidate": "Reversal Candidate",
    "manual": "Manual Match",
}

STATUS_LABELS = {
    "matched": "Matched",
    "proposed": "Proposed",
    "unmatched": "Unmatched",
    "duplicate": "Duplicate",
    "reversal_candidate": "Reversal candidate",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "manual": "Manual match",
    "timing_difference": "Timing difference",
    "approved_adjustment": "Approved adjustment",
    "superseded": "Superseded",
}

EXCEPTION_LABELS = {
    "unmatched_transaction": "Unmatched transaction",
    "amount_mismatch": "Amount mismatch",
    "date_mismatch": "Date mismatch",
    "reference_mismatch": "Reference mismatch",
    "gstin_mismatch": "GSTIN mismatch",
    "gstin_invalid": "GSTIN format invalid",
    "place_of_supply_mismatch": "Place of supply mismatch",
    "duplicate_records": "Duplicate records",
    "partial_settlement": "Partial settlement",
    "missing_source_data": "Missing source data",
    "currency_mismatch": "Currency mismatch",
    "possible_reversal": "Possible reversal",
    "multiple_possible_matches": "Multiple possible matches",
    "allocation_required": "Allocation required",
    "timing_difference": "Timing difference",
    "bank_charge_interest": "Bank charge / interest",
    "balance_variance": "Balance variance",
}

_DATE_FMTS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y%m%d",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d/%b/%Y",
    "%d %B %Y",
    "%b %d, %Y",
)
_REFERENCE_KEYS = (
    "invoice_number",
    "voucher_number",
    "bill_number",
    "document_number",
    "reference",
    "utr",
    "cheque_ref",
    "payment_reference",
    "clearing_document",
)
_GSTIN_KEYS = (
    "supplier_gstin",
    "customer_gstin",
    "party_gstin",
    "gstin",
)
_PARTY_KEYS = (
    "supplier_name",
    "party_name",
    "trade_name",
    "customer_name",
    "vendor_name",
    "account_name",
    "ledger_name",
)
_DATE_KEYS = (
    "invoice_date",
    "voucher_date",
    "posting_date",
    "document_date",
    "transaction_date",
    "value_date",
    "date",
)
_AMOUNT_KEYS = ("invoice_value", "amount", "total", "net_amount", "gross_amount")
_TAXABLE_KEYS = ("taxable_value", "taxable", "assessable_value")
_TAX_KEYS = ("tax", "tax_amount")
_CURRENCY_KEYS = ("currency_code", "currency")
_DESCRIPTION_KEYS = ("description", "narration", "detail", "particulars")
_DOCUMENT_TYPE_KEYS = ("document_type", "voucher_type", "type")
_BANK_DEBIT_KEYS = ("debit", "withdrawal", "withdrawals", "paid_out")
_BANK_CREDIT_KEYS = ("credit", "deposit", "deposits", "paid_in")
_OUTFLOW_VOUCHERS = ("payment", "paid", "debit note", "purchase")
_INFLOW_VOUCHERS = ("receipt", "received", "credit note", "sales")
_NETWORK_ROOTS = {"requests", "httpx", "urllib", "aiohttp", "socket", "http"}


# ---------------------------------------------------------------------------
# Normalisation and safe parsing
# ---------------------------------------------------------------------------


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_reference(value: Any) -> str:
    """Normalise invoice/voucher references without guessing their meaning.

    Spaces, punctuation and case are irrelevant.  Each numeric run loses
    leading zeros, so ``INV/001`` and ``inv-1`` compare equal while the
    original display value is always preserved separately.
    """

    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text:
        return ""
    text = (
        text.replace("₹", "")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("—", "-")
    )
    compact = re.sub(r"[^A-Z0-9]+", "", text)

    def _trim_zeros(match: re.Match[str]) -> str:
        digits = match.group(0).lstrip("0")
        return digits or "0"

    return re.sub(r"\d+", _trim_zeros, compact)


def normalize_gstin(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()


_GSTIN_STRUCTURE_RE = re.compile(
    r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]$"
)


def gstin_structure_valid(value: Any) -> bool:
    text = normalize_gstin(value)
    return bool(text) and bool(_GSTIN_STRUCTURE_RE.fullmatch(text))


def normalize_currency(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Za-z]", "", str(value)).upper()[:3]


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text and re.match(r"^\d{4}-\d{2}-\d{2} ", text):
        text = text.split(" ", 1)[0]
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parts = re.split(r"[/\-.]", text)
    if len(parts) == 3 and all(parts):
        try:
            first, second, third = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if first > 31:
            year, month, day = first, second, third
        else:
            day, month, year = first, second, third
            if year < 100:
                year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    # Excel serial dates arrive as numbers.
    try:
        serial = int(float(text))
    except (TypeError, ValueError):
        return None
    if 20000 <= serial <= 80000:
        from datetime import timedelta

        return date(1899, 12, 30) + timedelta(days=serial)
    return None


def parse_money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = (
        text.replace("₹", "")
        .replace("$", "")
        .replace("₹", "")
        .replace(",", "")
        .replace(" ", "")
        .replace("Dr.", "")
        .replace("Cr.", "")
        .replace("Dr", "")
        .replace("Cr", "")
    )
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", "-", ".", "-."}:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if negative and number > 0:
        number = -number
    return number


def _first_text(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            text = normalize_text(value)
            if text:
                return text
    return ""


def _first_money(row: Mapping[str, Any], keys: Sequence[str]) -> Decimal | None:
    for key in keys:
        if key in row:
            value = parse_money(row.get(key))
            if value is not None:
                return value
    return None


def _first_date(row: Mapping[str, Any], keys: Sequence[str]) -> date | None:
    for key in keys:
        if key in row:
            parsed = parse_date(row.get(key))
            if parsed is not None:
                return parsed
    return None


def _meta(row: Mapping[str, Any], key: str) -> Any:
    return row.get(f"_ca_{key}")


def _public_raw(row: Mapping[str, Any]) -> dict:
    return {
        str(key): value
        for key, value in row.items()
        if not str(key).startswith("_ca_")
    }


def _amount_difference(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return (left - right).copy_abs()


def _place_key(value: str) -> str:
    text = normalize_text(value).upper()
    match = re.match(r"^(\d{2})", text)
    return match.group(1) if match else text


def _date_difference(left: date | None, right: date | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left - right).days)


def _token_set(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z]{3,}", (value or "").upper())
        if token not in {"THE", "AND", "LIMITED", "LTD", "PRIVATE", "PVT", "COMPANY", "CO"}
    }


def party_overlap(left: str, right: str) -> tuple[int, bool]:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    shared = left_tokens & right_tokens
    distinctive = any(len(token) >= 5 for token in shared)
    return len(shared), distinctive


def reference_prefix(left: str, right: str) -> bool:
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < 4:
        return False
    return longer.startswith(shorter) or longer.endswith(shorter)


def _signed_direction(row: Mapping[str, Any], amount: Decimal | None) -> str:
    debit = _first_money(row, _BANK_DEBIT_KEYS)
    credit = _first_money(row, _BANK_CREDIT_KEYS)
    if debit is not None and debit != 0:
        return "debit"
    if credit is not None and credit != 0:
        return "credit"
    if amount is not None and amount < 0:
        return "credit"
    voucher = _first_text(row, ("voucher_type", "document_type", "type")).lower()
    if any(marker in voucher for marker in _INFLOW_VOUCHERS):
        return "credit"
    if any(marker in voucher for marker in _OUTFLOW_VOUCHERS):
        return "debit"
    return ""


def _row_amount(row: Mapping[str, Any]) -> Decimal | None:
    debit = _first_money(row, _BANK_DEBIT_KEYS)
    credit = _first_money(row, _BANK_CREDIT_KEYS)
    if debit is not None and debit != 0:
        return debit.copy_abs()
    if credit is not None and credit != 0:
        return credit.copy_abs()
    amount = _first_money(row, _AMOUNT_KEYS)
    return amount.copy_abs() if amount is not None else None


def _tax_components(row: Mapping[str, Any]) -> dict[str, Decimal | None]:
    return {
        "igst": _first_money(row, ("igst", "integrated_tax")),
        "cgst": _first_money(row, ("cgst", "central_tax")),
        "sgst": _first_money(row, ("sgst", "state_tax", "utgst")),
        "cess": _first_money(row, ("cess",)),
    }


def _tax_total(row: Mapping[str, Any]) -> Decimal | None:
    direct = _first_money(row, _TAX_KEYS)
    if direct is not None:
        return direct
    parts = [value for value in _tax_components(row).values() if value is not None]
    return sum(parts, ZERO) if parts else None


def _normalise_rule_number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def normalise_rules(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a complete, validated rule snapshot with safe bounds."""

    source = dict(DEFAULT_RULES)
    incoming = dict(config or {})
    weights = dict(DEFAULT_RULES["weights"])
    if isinstance(incoming.get("weights"), Mapping):
        weights.update(
            {
                str(key): _normalise_rule_number(value, weights.get(key, 0))
                for key, value in incoming["weights"].items()
                if key in weights
            }
        )
    source.update({key: value for key, value in incoming.items() if key != "weights"})
    source["weights"] = weights
    for key, label in (
        ("amount_tolerance", 0.0),
        ("date_tolerance_days", 0.0),
        ("reference_date_tolerance_days", 0.0),
        ("bank_date_tolerance_days", 0.0),
        ("fuzzy_date_tolerance_days", 0.0),
        ("review_threshold", 0.0),
        ("auto_accept_threshold", 0.0),
        ("max_allocation_items", 2.0),
    ):
        value = _normalise_rule_number(source.get(key), DEFAULT_RULES[key])
        source[key] = value
    source["amount_tolerance"] = max(0.0, source["amount_tolerance"])
    for key in (
        "date_tolerance_days",
        "reference_date_tolerance_days",
        "bank_date_tolerance_days",
        "fuzzy_date_tolerance_days",
    ):
        source[key] = int(max(0, source[key]))
    source["max_allocation_items"] = int(
        min(8, max(2, source["max_allocation_items"]))
    )
    source["review_threshold"] = min(100, max(0, source["review_threshold"]))
    source["auto_accept_threshold"] = min(
        100, max(source["review_threshold"], source["auto_accept_threshold"])
    )
    for key in (
        "allow_one_to_many",
        "allow_many_to_one",
        "allow_partial",
        "detect_duplicates",
        "detect_reversals",
        "normalize_references",
        "gstin_validation",
    ):
        source[key] = bool(source.get(key, DEFAULT_RULES[key]))
    total_weight = sum(max(0.0, float(value)) for value in weights.values())
    if total_weight <= 0:
        weights = dict(DEFAULT_RULES["weights"])
    source["weights"] = weights
    return source


def rule_summary(config: Mapping[str, Any] | None) -> list[str]:
    rules = normalise_rules(config)
    notes = [
        f"Amount tolerance: ₹{rules['amount_tolerance']:,.2f}.",
        f"Date tolerance: {rules['date_tolerance_days']} days (bank reference window {rules['bank_date_tolerance_days']} days).",
        "Invoice/voucher references are normalised for case, spaces, punctuation and leading zeros."
        if rules["normalize_references"]
        else "Reference normalisation is disabled.",
        f"Review threshold: confidence {rules['review_threshold']} and above can be proposed; below that a row needs manual investigation.",
        f"Auto-confirm threshold: only exact/strong evidence at {rules['auto_accept_threshold']} or above is treated as matched.",
        "One-to-many allocations are supported but always require review."
        if rules["allow_one_to_many"]
        else "One-to-many allocations are disabled.",
        "Partial settlements are detected where a reference and amount support them."
        if rules["allow_partial"]
        else "Partial settlement detection is disabled.",
        "Currencies are never converted; mismatches are review items.",
    ]
    return notes


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineRecord:
    index: int
    side: str
    row: Mapping[str, Any]
    row_id: int | None
    file_id: int | None
    file_name: str
    kind: str
    source: str
    page: int | None
    bbox: str | None
    reference_display: str
    reference: str
    gstin: str
    party: str
    date: date | None
    date_display: str
    amount: Decimal | None
    taxable: Decimal | None
    tax: Decimal | None
    tax_parts: Mapping[str, Decimal | None]
    currency: str
    direction: str
    description: str
    document_type: str

    def public(self) -> dict:
        return {
            "row_id": self.row_id,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "kind": self.kind,
            "reference": self.reference_display,
            "normalized_reference": self.reference,
            "gstin": self.gstin,
            "party": self.party,
            "date": self.date_display,
            "amount": _float(self.amount),
            "taxable": _float(self.taxable),
            "tax": _float(self.tax),
            "igst": _float(self.tax_parts.get("igst")),
            "cgst": _float(self.tax_parts.get("cgst")),
            "sgst": _float(self.tax_parts.get("sgst")),
            "cess": _float(self.tax_parts.get("cess")),
            "currency": self.currency,
            "direction": self.direction,
            "description": self.description,
            "document_type": self.document_type,
            "source": self.source,
            "source_page": self.page,
            "source_bbox": self.bbox,
            "raw": _public_raw(self.row),
        }

    def search_text(self) -> str:
        parts = [
            self.reference_display,
            self.reference,
            self.gstin,
            self.party,
            self.date_display,
            self.description,
            self.file_name,
            self.source,
            self.currency,
            self.document_type,
        ]
        return " ".join(str(part) for part in parts if part).upper()


def build_record(row: Mapping[str, Any], index: int, side: str) -> EngineRecord:
    reference_display = _first_text(row, _REFERENCE_KEYS)
    amount = _row_amount(row)
    parsed_date = _first_date(row, _DATE_KEYS)
    date_raw = _first_text(row, _DATE_KEYS)
    return EngineRecord(
        index=index,
        side=side,
        row=row,
        row_id=_coerce_int(_meta(row, "row_id")),
        file_id=_coerce_int(_meta(row, "file_id")),
        file_name=normalize_text(_meta(row, "file_name") or row.get("file_name")),
        kind=normalize_text(_meta(row, "kind") or row.get("kind")),
        source=_first_text(row, ("source",)),
        page=_coerce_int(_meta(row, "page") or row.get("source_page")),
        bbox=normalize_text(_meta(row, "bbox") or row.get("source_bbox")) or None,
        reference_display=reference_display,
        reference=normalize_reference(reference_display),
        gstin=normalize_gstin(_first_text(row, _GSTIN_KEYS)),
        party=_first_text(row, _PARTY_KEYS),
        date=parsed_date,
        date_display=parsed_date.isoformat() if parsed_date else date_raw,
        amount=amount,
        taxable=_first_money(row, _TAXABLE_KEYS),
        tax=_tax_total(row),
        tax_parts=_tax_components(row),
        currency=normalize_currency(_first_text(row, _CURRENCY_KEYS)),
        direction=_signed_direction(row, amount),
        description=_first_text(row, _DESCRIPTION_KEYS),
        document_type=_first_text(row, _DOCUMENT_TYPE_KEYS),
    )


def _apply_reference_policy(
    records: Sequence[EngineRecord], rules: Mapping[str, Any]
) -> list[EngineRecord]:
    if rules.get("normalize_references", True):
        return list(records)
    return [
        replace(record, reference=normalize_text(record.reference_display))
        for record in records
    ]


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _is_credit_note(record: EngineRecord) -> bool:
    # Document type is the reliable signal.  A reference that merely starts
    # with "CN" is not enough; invoice series can legitimately use CN-001.
    marker = f"{record.document_type}".upper()
    if any(token in marker for token in ("CDN", "CREDIT NOTE", "CRNOTE", "CREDIT_MEMO")):
        return True
    raw = _first_money(record.row, _AMOUNT_KEYS)
    return raw is not None and raw < 0


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------


@dataclass
class MatchProposal:
    left: list[EngineRecord] = field(default_factory=list)
    right: list[EngineRecord] = field(default_factory=list)
    classification: str = "review"
    status: str = "proposed"
    match_type: str = "none"
    confidence: int = 0
    requires_review: bool = True
    reason_code: str = ""
    explanation: str = ""
    matched_fields: list[dict] = field(default_factory=list)
    differences: dict = field(default_factory=dict)
    tolerances: list[str] = field(default_factory=list)
    exception_categories: list[str] = field(default_factory=list)
    candidates: list[EngineRecord] = field(default_factory=list)
    allocations: list[dict] = field(default_factory=list)
    rule_notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "left": [record.public() for record in self.left],
            "right": [record.public() for record in self.right],
            "left_ids": [record.row_id for record in self.left if record.row_id],
            "right_ids": [record.row_id for record in self.right if record.row_id],
            "candidates": [record.public() for record in self.candidates],
            "classification": self.classification,
            "classification_label": CLASSIFICATION_LABELS.get(
                self.classification, self.classification
            ),
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "match_type": self.match_type,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "matched_fields": self.matched_fields,
            "differences": self.differences,
            "tolerances": self.tolerances,
            "exception_categories": self.exception_categories,
            "allocations": self.allocations,
        }


def _base_differences(left: EngineRecord | None, right: EngineRecord | None) -> dict:
    amount_diff = _amount_difference(
        left.amount if left else None, right.amount if right else None
    )
    taxable_diff = _amount_difference(
        left.taxable if left else None, right.taxable if right else None
    )
    tax_diff = _amount_difference(
        left.tax if left else None, right.tax if right else None
    )
    signed = None
    if left and right and left.amount is not None and right.amount is not None:
        signed = left.amount - right.amount
    return {
        "amount": _float(amount_diff),
        "amount_signed": _float(signed),
        "taxable": _float(taxable_diff),
        "tax": _float(tax_diff),
        "igst": _float(
            _amount_difference(
                left.tax_parts.get("igst") if left else None,
                right.tax_parts.get("igst") if right else None,
            )
        ),
        "cgst": _float(
            _amount_difference(
                left.tax_parts.get("cgst") if left else None,
                right.tax_parts.get("cgst") if right else None,
            )
        ),
        "sgst": _float(
            _amount_difference(
                left.tax_parts.get("sgst") if left else None,
                right.tax_parts.get("sgst") if right else None,
            )
        ),
        "cess": _float(
            _amount_difference(
                left.tax_parts.get("cess") if left else None,
                right.tax_parts.get("cess") if right else None,
            )
        ),
        "date_days": _date_difference(
            left.date if left else None, right.date if right else None
        ),
        "outstanding": None,
    }


def _field_entry(
    field: str,
    left_value: Any,
    right_value: Any,
    matched: bool | None,
    note: str = "",
) -> dict:
    return {
        "field": field,
        "left": left_value,
        "right": right_value,
        "matched": matched,
        "note": note,
    }


def _matched_fields(
    left: EngineRecord,
    right: EngineRecord,
    rules: Mapping[str, Any],
    *,
    reference_hit: bool | None = None,
    bank_reference: bool = False,
) -> list[dict]:
    tolerance = Decimal(str(rules["amount_tolerance"]))
    fields: list[dict] = []
    exact_reference = bool(left.reference and right.reference and left.reference == right.reference)
    if bank_reference:
        reference_match = True
    elif exact_reference:
        reference_match = True
    elif reference_hit:
        reference_match = True
    elif reference_prefix(left.reference, right.reference):
        reference_match = None
    elif left.reference and right.reference:
        reference_match = False
    else:
        reference_match = None
    fields.append(
        _field_entry(
            "Reference",
            left.reference_display or left.description,
            right.reference_display or right.description,
            reference_match,
            "Narration reference found" if bank_reference else (
                "Normalised references agree" if exact_reference else (
                    "Reference prefix overlaps" if reference_match is None else ""
                )
            ),
        )
    )
    if left.gstin or right.gstin:
        gstin_match = (
            True
            if left.gstin and right.gstin and left.gstin == right.gstin
            else None
            if not left.gstin or not right.gstin
            else False
        )
        fields.append(_field_entry("GSTIN", left.gstin, right.gstin, gstin_match))
        if rules.get("gstin_validation") and (
            (left.gstin and not gstin_structure_valid(left.gstin))
            or (right.gstin and not gstin_structure_valid(right.gstin))
        ):
            fields.append(
                _field_entry(
                    "GSTIN format",
                    "invalid" if left.gstin and not gstin_structure_valid(left.gstin) else "valid",
                    "invalid" if right.gstin and not gstin_structure_valid(right.gstin) else "valid",
                    False,
                    "GSTIN does not match the 15-character structural format",
                )
            )
    amount_diff = _amount_difference(left.amount, right.amount)
    fields.append(
        _field_entry(
            "Amount",
            _float(left.amount),
            _float(right.amount),
            None if amount_diff is None else amount_diff <= tolerance,
            "No readable amount on one side" if amount_diff is None else (
                f"Difference ₹{amount_diff:,.2f} within tolerance"
                if amount_diff <= tolerance
                else f"Difference ₹{amount_diff:,.2f} exceeds tolerance"
            ),
        )
    )
    date_diff = _date_difference(left.date, right.date)
    date_window = int(rules["bank_date_tolerance_days"] if bank_reference else rules["date_tolerance_days"])
    fields.append(
        _field_entry(
            "Date",
            left.date_display,
            right.date_display,
            None if date_diff is None else date_diff <= date_window,
            "Date missing on one side" if date_diff is None else (
                f"{date_diff} day(s) apart" if date_diff else "Same date"
            ),
        )
    )
    overlap, distinctive = party_overlap(left.party, right.party)
    party_match = True if overlap and distinctive else (True if overlap >= 2 else (None if not left.party or not right.party else False))
    fields.append(_field_entry("Party", left.party, right.party, party_match, "Token overlap" if overlap else ""))
    left_pos = _first_text(left.row, ("place_of_supply", "pos"))
    right_pos = _first_text(right.row, ("place_of_supply", "pos"))
    if left_pos or right_pos:
        pos_match = (
            None
            if not left_pos or not right_pos
            else _place_key(left_pos) == _place_key(right_pos)
        )
        fields.append(
            _field_entry(
                "Place of supply",
                left_pos,
                right_pos,
                pos_match,
                "State code compared where present",
            )
        )
    left_itc = _first_text(left.row, ("itc_availability", "itc_eligible", "itc"))
    right_itc = _first_text(right.row, ("itc_availability", "itc_eligible", "itc"))
    if left_itc or right_itc:
        fields.append(
            _field_entry(
                "ITC flag",
                left_itc,
                right_itc,
                None,
                "System flag only; no ITC eligibility conclusion is made",
            )
        )
    if left.document_type or right.document_type:
        fields.append(
            _field_entry(
                "Document type",
                left.document_type,
                right.document_type,
                None,
                "Source document classification is preserved; the engine does not reclassify it",
            )
        )
    if left.taxable is not None or right.taxable is not None:
        taxable_diff = _amount_difference(left.taxable, right.taxable)
        fields.append(
            _field_entry(
                "Taxable value",
                _float(left.taxable),
                _float(right.taxable),
                None if taxable_diff is None else taxable_diff <= tolerance,
                "" if taxable_diff is None else f"Difference ₹{taxable_diff:,.2f}",
            )
        )
    for component in ("igst", "cgst", "sgst", "cess"):
        left_value = left.tax_parts.get(component)
        right_value = right.tax_parts.get(component)
        if left_value is None and right_value is None:
            continue
        diff = _amount_difference(left_value, right_value)
        fields.append(
            _field_entry(
                component.upper(),
                _float(left_value),
                _float(right_value),
                None if diff is None else diff <= tolerance,
                "" if diff is None else f"Difference ₹{diff:,.2f}",
            )
        )
    if left.currency or right.currency:
        currency_match = (
            True
            if left.currency and right.currency and left.currency == right.currency
            else None
            if not left.currency or not right.currency
            else False
        )
        fields.append(_field_entry("Currency", left.currency, right.currency, currency_match, "No conversion is performed"))
    if left.direction or right.direction:
        direction_match = (
            True
            if left.direction and right.direction and left.direction == right.direction
            else None
            if not left.direction or not right.direction
            else False
        )
        fields.append(_field_entry("Direction", left.direction, right.direction, direction_match))
    return fields


def _tolerance_notes(
    left: EngineRecord,
    right: EngineRecord,
    rules: Mapping[str, Any],
    differences: Mapping[str, Any],
    *,
    bank_reference: bool = False,
) -> list[str]:
    tolerance = float(rules["amount_tolerance"])
    notes: list[str] = []
    if left.amount is None or right.amount is None:
        notes.append("Amount tolerance could not be applied because one side has no readable amount.")
    else:
        diff = float(differences.get("amount") or 0)
        verdict = "within" if diff <= tolerance else "outside"
        notes.append(
            f"Amount tolerance ₹{tolerance:,.2f} applied: difference ₹{diff:,.2f} is {verdict} tolerance."
        )
    if left.date is not None and right.date is not None:
        window = (
            rules["bank_date_tolerance_days"]
            if bank_reference
            else rules["date_tolerance_days"]
        )
        diff_days = differences.get("date_days") or 0
        verdict = "within" if diff_days <= window else "outside"
        notes.append(
            f"Date tolerance {window} days applied: gap {diff_days} day(s) is {verdict} tolerance."
        )
    else:
        notes.append("Date tolerance was not applied because one side has no readable date.")
    if any(differences.get(key) is not None for key in ("tax", "taxable", "igst", "cgst", "sgst", "cess")):
        notes.append(
            f"Tax and taxable components are compared using the same ₹{tolerance:,.2f} tolerance."
        )
    if left.currency and right.currency and left.currency != right.currency:
        notes.append("Currency mismatch flagged; no conversion was performed.")
    return notes


def _weighted_score(fields: Sequence[Mapping[str, Any]], rules: Mapping[str, Any]) -> int:
    weights = rules.get("weights") or DEFAULT_RULES["weights"]
    mapping = {
        "Reference": "reference",
        "GSTIN": "gstin",
        "Amount": "amount",
        "Date": "date",
        "Party": "party",
        "Taxable value": "tax",
        "IGST": "tax",
        "CGST": "tax",
        "SGST": "tax",
        "CESS": "tax",
    }
    # Only fields that could actually be compared count towards the
    # denominator.  A vendor statement often has no GSTIN; that absence must
    # not make a clean reference+amount+date+party match look weak.
    comparable: set[str] = set()
    matched: set[str] = set()
    for entry in fields:
        key = mapping.get(str(entry.get("field")))
        if not key:
            continue
        state = entry.get("matched")
        if state is not None:
            comparable.add(key)
            if state is True:
                matched.add(key)
    total_weight = sum(float(weights.get(key) or 0) for key in comparable)
    if total_weight <= 0:
        return 0
    score = sum(float(weights.get(key) or 0) for key in matched)
    return max(0, min(100, int(round(score * 100.0 / total_weight))))


def _evaluate_pair(
    left: EngineRecord,
    right: EngineRecord,
    rules: Mapping[str, Any],
    *,
    bank_reference: bool = False,
    reference_hit: bool | None = None,
    partial_allowed: bool = False,
) -> MatchProposal:
    fields = _matched_fields(
        left, right, rules, reference_hit=reference_hit, bank_reference=bank_reference
    )
    differences = _base_differences(left, right)
    tolerances = _tolerance_notes(
        left, right, rules, differences, bank_reference=bank_reference
    )
    tolerance = Decimal(str(rules["amount_tolerance"]))
    score = _weighted_score(fields, rules)
    ref_entry = fields[0] if fields else {}
    exact_reference = bool(
        left.reference and right.reference and left.reference == right.reference
    )
    ref_state = ref_entry.get("matched")
    gstin_state = next((f.get("matched") for f in fields if f["field"] == "GSTIN"), None)
    amount_state = next((f.get("matched") for f in fields if f["field"] == "Amount"), None)
    date_state = next((f.get("matched") for f in fields if f["field"] == "Date"), None)
    party_state = next((f.get("matched") for f in fields if f["field"] == "Party"), None)
    currency_state = next((f.get("matched") for f in fields if f["field"] == "Currency"), None)
    direction_state = next((f.get("matched") for f in fields if f["field"] == "Direction"), None)
    place_state = next((f.get("matched") for f in fields if f["field"] == "Place of supply"), None)
    if bank_reference and ref_state is True and amount_state is True:
        # A bank/UTR/cheque reference plus an agreeing amount is strong direct
        # evidence, even when the counterparty name is absent from one side.
        score = max(score, 95 if date_state is not False else 82)
    tax_states = [
        f.get("matched")
        for f in fields
        if f["field"] in {"Taxable value", "IGST", "CGST", "SGST", "CESS"}
        and f.get("matched") is not None
    ]
    reason = "values_agree"
    explanation = ""
    classification = "review"
    match_type = "reference" if bank_reference else "normalized"
    requires_review = True

    currency_conflict = currency_state is False
    gstin_conflict = gstin_state is False
    gstin_invalid = bool(rules.get("gstin_validation")) and (
        (left.gstin and not gstin_structure_valid(left.gstin))
        or (right.gstin and not gstin_structure_valid(right.gstin))
    )
    direction_conflict = direction_state is False
    amount_diff = differences.get("amount")
    amount_conflict = amount_state is False
    tax_conflict = any(state is False for state in tax_states)
    date_conflict = date_state is False
    reference_conflict = ref_state is False

    if currency_conflict:
        reason = "currency_mismatch"
        explanation = (
            "The records point to the same transaction but their currencies differ. "
            "No conversion is performed; a professional must review the currency before relying on this match."
        )
        score = min(score, 55)
    elif gstin_invalid:
        reason = "gstin_invalid"
        explanation = (
            "A GSTIN on one side does not match the 15-character structural format. "
            "The identifier cannot be relied on until the source master data is corrected."
        )
        score = min(score, 65)
    elif gstin_conflict:
        reason = "gstin_mismatch"
        explanation = (
            "The reference and amount agree but the GSTIN identifiers differ. "
            "This may be a supplier identification issue; confirm before accepting."
        )
        score = min(score, 60)
    elif amount_state is None:
        reason = "amount_missing"
        explanation = (
            "The reference agrees but one side has no readable amount. "
            "The match cannot be confirmed until the amount is verified."
        )
        score = min(score, 45)
    elif amount_conflict:
        outstanding = differences.get("amount") or 0
        if (
            partial_allowed
            and rules.get("allow_partial")
            and (exact_reference or bank_reference)
            and not currency_conflict
            and date_state is not False
        ):
            classification = "partial"
            match_type = "partial"
            reason = "partial_settlement"
            differences["outstanding"] = outstanding
            explanation = (
                f"The reference agrees but the amounts differ by ₹{outstanding:,.2f}. "
                "This is a partial-settlement candidate; the outstanding balance is calculated, not written back."
            )
            score = min(95, max(score, 70))
        else:
            reason = "amount_mismatch"
            classification = "review"
            match_type = "tolerance"
            explanation = (
                f"The reference/identifier agrees but the total differs by ₹{outstanding:,.2f}. "
                "The difference is outside the configured tolerance and needs investigation."
            )
            score = min(score, 60)
    elif tax_conflict:
        reason = "tax_difference"
        explanation = (
            "The total agrees but one or more tax/taxable components differ outside tolerance. "
            "Confirm the tax treatment before accepting."
        )
        score = min(score, 75)
    elif date_conflict:
        reason = "date_difference"
        explanation = (
            "The reference and amount agree but the dates are outside the configured tolerance. "
            "Check whether this is a timing difference."
        )
        score = min(score, 78)
    elif direction_conflict:
        reason = "direction_mismatch"
        explanation = (
            "The reference and amount agree but the debit/credit direction differs. "
            "Confirm the voucher and bank direction before accepting."
        )
        score = min(score, 55)
    elif place_state is False:
        reason = "place_of_supply_differs"
        explanation = (
            "The invoice identifiers and amount agree but the place-of-supply state code differs. "
            "Confirm the correct place of supply before accepting."
        )
        score = min(score, 72)
    elif reference_conflict and not exact_reference:
        if reference_prefix(left.reference, right.reference) and amount_state:
            reason = "reference_prefix"
            classification = "probable"
            match_type = "normalized"
            explanation = (
                "The references share a prefix/suffix and the amount agrees, but the references are not identical. "
                "A human must confirm this probable match."
            )
            score = min(84, max(score, 65))
        elif party_state is True and date_state is not False and (gstin_state is True or gstin_state is None):
            reason = "party_amount_date"
            classification = "probable"
            match_type = "tolerance"
            explanation = (
                "No shared reference could be normalised. The party, amount and date support a probable match, "
                "but this must be reviewed and is never auto-confirmed."
            )
            score = min(80, max(score, 62))
        else:
            reason = "reference_mismatch"
            explanation = (
                "The amount and some fields agree but the references conflict. "
                "This requires manual confirmation."
            )
            score = min(score, 58)
    elif exact_reference or bank_reference:
        strong_secondary = (
            (gstin_state is True or gstin_state is None)
            and date_state is not False
            and tax_conflict is False
            and not currency_conflict
        )
        if strong_secondary and score >= int(rules["auto_accept_threshold"]):
            classification = "exact" if (
                exact_reference
                and gstin_state is True
                and date_state is True
                and party_state is True
                and not tax_conflict
            ) or (bank_reference and date_state is True) else "strong"
            match_type = "exact" if classification == "exact" else (
                "reference" if bank_reference else "normalized"
            )
            requires_review = False
            reason = "bank_reference" if bank_reference else "values_agree"
            explanation = (
                "The bank narration reference and amount agree within tolerance."
                if bank_reference
                else "The normalised reference, identifiers, amount and date agree within the configured tolerances."
            )
        elif score >= int(rules["review_threshold"]):
            classification = "strong" if score >= int(rules["auto_accept_threshold"]) else "probable"
            match_type = "reference" if bank_reference else "normalized"
            reason = "bank_reference" if bank_reference else "supported_reference"
            explanation = (
                "The reference and amount agree but a secondary field is missing or differs; review the evidence."
            )
            requires_review = True
        else:
            classification = "review"
            reason = "weak_evidence"
            explanation = "Some fields agree but there is not enough evidence for a proposed match."
            requires_review = True
    else:
        # No shared reference.  Only a party + amount + date + identifier
        # combination may become a probable match.
        if (
            gstin_state is True
            and amount_state is True
            and date_state is not False
            and (party_state is True or party_state is None)
            and score >= int(rules["review_threshold"])
        ):
            classification = "probable"
            match_type = "tolerance"
            reason = "party_amount_date"
            explanation = (
                "The GSTIN, amount and nearby date agree but there is no shared reference. "
                "This is a probable match for review, not an automatic match."
            )
            requires_review = True
        elif party_state is True and amount_state is True and date_state is True and score >= int(rules["review_threshold"]):
            classification = "probable"
            match_type = "tolerance"
            reason = "party_amount_date"
            explanation = (
                "The party, amount and date agree but there is no shared reference. "
                "Confirm the reference before accepting."
            )
            requires_review = True
        else:
            classification = "review"
            reason = "no_supporting_reference"
            explanation = (
                "The records do not share a reliable reference. Similar amounts alone are never treated as a match."
            )
            requires_review = True
            score = min(score, int(rules["review_threshold"]) - 1)

    categories = _exception_categories_for(
        classification,
        reason,
        left,
        right,
        differences,
        rules,
        duplicate=False,
        multiple=False,
        allocation=False,
    )
    if classification in {"exact", "strong"} and not requires_review:
        status = "matched"
    elif classification == "partial":
        status = "proposed"
    else:
        status = "proposed"
    return MatchProposal(
        left=[left],
        right=[right],
        classification=classification,
        status=status,
        match_type=match_type,
        confidence=max(0, min(100, score)),
        requires_review=requires_review,
        reason_code=reason,
        explanation=explanation,
        matched_fields=fields,
        differences=differences,
        tolerances=tolerances,
        exception_categories=categories,
        rule_notes=rule_summary(rules),
    )


def _exception_categories_for(
    classification: str,
    reason: str,
    left: EngineRecord | None,
    right: EngineRecord | None,
    differences: Mapping[str, Any],
    rules: Mapping[str, Any],
    *,
    duplicate: bool,
    multiple: bool,
    allocation: bool,
) -> list[str]:
    categories: list[str] = []
    if classification == "exact":
        return categories
    if duplicate:
        return ["duplicate_records"]
    if classification == "reversal_candidate":
        return ["possible_reversal"]
    if multiple:
        return ["multiple_possible_matches"]
    if allocation:
        categories.append("allocation_required")
    if classification == "unmatched":
        categories.append("unmatched_transaction")
        if (left and left.file_id is None) or (right and right.file_id is None):
            categories.append("missing_source_data")
        return categories
    if classification == "partial" or reason == "partial_settlement":
        categories.append("partial_settlement")
    if reason in {"amount_mismatch", "total_differs"}:
        categories.append("amount_mismatch")
    if reason == "date_difference":
        categories.append("date_mismatch")
    if reason in {"gstin_mismatch"}:
        categories.append("gstin_mismatch")
    if reason == "gstin_invalid":
        categories.append("gstin_invalid")
    if reason == "place_of_supply_differs":
        categories.append("place_of_supply_mismatch")
    if reason in {
        "reference_prefix",
        "reference_mismatch",
        "no_supporting_reference",
        "party_amount_date",
        "supported_reference",
        "bank_fuzzy",
    }:
        categories.append("reference_mismatch")
    if reason == "currency_mismatch":
        categories.append("currency_mismatch")
    if reason in {"amount_missing", "no_supporting_reference", "weak_evidence"}:
        categories.append("missing_source_data")
    tolerance = float(rules["amount_tolerance"])
    if (
        differences.get("amount") is not None
        and float(differences.get("amount") or 0) > tolerance
        and "amount_mismatch" not in categories
        and classification not in {"partial", "unmatched", "duplicate"}
    ):
        categories.append("amount_mismatch")
    return sorted(dict.fromkeys(categories))


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _duplicate_groups(records: Sequence[EngineRecord]) -> dict[int, list[EngineRecord]]:
    """Return duplicate groups keyed by the first record's index.

    A duplicate is an identical reference for the same GSTIN/party on the same
    side, or an identical date+amount+direction+party fingerprint when no
    reference exists.  The engine never pairs duplicates automatically.
    """

    by_reference: dict[tuple[str, str], list[EngineRecord]] = {}
    by_fingerprint: dict[tuple[str, str, str, str], list[EngineRecord]] = {}
    for record in records:
        if record.reference and len(record.reference) >= 3:
            key = (record.gstin, record.reference)
            if not record.gstin:
                if not record.party:
                    continue
                key = (normalize_text(record.party).upper(), record.reference)
            by_reference.setdefault(key, []).append(record)
        elif record.amount is not None and record.date is not None:
            key = (
                record.date.isoformat(),
                str(record.amount),
                record.direction,
                normalize_text(record.party).upper(),
            )
            if key[2] or key[3]:
                by_fingerprint.setdefault(key, []).append(record)
    groups: dict[int, list[EngineRecord]] = {}
    for group in list(by_reference.values()) + list(by_fingerprint.values()):
        if len(group) < 2:
            continue
        groups[min(record.index for record in group)] = sorted(
            group, key=lambda item: item.index
        )
    return groups


# ---------------------------------------------------------------------------
# Bank narration references
# ---------------------------------------------------------------------------

_UTR_RE = re.compile(r"\b[A-Z]{4}\d{6,}\b")
_CHEQUE_RE = re.compile(r"\b(?:CHQ|CHEQUE|CHECK)[\s:./-]*([0-9]{4,12})\b", re.I)
_INVOICE_RE = re.compile(r"\b(?:INV|BILL|VCH|VOUCHER)[\s:./-]*([A-Z0-9][A-Z0-9/.-]{2,})\b", re.I)
_LONG_NUMBER_RE = re.compile(r"\b\d{6,18}\b")


def narration_references(text: str) -> set[str]:
    if not text:
        return set()
    upper = text.upper()
    references: set[str] = set()
    for match in _UTR_RE.finditer(upper):
        references.add(normalize_reference(match.group(0)))
    for match in _CHEQUE_RE.finditer(upper):
        references.add(normalize_reference(match.group(1)))
    for match in _INVOICE_RE.finditer(upper):
        value = match.group(1)
        references.add(normalize_reference(value))
        # Keep the document prefix: INV/001 and INV-1 must both normalise to
        # INV1, not just the numeric suffix.
        prefix = match.group(0).split(value, 1)[0].strip(" /:.-")
        references.add(normalize_reference(prefix + value))
    for match in _LONG_NUMBER_RE.finditer(upper):
        references.add(normalize_reference(match.group(0)))
    for token in re.findall(r"[A-Z0-9][A-Z0-9/.-]{4,}", upper):
        cleaned = normalize_reference(token)
        if len(cleaned) >= 5 and any(char.isdigit() for char in cleaned):
            references.add(cleaned)
    return references


def narration_mentions_reference(text: str, reference: str) -> bool:
    normalised = normalize_reference(reference)
    if len(normalised) < 4:
        return False
    refs = narration_references(text)
    if normalised in refs:
        return True
    compact = normalize_reference(text)
    return len(normalised) >= 6 and normalised in compact


def _bank_duplicate_groups(records: Sequence[EngineRecord]) -> dict[int, list[EngineRecord]]:
    by_reference: dict[tuple[str, str], list[EngineRecord]] = {}
    by_description: dict[tuple[str, str, str], list[EngineRecord]] = {}
    for record in records:
        text = f"{record.description} {record.reference_display}"
        refs = sorted(
            (ref for ref in narration_references(text) if len(ref) >= 6),
            key=lambda value: (-len(value), value),
        )
        if refs:
            key = (refs[0], str(record.amount), record.direction)
            by_reference.setdefault(key, []).append(record)
        elif record.description and record.amount is not None and record.date is not None:
            key = (
                normalize_text(record.description).upper(),
                str(record.amount),
                record.direction,
            )
            by_description.setdefault(key, []).append(record)
    groups: dict[int, list[EngineRecord]] = {}
    for group in list(by_reference.values()) + list(by_description.values()):
        if len(group) < 2:
            continue
        groups[min(record.index for record in group)] = sorted(
            group, key=lambda item: item.index
        )
    return groups


def _bank_charge_or_interest(record: EngineRecord) -> bool:
    text = f"{record.description} {record.document_type}".upper()
    return any(
        marker in text
        for marker in (
            "BANK CHARGE",
            "BANK CHARGES",
            "SERVICE CHARGE",
            "SMS CHARGE",
            "INTEREST",
            "INT.PD",
            "INT CREDIT",
            "GST ON BANK",
            "CHARGES",
        )
    )


def _unpresented_hint(record: EngineRecord, side: str) -> str:
    direction = record.direction
    text = f"{record.description} {record.document_type}".upper()
    if "CHEQUE" in text or "CHQ" in text or record.reference_display:
        if side == "right" and direction == "debit":
            return "Possible unpresented cheque: the books record the payment but the bank has not yet shown it."
        if side == "right" and direction == "credit":
            return "Possible deposit in transit: the books record the receipt but the bank has not yet shown it."
    return ""


# ---------------------------------------------------------------------------
# Dataset matching
# ---------------------------------------------------------------------------


def _group_key(record: EngineRecord) -> tuple[str, str] | None:
    if not record.reference:
        return None
    return (record.gstin, record.reference)


def _candidate_index(records: Sequence[EngineRecord]) -> dict[str, dict[str, list[int]]]:
    by_gstin: dict[str, list[int]] = {}
    by_party: dict[str, list[int]] = {}
    by_prefix: dict[str, list[int]] = {}
    by_amount: dict[str, list[int]] = {}
    for record in records:
        if record.gstin:
            by_gstin.setdefault(record.gstin, []).append(record.index)
        for token in _token_set(record.party):
            by_party.setdefault(token, []).append(record.index)
        if record.reference:
            by_prefix.setdefault(record.reference[:6], []).append(record.index)
        if record.amount is not None:
            by_amount.setdefault(str(record.amount.quantize(Decimal("0.01"))), []).append(record.index)
    return {
        "gstin": by_gstin,
        "party": by_party,
        "prefix": by_prefix,
        "amount": by_amount,
    }


def _candidate_indices(
    left: EngineRecord,
    index: Mapping[str, Mapping[str, list[int]]],
    limit: int = 120,
) -> list[int]:
    found: set[int] = set()
    if left.gstin:
        found.update(index["gstin"].get(left.gstin, []))
    for token in _token_set(left.party):
        found.update(index["party"].get(token, []))
    if left.reference:
        found.update(index["prefix"].get(left.reference[:6], []))
    if left.amount is not None:
        found.update(index["amount"].get(str(left.amount.quantize(Decimal("0.01"))), []))
    return sorted(found)[:limit]


def match_records(
    left_rows: Sequence[Mapping[str, Any]],
    right_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
    *,
    partial_allowed: bool = False,
) -> dict:
    """Match two invoice-like datasets and return explainable proposals."""

    rules = normalise_rules(config)
    left = _apply_reference_policy(
        [build_record(row, index, "left") for index, row in enumerate(left_rows or [])],
        rules,
    )
    right = _apply_reference_policy(
        [build_record(row, index, "right") for index, row in enumerate(right_rows or [])],
        rules,
    )
    proposals: list[MatchProposal] = []
    used_left: set[int] = set()
    used_right: set[int] = set()

    if rules["detect_duplicates"]:
        for side, records, used in (("left", left, used_left), ("right", right, used_right)):
            for group in _duplicate_groups(records).values():
                for record in group:
                    used.add(record.index)
                    proposals.append(
                        MatchProposal(
                            left=[record] if side == "left" else [],
                            right=[record] if side == "right" else [],
                            classification="duplicate",
                            status="duplicate",
                            match_type="duplicate",
                            confidence=100,
                            requires_review=True,
                            reason_code="duplicate_reference",
                            explanation=(
                                f"This reference/fingerprint appears {len(group)} times in the {side} dataset. "
                                "No arbitrary pairing was made. Confirm which copy is genuine."
                            ),
                            differences=_base_differences(
                                record if side == "left" else None,
                                record if side == "right" else None,
                            ),
                            tolerances=["Duplicate detection runs before amount/date tolerances."],
                            exception_categories=["duplicate_records"],
                            rule_notes=rule_summary(rules),
                        )
                    )

    left_pool = [record for record in left if record.index not in used_left]
    right_pool = [record for record in right if record.index not in used_right]
    left_by_index = {record.index: record for record in left_pool}
    right_by_index = {record.index: record for record in right_pool}

    left_groups: dict[tuple[str, str], list[EngineRecord]] = {}
    right_groups: dict[tuple[str, str], list[EngineRecord]] = {}
    for record in left_pool:
        key = _group_key(record)
        if key:
            left_groups.setdefault(key, []).append(record)
    for record in right_pool:
        key = _group_key(record)
        if key:
            right_groups.setdefault(key, []).append(record)

    def claim(proposal: MatchProposal) -> None:
        if any(record.index in used_left for record in proposal.left):
            return
        if any(record.index in used_right for record in proposal.right):
            return
        for record in proposal.left:
            used_left.add(record.index)
        for record in proposal.right:
            used_right.add(record.index)
        proposals.append(proposal)

    # Exact/normalised key groups.
    for key in sorted(set(left_groups) & set(right_groups)):
        pending_left = [record for record in left_groups[key] if record.index not in used_left]
        pending_right = [record for record in right_groups[key] if record.index not in used_right]
        if not pending_left or not pending_right:
            continue
        evaluations: dict[tuple[int, int], MatchProposal] = {}
        for lrec in pending_left:
            for rrec in pending_right:
                # A credit note is never auto-paired with an invoice.  It
                # remains available for reversal-candidate detection later.
                if _is_credit_note(lrec) != _is_credit_note(rrec):
                    continue
                evaluations[(lrec.index, rrec.index)] = _evaluate_pair(
                    lrec, rrec, rules, partial_allowed=partial_allowed
                )
        if not evaluations:
            continue
        if len(pending_left) == 1 and len(pending_right) == 1:
            proposal = evaluations[(pending_left[0].index, pending_right[0].index)]
            if proposal.reason_code != "no_supporting_reference":
                claim(proposal)
            continue
        # Mutual best pairs only, so an ambiguous group is never allocated
        # arbitrarily.
        left_best: dict[int, list[tuple[int, int]]] = {}
        right_best: dict[int, list[tuple[int, int]]] = {}
        for (li, ri), proposal in evaluations.items():
            if proposal.confidence < rules["review_threshold"]:
                continue
            left_best.setdefault(li, []).append((proposal.confidence, ri))
            right_best.setdefault(ri, []).append((proposal.confidence, li))
        for li, choices in sorted(left_best.items()):
            highest = max(score for score, _ in choices)
            top = [ri for score, ri in choices if score == highest]
            if len(top) != 1:
                continue
            ri = top[0]
            reverse = right_best.get(ri) or []
            reverse_highest = max((score for score, _ in reverse), default=0)
            reverse_top = [candidate for score, candidate in reverse if score == reverse_highest]
            if reverse_highest == highest and reverse_top == [li]:
                proposal = evaluations[(li, ri)]
                # Explicit identification can be exact, but mutual unique
                # groups with weaker evidence remain review proposals.
                claim(proposal)
        remaining_left = [r for r in pending_left if r.index not in used_left]
        remaining_right = [r for r in pending_right if r.index not in used_right]
        for lrec in remaining_left:
            candidates = [
                rrec
                for rrec in remaining_right
                if rrec.index not in used_right
                and evaluations[(lrec.index, rrec.index)].confidence >= rules["review_threshold"]
            ]
            if len(candidates) == 1:
                proposal = evaluations[(lrec.index, candidates[0].index)]
                if proposal.reason_code != "no_supporting_reference":
                    claim(proposal)
            elif len(candidates) > 1:
                used_left.add(lrec.index)
                proposals.append(
                    MatchProposal(
                        left=[lrec],
                        classification="review",
                        status="proposed",
                        match_type="reference",
                        confidence=min(
                            99,
                            max(
                                evaluations[(lrec.index, cand.index)].confidence
                                for cand in candidates
                            ),
                        ),
                        requires_review=True,
                        reason_code="multiple_candidates",
                        explanation=(
                            f"{len(candidates)} records share this reference/identifier. "
                            "No record was allocated; choose the correct match manually."
                        ),
                        differences=_base_differences(lrec, None),
                        candidates=list(candidates),
                        exception_categories=["multiple_possible_matches"],
                        rule_notes=rule_summary(rules),
                    )
                )

    # Candidate pass for records without a shared key.  Ambiguous records are
    # parked, not consumed, so one-to-many/reversal detection can still use
    # them.  They are only surfaced as review rows if no stronger proposal
    # claimed them later.
    candidate_index = _candidate_index(right_pool)
    ambiguous: dict[int, tuple[int, list[EngineRecord]]] = {}
    pending_mismatch: dict[int, list[tuple[int, EngineRecord, MatchProposal]]] = {}
    for lrec in left_pool:
        if lrec.index in used_left:
            continue
        indices = _candidate_indices(lrec, candidate_index)
        candidates: list[tuple[EngineRecord, MatchProposal]] = []
        for ri in indices:
            rrec = right_by_index.get(ri)
            if rrec is None or rrec.index in used_right:
                continue
            if _is_credit_note(lrec) != _is_credit_note(rrec):
                continue
            # Hard filter: an exact reference may be compared even when the
            # amount differs (it becomes a review item).  Without a reference,
            # require an amount and at least one supporting field.
            same_ref = bool(lrec.reference and lrec.reference == rrec.reference)
            prefix = reference_prefix(lrec.reference, rrec.reference)
            amount_close = (
                lrec.amount is not None
                and rrec.amount is not None
                and _amount_difference(lrec.amount, rrec.amount) <= Decimal(str(rules["amount_tolerance"]))
            )
            gstin_same = bool(lrec.gstin and rrec.gstin and lrec.gstin == rrec.gstin)
            overlap, distinctive = party_overlap(lrec.party, rrec.party)
            if not (same_ref or amount_close or prefix):
                continue
            if not (same_ref or gstin_same or prefix or overlap or distinctive):
                continue
            proposal = _evaluate_pair(
                lrec,
                rrec,
                rules,
                reference_hit=prefix or None,
                partial_allowed=partial_allowed,
            )
            if proposal.reason_code == "no_supporting_reference":
                continue
            if proposal.reason_code == "amount_mismatch":
                # A reference-linked amount difference may actually be a
                # split/aggregation.  Park it until allocations have run.
                pending_mismatch.setdefault(lrec.index, []).append(
                    (proposal.confidence, rrec, proposal)
                )
                continue
            if proposal.confidence < rules["review_threshold"] and proposal.reason_code not in {
                "amount_mismatch",
                "currency_mismatch",
                "gstin_mismatch",
                "tax_difference",
                "partial_settlement",
            }:
                continue
            candidates.append((rrec, proposal))
        if not candidates:
            continue
        # Prefer exact references and unique highest confidence.
        candidates.sort(key=lambda item: (-item[1].confidence, item[0].index))
        top_score = candidates[0][1].confidence
        top = [item for item in candidates if item[1].confidence == top_score]
        if len(top) == 1 and top[0][1].confidence >= rules["review_threshold"]:
            claim(top[0][1])
        else:
            ambiguous[lrec.index] = (
                top_score,
                [item[0] for item in candidates[:10]],
            )

    # One-to-many and many-to-one allocations.
    if rules["allow_one_to_many"]:
        _allocate_groups(
            left_pool,
            right_pool,
            used_left,
            used_right,
            proposals,
            rules,
            partial_allowed=partial_allowed,
            one_to_many=True,
        )
    if rules["allow_many_to_one"]:
        _allocate_groups(
            left_pool,
            right_pool,
            used_left,
            used_right,
            proposals,
            rules,
            partial_allowed=partial_allowed,
            one_to_many=False,
        )

    # Reversal candidates from what remains.
    if rules["detect_reversals"]:
        _reversal_candidates(left_pool, right_pool, used_left, used_right, proposals, rules)

    # Reference-supported amount differences that no allocation claimed are
    # now surfaced as review rows rather than being lost.
    for lrec in left_pool:
        if lrec.index in used_left or lrec.index not in pending_mismatch:
            continue
        entries = pending_mismatch[lrec.index]
        available = [
            entry
            for entry in entries
            if entry[1].index not in used_right
        ]
        if not available:
            continue
        if len(available) == 1:
            claim(available[0][2])
            continue
        used_left.add(lrec.index)
        best = max(available, key=lambda entry: (entry[0], -entry[1].index))
        proposals.append(
            MatchProposal(
                left=[lrec],
                classification="review",
                status="proposed",
                match_type="tolerance",
                confidence=best[0],
                requires_review=True,
                reason_code="multiple_candidates",
                explanation=(
                    "Several records share the reference or supporting fields but have different amounts. "
                    "No allocation was made; review the candidates and choose the correct match."
                ),
                differences=_base_differences(lrec, None),
                candidates=[entry[1] for entry in available[:10]],
                exception_categories=["multiple_possible_matches", "amount_mismatch"],
                rule_notes=rule_summary(rules),
            )
        )

    # Ambiguous records that no stronger allocation or reversal claimed are
    # surfaced for manual selection, with the candidate list preserved.
    for lrec in left_pool:
        if lrec.index in used_left or lrec.index not in ambiguous:
            continue
        top_score, candidates = ambiguous[lrec.index]
        used_left.add(lrec.index)
        proposals.append(
            MatchProposal(
                left=[lrec],
                classification="review",
                status="proposed",
                match_type="tolerance",
                confidence=top_score,
                requires_review=True,
                reason_code="multiple_candidates",
                explanation=(
                    "More than one record has a similar amount and supporting fields. "
                    "No match was allocated; review the candidates and choose manually."
                ),
                differences=_base_differences(lrec, None),
                candidates=candidates,
                exception_categories=["multiple_possible_matches"],
                rule_notes=rule_summary(rules),
            )
        )

    # Never discard unmatched records.
    for record in left:
        if record.index in used_left:
            continue
        used_left.add(record.index)
        hint = _unpresented_hint(record, "left")
        categories = ["unmatched_transaction"]
        if record.file_id is None:
            categories.append("missing_source_data")
        explanation = "No matching record was found in the destination dataset."
        if hint:
            explanation += " " + hint
            categories.append("timing_difference")
        proposals.append(
            MatchProposal(
                left=[record],
                classification="unmatched",
                status="unmatched",
                match_type="none",
                confidence=0,
                requires_review=True,
                reason_code="no_counterpart",
                explanation=explanation,
                differences=_base_differences(record, None),
                exception_categories=sorted(dict.fromkeys(categories)),
                rule_notes=rule_summary(rules),
            )
        )
    for record in right:
        if record.index in used_right:
            continue
        used_right.add(record.index)
        hint = _unpresented_hint(record, "right")
        categories = ["unmatched_transaction"]
        if record.file_id is None:
            categories.append("missing_source_data")
        explanation = "No matching record was found in the source dataset."
        if hint:
            explanation += " " + hint
            categories.append("timing_difference")
        proposals.append(
            MatchProposal(
                right=[record],
                classification="unmatched",
                status="unmatched",
                match_type="none",
                confidence=0,
                requires_review=True,
                reason_code="no_counterpart",
                explanation=explanation,
                differences=_base_differences(None, record),
                exception_categories=sorted(dict.fromkeys(categories)),
                rule_notes=rule_summary(rules),
            )
        )

    result = _summarise(proposals, left, right, rules)
    result["checks"] = []
    return result


def _allocate_groups(
    left_pool: Sequence[EngineRecord],
    right_pool: Sequence[EngineRecord],
    used_left: set[int],
    used_right: set[int],
    proposals: list[MatchProposal],
    rules: Mapping[str, Any],
    *,
    partial_allowed: bool,
    one_to_many: bool,
) -> None:
    tolerance = Decimal(str(rules["amount_tolerance"]))
    max_items = int(rules["max_allocation_items"])
    primaries = [record for record in (left_pool if one_to_many else right_pool) if record.index not in (used_left if one_to_many else used_right)]
    secondaries = [record for record in (right_pool if one_to_many else left_pool) if record.index not in (used_right if one_to_many else used_left)]
    secondaries_by_gstin: dict[str, list[EngineRecord]] = {}
    secondaries_by_party: dict[str, list[EngineRecord]] = {}
    for record in secondaries:
        if record.gstin:
            secondaries_by_gstin.setdefault(record.gstin, []).append(record)
        for token in _token_set(record.party):
            secondaries_by_party.setdefault(token, []).append(record)
    for primary in sorted(primaries, key=lambda item: (-(item.amount or ZERO), item.index)):
        if primary.amount is None:
            continue
        if one_to_many and primary.index in used_left or not one_to_many and primary.index in used_right:
            continue
        pool: dict[int, EngineRecord] = {}
        if primary.gstin:
            for record in secondaries_by_gstin.get(primary.gstin, []):
                pool[record.index] = record
        for token in _token_set(f"{primary.party} {primary.description}"):
            for record in secondaries_by_party.get(token, []):
                pool[record.index] = record
        # Bank narration references can support a split even when one side has
        # no party name at all.
        for record in secondaries:
            if record.index in pool:
                continue
            if record.reference and narration_mentions_reference(primary.description, record.reference):
                pool[record.index] = record
            elif primary.reference and narration_mentions_reference(record.description, primary.reference):
                pool[record.index] = record
        candidates = [
            record
            for record in pool.values()
            if record.index not in (used_right if one_to_many else used_left)
            and record.amount is not None
            and record.amount > 0
            and (primary.date is None or record.date is None or _date_difference(primary.date, record.date) <= rules["date_tolerance_days"])
            and (
                (record.gstin and primary.gstin and record.gstin == primary.gstin)
                or party_overlap(f"{primary.party} {primary.description}", record.party)[0] > 0
                or (record.reference and narration_mentions_reference(primary.description, record.reference))
            )
            and _is_credit_note(record) == _is_credit_note(primary)
        ]
        candidates.sort(key=lambda item: (str(item.date or ""), item.index))
        candidates = candidates[:20]
        if len(candidates) < 2:
            continue
        best: tuple[int, int, tuple[EngineRecord, ...], str] | None = None
        max_size = min(max_items, len(candidates))
        for size in range(2, max_size + 1):
            for combo in itertools.combinations(candidates, size):
                total = sum((record.amount or ZERO for record in combo), ZERO)
                difference = (primary.amount - total).copy_abs()
                if difference <= tolerance:
                    classification_hint = "exact"
                elif (
                    partial_allowed
                    and rules.get("allow_partial")
                    and total < primary.amount
                    and difference > tolerance
                ):
                    classification_hint = "partial"
                else:
                    continue
                evidence = _allocation_support(primary, combo, rules)
                if evidence < rules["review_threshold"]:
                    continue
                rank = (
                    0 if classification_hint == "exact" else 1,
                    evidence,
                    -size,
                )
                if best is None or rank > (best[0], best[1], -len(best[2])):
                    best = (rank[0], evidence, combo, classification_hint)
            if best is not None and best[0] == 0:
                break
        if best is None:
            continue
        _, evidence, combo, classification_hint = best
        total = sum((record.amount or ZERO for record in combo), ZERO)
        difference = primary.amount - total
        if one_to_many:
            left_records = [primary]
            right_records = list(combo)
        else:
            left_records = list(combo)
            right_records = [primary]
        left_total = sum((record.amount or ZERO for record in left_records), ZERO)
        right_total = sum((record.amount or ZERO for record in right_records), ZERO)
        differences = {
            "amount": float((left_total - right_total).copy_abs()),
            "amount_signed": float(left_total - right_total),
            "date_days": _date_difference(
                left_records[0].date if left_records else None,
                right_records[0].date if right_records else None,
            ),
            "outstanding": float(difference.copy_abs()) if classification_hint == "partial" else None,
        }
        allocations = _build_allocations(left_records, right_records)
        classification = "partial" if classification_hint == "partial" else (
            "strong" if evidence >= rules["auto_accept_threshold"] else "probable"
        )
        # Allocations are always review items: one source record is being
        # split or aggregated, and a human must confirm the allocation.
        proposals.append(
            MatchProposal(
                left=left_records,
                right=right_records,
                classification=classification,
                status="proposed",
                match_type="one_to_many" if one_to_many else "many_to_one",
                confidence=min(99, max(evidence, rules["review_threshold"])),
                requires_review=True,
                reason_code="one_to_many_allocation" if one_to_many else "many_to_one_allocation",
                explanation=(
                    ("One record is matched to multiple records; the allocation must be reviewed. "
                     if one_to_many else
                     "Multiple records are matched to one record; the aggregation must be reviewed. ")
                    + (f"₹{difference.copy_abs():,.2f} remains outstanding." if classification == "partial" else "The allocated total agrees within tolerance.")
                ),
                differences=differences,
                tolerances=[
                    f"Amount tolerance ₹{rules['amount_tolerance']:,.2f} applied to the allocated total.",
                    f"Date tolerance {rules['date_tolerance_days']} days applied to every member.",
                ],
                exception_categories=["allocation_required"] + (["partial_settlement"] if classification == "partial" else []),
                allocations=allocations,
                rule_notes=rule_summary(rules),
            )
        )
        for record in left_records:
            used_left.add(record.index)
        for record in right_records:
            used_right.add(record.index)


def _allocation_support(
    primary: EngineRecord, combo: Sequence[EngineRecord], rules: Mapping[str, Any]
) -> int:
    support = 0
    if primary.gstin and all(record.gstin == primary.gstin for record in combo if record.gstin):
        support += 35
    if party_overlap(f"{primary.party} {primary.description}", combo[0].party)[0] > 0:
        support += 20
    if primary.date and all(
        record.date is not None and _date_difference(primary.date, record.date) <= rules["date_tolerance_days"]
        for record in combo
    ):
        support += 15
    if any(
        narration_mentions_reference(record.description, primary.reference)
        or narration_mentions_reference(primary.description, record.reference)
        for record in combo
    ):
        support += 20
    if any(reference_prefix(primary.reference, record.reference) for record in combo):
        support += 10
    return min(100, support + 10)


def _build_allocations(
    left_records: Sequence[EngineRecord], right_records: Sequence[EngineRecord]
) -> list[dict]:
    left_total = sum((record.amount or ZERO for record in left_records), ZERO)
    right_total = sum((record.amount or ZERO for record in right_records), ZERO)
    allocations: list[dict] = []
    for left in left_records:
        left_share = (left.amount or ZERO) / left_total if left_total else ZERO
        for right in right_records:
            right_share = (right.amount or ZERO) / right_total if right_total else ZERO
            amount = min(left.amount or ZERO, right.amount or ZERO) * left_share * right_share
            allocations.append(
                {
                    "left_id": left.row_id,
                    "left_index": left.index,
                    "right_id": right.row_id,
                    "right_index": right.index,
                    "amount": float(amount.quantize(Decimal("0.01"))),
                    "basis": "pro-rata allocation of the agreed total",
                }
            )
    return allocations


def _reversal_candidates(
    left_pool: Sequence[EngineRecord],
    right_pool: Sequence[EngineRecord],
    used_left: set[int],
    used_right: set[int],
    proposals: list[MatchProposal],
    rules: Mapping[str, Any],
) -> None:
    tolerance = Decimal(str(rules["amount_tolerance"]))
    for left in left_pool:
        if left.index in used_left or left.amount is None:
            continue
        for right in right_pool:
            if right.index in used_right or right.amount is None:
                continue
            if left.amount.copy_abs() != right.amount.copy_abs():
                if (left.amount.copy_abs() - right.amount.copy_abs()).copy_abs() > tolerance:
                    continue
            if _is_credit_note(left) == _is_credit_note(right):
                # Both are invoices or both are credit notes: a reversal needs
                # two explicitly known, opposite directions.
                if not (
                    left.direction
                    and right.direction
                    and left.direction != right.direction
                ):
                    continue
            reference_link = (
                bool(left.reference and right.reference and left.reference == right.reference)
                or reference_prefix(left.reference, right.reference)
            )
            party_link = party_overlap(left.party, right.party)[0] > 0
            if not (reference_link or party_link):
                continue
            if not (
                left.date is None
                or right.date is None
                or _date_difference(left.date, right.date) <= rules["date_tolerance_days"]
            ):
                continue
            confidence = 55
            if reference_link:
                confidence += 20
            if party_link:
                confidence += 10
            if _is_credit_note(left) or _is_credit_note(right):
                confidence += 10
            used_left.add(left.index)
            used_right.add(right.index)
            proposals.append(
                MatchProposal(
                    left=[left],
                    right=[right],
                    classification="reversal_candidate",
                    status="reversal_candidate",
                    match_type="reversal",
                    confidence=min(95, confidence),
                    requires_review=True,
                    reason_code="possible_reversal",
                    explanation=(
                        "The amounts are equal and opposite in direction or document type. "
                        "This is only a reversal/credit-note candidate: two opposite amounts are not proof of a reversal. "
                        "Confirm the credit note, cancellation or return before accepting."
                    ),
                    differences=_base_differences(left, right),
                    tolerances=[f"Amount tolerance ₹{rules['amount_tolerance']:,.2f} used to compare absolute values."],
                    exception_categories=["possible_reversal"],
                    rule_notes=rule_summary(rules),
                )
            )
            break


def _summarise(
    proposals: Sequence[MatchProposal],
    left: Sequence[EngineRecord],
    right: Sequence[EngineRecord],
    rules: Mapping[str, Any],
) -> dict:
    counts = {
        "exact": 0,
        "strong": 0,
        "probable": 0,
        "partial": 0,
        "review": 0,
        "unmatched": 0,
        "duplicate": 0,
        "reversal_candidate": 0,
        "matched": 0,
        "proposed": 0,
        "total": len(proposals),
    }
    matched_records = 0
    unmatched_records = 0
    proposed_records = 0
    duplicate_records = 0
    matched_amount = ZERO
    unresolved_amount = ZERO
    debit_total = ZERO
    credit_total = ZERO
    for record in left:
        if record.direction == "debit":
            debit_total += record.amount or ZERO
        elif record.direction == "credit":
            credit_total += record.amount or ZERO
    for record in right:
        if record.direction == "debit":
            debit_total += record.amount or ZERO
        elif record.direction == "credit":
            credit_total += record.amount or ZERO
    for proposal in proposals:
        counts[proposal.classification] = counts.get(proposal.classification, 0) + 1
        if proposal.status == "matched":
            counts["matched"] += 1
            matched_records += len(proposal.left) + len(proposal.right)
            matched_amount += sum((record.amount or ZERO for record in proposal.left), ZERO)
        elif proposal.status == "proposed":
            counts["proposed"] += 1
            proposed_records += len(proposal.left) + len(proposal.right)
            amount = sum((record.amount or ZERO for record in proposal.left), ZERO)
            if amount == 0:
                amount = sum((record.amount or ZERO for record in proposal.right), ZERO)
            unresolved_amount += amount.copy_abs()
        elif proposal.status == "duplicate":
            duplicate_records += len(proposal.left) + len(proposal.right)
            amount = sum((record.amount or ZERO for record in proposal.left + proposal.right), ZERO)
            unresolved_amount += amount.copy_abs()
        elif proposal.status == "reversal_candidate":
            proposed_records += len(proposal.left) + len(proposal.right)
            amount = sum((record.amount or ZERO for record in proposal.left), ZERO)
            unresolved_amount += amount.copy_abs()
        elif proposal.status == "unmatched":
            unmatched_records += len(proposal.left) + len(proposal.right)
            amount = sum((record.amount or ZERO for record in proposal.left + proposal.right), ZERO)
            unresolved_amount += amount.copy_abs()
    left_total = sum((record.amount or ZERO for record in left), ZERO)
    right_total = sum((record.amount or ZERO for record in right), ZERO)
    return {
        "engine_version": ENGINE_VERSION,
        "rules": rules,
        "rule_notes": rule_summary(rules),
        "rows": [proposal.to_payload() for proposal in proposals],
        "counts": counts,
        "totals": {
            "left_amount": float(left_total),
            "right_amount": float(right_total),
            "difference": float(left_total - right_total),
            "matched_amount": float(matched_amount),
            "unresolved_amount": float(unresolved_amount),
            "debit_total": float(debit_total),
            "credit_total": float(credit_total),
            "left_rows": len(left),
            "right_rows": len(right),
            "matched_records": matched_records,
            "unmatched_records": unmatched_records,
            "proposed_records": proposed_records,
            "duplicate_records": duplicate_records,
        },
    }


# ---------------------------------------------------------------------------
# Bank statement vs accounting ledger
# ---------------------------------------------------------------------------


def match_bank_ledger(
    bank_rows: Sequence[Mapping[str, Any]],
    ledger_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> dict:
    rules = normalise_rules(config)
    bank = _apply_reference_policy(
        [build_record(row, index, "left") for index, row in enumerate(bank_rows or [])],
        rules,
    )
    ledger = _apply_reference_policy(
        [build_record(row, index, "right") for index, row in enumerate(ledger_rows or [])],
        rules,
    )
    proposals: list[MatchProposal] = []
    used_bank: set[int] = set()
    used_ledger: set[int] = set()
    ambiguous_bank: dict[int, tuple[int, list[EngineRecord]]] = {}
    tolerance = Decimal(str(rules["amount_tolerance"]))
    ledger_index = _candidate_index(ledger)

    if rules["detect_duplicates"]:
        for side, records, used in (
            ("bank statement", bank, used_bank),
            ("accounting ledger", ledger, used_ledger),
        ):
            groups = (
                _bank_duplicate_groups(records)
                if side == "bank statement"
                else _duplicate_groups(records)
            )
            for group in groups.values():
                for record in group:
                    used.add(record.index)
                    proposals.append(
                        MatchProposal(
                            left=[record] if side == "bank statement" else [],
                            right=[record] if side == "accounting ledger" else [],
                            classification="duplicate",
                            status="duplicate",
                            match_type="duplicate",
                            confidence=100,
                            requires_review=True,
                            reason_code="duplicate_reference",
                            explanation=(
                                f"This bank/ledger reference or fingerprint appears {len(group)} times in the {side}. "
                                "No automatic pairing was made; confirm which transaction is genuine."
                            ),
                            differences=_base_differences(
                                record if side == "bank statement" else None,
                                record if side == "accounting ledger" else None,
                            ),
                            tolerances=["Duplicate detection runs before amount/date tolerances."],
                            exception_categories=["duplicate_records"],
                            rule_notes=rule_summary(rules),
                        )
                    )

    def claim(proposal: MatchProposal) -> None:
        if any(record.index in used_bank for record in proposal.left):
            return
        if any(record.index in used_ledger for record in proposal.right):
            return
        for record in proposal.left:
            used_bank.add(record.index)
        for record in proposal.right:
            used_ledger.add(record.index)
        proposals.append(proposal)

    # Reference-based pass first.
    for line in bank:
        if line.index in used_bank:
            continue
        text = f"{line.description} {line.reference_display}"
        candidates: list[tuple[EngineRecord, bool]] = []
        for record in ledger:
            if record.index in used_ledger:
                continue
            if not record.reference:
                continue
            if narration_mentions_reference(text, record.reference):
                candidates.append((record, True))
        if len(candidates) > 1:
            amount_candidates = [
                item
                for item in candidates
                if _amount_difference(line.amount, item[0].amount) is not None
                and _amount_difference(line.amount, item[0].amount) <= tolerance
            ]
            if len(amount_candidates) == 1:
                candidates = amount_candidates
        if len(candidates) == 1:
            record, _ = candidates[0]
            proposal = _evaluate_pair(
                line,
                record,
                rules,
                bank_reference=True,
                partial_allowed=True,
            )
            claim(proposal)
            continue
        if len(candidates) > 1:
            # Several vouchers are named in the narration.  Keep the bank line
            # available for an explicit split; only surface ambiguity if no
            # allocation can use it later.
            ambiguous_bank[line.index] = (
                min(
                    99,
                    max(
                        _evaluate_pair(
                            line, record, rules, bank_reference=True
                        ).confidence
                        for record, _ in candidates
                    ),
                ),
                [record for record, _ in candidates],
            )

    # Cheque/UTR reference on the ledger side may be present as an explicit
    # reference field even when narration parsing misses it.
    for line in bank:
        if line.index in used_bank:
            continue
        for record in ledger:
            if record.index in used_ledger or not record.reference:
                continue
            if narration_mentions_reference(text=record.reference, reference=line.reference_display):
                proposal = _evaluate_pair(
                    line, record, rules, bank_reference=True, partial_allowed=True
                )
                claim(proposal)
                break

    # Fuzzy pass: amount + nearby date + party, never amount alone.
    for line in bank:
        if line.index in used_bank:
            continue
        indices = _candidate_indices(line, ledger_index)
        candidates: list[tuple[EngineRecord, MatchProposal]] = []
        for index in indices:
            record = next((item for item in ledger if item.index == index), None)
            if record is None or record.index in used_ledger:
                continue
            if line.amount is None or record.amount is None:
                continue
            if _amount_difference(line.amount, record.amount) > tolerance:
                continue
            if not (
                line.date is None
                or record.date is None
                or _date_difference(line.date, record.date) <= rules["fuzzy_date_tolerance_days"]
            ):
                continue
            overlap, distinctive = party_overlap(line.description, record.party)
            if not (overlap or distinctive):
                continue
            proposal = _evaluate_pair(
                line,
                record,
                rules,
                bank_reference=False,
                partial_allowed=True,
            )
            proposal.classification = "probable" if proposal.classification in {"exact", "strong"} else proposal.classification
            proposal.requires_review = True
            proposal.status = "proposed"
            proposal.reason_code = "bank_fuzzy"
            proposal.explanation = (
                "The amount, nearby date and party overlap support a probable match, but no bank/UTR/cheque reference was found. "
                "This must be reviewed and is never auto-confirmed."
            )
            candidates.append((record, proposal))
        if not candidates:
            continue
        candidates.sort(key=lambda item: (-item[1].confidence, item[0].index))
        top_score = candidates[0][1].confidence
        top = [item for item in candidates if item[1].confidence == top_score]
        if len(top) == 1:
            claim(top[0][1])
        else:
            used_bank.add(line.index)
            proposals.append(
                MatchProposal(
                    left=[line],
                    classification="review",
                    status="proposed",
                    match_type="tolerance",
                    confidence=top_score,
                    requires_review=True,
                    reason_code="multiple_candidates",
                    explanation="Several vouchers have this amount, nearby date and party. Choose the correct match manually.",
                    differences=_base_differences(line, None),
                    candidates=[item[0] for item in candidates[:10]],
                    exception_categories=["multiple_possible_matches"],
                    rule_notes=rule_summary(rules),
                )
            )

    # Bank splits / part payments.
    if rules["allow_one_to_many"]:
        _allocate_groups(
            bank, ledger, used_bank, used_ledger, proposals, rules,
            partial_allowed=True, one_to_many=True,
        )
    if rules["allow_many_to_one"]:
        _allocate_groups(
            bank, ledger, used_bank, used_ledger, proposals, rules,
            partial_allowed=True, one_to_many=False,
        )

    if rules["detect_reversals"]:
        _reversal_candidates(bank, ledger, used_bank, used_ledger, proposals, rules)

    for line in bank:
        if line.index in used_bank or line.index not in ambiguous_bank:
            continue
        confidence, candidates = ambiguous_bank[line.index]
        remaining = [record for record in candidates if record.index not in used_ledger]
        if not remaining:
            continue
        used_bank.add(line.index)
        proposals.append(
            MatchProposal(
                left=[line],
                classification="review",
                status="proposed",
                match_type="reference",
                confidence=confidence,
                requires_review=True,
                reason_code="multiple_candidates",
                explanation=(
                    "More than one voucher reference appears in this bank narration and no split allocation was made. "
                    "Choose the correct match manually."
                ),
                differences=_base_differences(line, None),
                candidates=remaining,
                exception_categories=["multiple_possible_matches"],
                rule_notes=rule_summary(rules),
            )
        )

    for record in bank:
        if record.index in used_bank:
            continue
        used_bank.add(record.index)
        categories = ["unmatched_transaction"]
        explanation = "No matching accounting voucher was found for this bank line."
        if _bank_charge_or_interest(record):
            categories = ["bank_charge_interest"]
            explanation += " The narration suggests a bank charge or interest entry; confirm the corresponding ledger posting."
        if record.file_id is None:
            categories.append("missing_source_data")
        proposals.append(
            MatchProposal(
                left=[record],
                classification="unmatched",
                status="unmatched",
                match_type="none",
                confidence=0,
                requires_review=True,
                reason_code="no_counterpart",
                explanation=explanation,
                differences=_base_differences(record, None),
                exception_categories=categories,
                rule_notes=rule_summary(rules),
            )
        )
    for record in ledger:
        if record.index in used_ledger:
            continue
        used_ledger.add(record.index)
        hint = _unpresented_hint(record, "right")
        categories = ["unmatched_transaction"]
        explanation = "No matching bank statement line was found for this accounting voucher."
        if hint:
            explanation += " " + hint
            categories.append("timing_difference")
        if record.file_id is None:
            categories.append("missing_source_data")
        proposals.append(
            MatchProposal(
                right=[record],
                classification="unmatched",
                status="unmatched",
                match_type="none",
                confidence=0,
                requires_review=True,
                reason_code="no_counterpart",
                explanation=explanation,
                differences=_base_differences(None, record),
                exception_categories=categories,
                rule_notes=rule_summary(rules),
            )
        )

    result = _summarise(proposals, bank, ledger, rules)
    result["checks"] = _balance_check(bank_rows, ledger_rows)
    return result


def _balance_check(bank_rows: Sequence[Mapping[str, Any]], ledger_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    checks: list[dict] = []
    bank_metrics = _movement_metrics(bank_rows)
    ledger_metrics = _movement_metrics(ledger_rows)
    checks.append(
        {
            "name": "Source movement",
            "status": "calculated" if bank_metrics["rows"] or ledger_metrics["rows"] else "insufficient_data",
            "left_label": "Bank statement",
            "right_label": "Accounting ledger",
            "left": bank_metrics,
            "right": ledger_metrics,
            "difference": _float(
                _movement_signed(bank_metrics) - _movement_signed(ledger_metrics)
            ),
            "explanation": (
                "Debit and credit movements calculated from the stored source rows."
                if bank_metrics["rows"] or ledger_metrics["rows"]
                else "No readable rows were available for a balance calculation."
            ),
        }
    )
    bank_sources = {
        str(row.get("_ca_file_name") or row.get("source") or "")
        for row in bank_rows or []
        if row.get("_ca_file_name") or row.get("source")
    }
    bank_closing = _closing_balance(bank_rows)
    ledger_closing = _closing_balance(ledger_rows)
    if len(bank_sources) > 1:
        # Closing balances from different statements cannot be compared as one
        # account without an explicit account grouping.
        bank_closing = None
    if bank_closing is not None or ledger_closing is not None:
        difference = None
        if bank_closing is not None and ledger_closing is not None:
            difference = _float((bank_closing - ledger_closing).copy_abs())
        checks.append(
            {
                "name": "Closing balance",
                "status": "calculated" if bank_closing is not None and ledger_closing is not None else "insufficient_data",
                "left_label": "Bank closing",
                "right_label": "Ledger closing",
                "left": {"closing_balance": _float(bank_closing)},
                "right": {"closing_balance": _float(ledger_closing)},
                "difference": difference,
                "explanation": (
                    "Multiple bank statements were present, so a single closing balance was not compared. "
                    "Reconcile one account or provide an explicit account grouping."
                    if len(bank_sources) > 1
                    else (
                        "Closing balances agree within tolerance."
                        if difference is not None and difference <= 1
                        else (
                            "Closing balance difference calculated from stored values."
                            if difference is not None
                            else "Only one side carries a closing balance, so no reconciliation conclusion is claimed."
                        )
                    )
                ),
            }
        )
    return checks


def _movement_metrics(rows: Sequence[Mapping[str, Any]]) -> dict:
    debit = ZERO
    credit = ZERO
    count = 0
    opening = None
    for row in rows or []:
        count += 1
        record = build_record(row, count, "left")
        if record.direction == "debit":
            debit += record.amount or ZERO
        elif record.direction == "credit":
            credit += record.amount or ZERO
        if opening is None:
            opening = parse_money(row.get("opening_balance"))
    return {
        "rows": count,
        "debit": float(debit),
        "credit": float(credit),
        "net": float(debit - credit),
        "opening_balance": _float(opening),
        "closing_balance": _float(_closing_balance(rows)),
    }


def _movement_signed(metrics: Mapping[str, Any]) -> Decimal:
    return parse_money(metrics.get("net")) or ZERO


def _closing_balance(rows: Sequence[Mapping[str, Any]]) -> Decimal | None:
    explicit = None
    derived = None
    for row in rows or []:
        value = parse_money(row.get("closing_balance"))
        if value is not None:
            explicit = value
        balance = parse_money(row.get("balance"))
        if balance is not None:
            derived = balance
    return explicit if explicit is not None else derived


# ---------------------------------------------------------------------------
# GL / sub-ledger balance reconciliation
# ---------------------------------------------------------------------------


def _account_key(row: Mapping[str, Any]) -> str:
    return _first_text(
        row,
        (
            "control_account",
            "gl_account",
            "account_code",
            "account_name",
            "ledger_name",
            "party_code",
            "vendor_number",
            "customer_number",
        ),
    )


def _balance_row(row: Mapping[str, Any], side: str, index: int) -> dict:
    opening = _first_money(row, ("opening_balance", "opening"))
    debit = _first_money(row, ("debit", "debits"))
    credit = _first_money(row, ("credit", "credits"))
    movement = _first_money(row, ("movement", "period_movement", "amount"))
    if movement is None:
        if debit is not None or credit is not None:
            movement = (debit or ZERO) - (credit or ZERO)
    closing = _first_money(row, ("closing_balance", "closing"))
    if closing is None and opening is not None and movement is not None:
        closing = opening + movement
    return {
        "row_id": _coerce_int(_meta(row, "row_id")),
        "file_id": _coerce_int(_meta(row, "file_id")),
        "file_name": normalize_text(_meta(row, "file_name")),
        "kind": normalize_text(_meta(row, "kind")),
        "account": _account_key(row),
        "party": _first_text(
            row,
            (
                *_PARTY_KEYS,
                "vendor_number",
                "customer_number",
                "party_code",
            ),
        ),
        "opening": _float(opening),
        "movement": _float(movement),
        "closing": _float(closing),
        "debit": _float(debit),
        "credit": _float(credit),
        "source": _first_text(row, ("source",)),
        "source_page": _coerce_int(_meta(row, "page") or row.get("source_page")),
        "source_bbox": normalize_text(_meta(row, "bbox") or row.get("source_bbox")) or None,
        "raw": _public_raw(row),
        "side": side,
        "index": index,
    }


def compare_balances(
    control_rows: Sequence[Mapping[str, Any]],
    subledger_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> dict:
    """Compare grouped account balances with explicit opening/movement/closing.

    This is a foundation for control-account reconciliation.  It only reports a
    balance as reconciled when both sides have a closing balance and the
    difference is within the configured amount tolerance.
    """

    rules = normalise_rules(config)
    tolerance = Decimal(str(rules["amount_tolerance"]))
    control: dict[str, list[dict]] = {}
    subledger: dict[str, list[dict]] = {}
    for index, row in enumerate(control_rows or []):
        item = _balance_row(row, "left", index)
        if item["account"]:
            control.setdefault(item["account"].upper(), []).append(item)
    for index, row in enumerate(subledger_rows or []):
        item = _balance_row(row, "right", index)
        if item["account"]:
            subledger.setdefault(item["account"].upper(), []).append(item)
    rows: list[dict] = []
    counts = {"matched": 0, "review_required": 0, "left_only": 0, "right_only": 0}
    for key in sorted(set(control) | set(subledger)):
        left_items = control.get(key) or []
        right_items = subledger.get(key) or []
        left = _aggregate_balance(left_items)
        right = _aggregate_balance(right_items)
        if left and right:
            difference = None
            if left["closing"] is not None and right["closing"] is not None:
                difference = Decimal(str(left["closing"])) - Decimal(str(right["closing"]))
                if difference.copy_abs() <= tolerance:
                    status = "matched"
                    explanation = "Opening, movement and closing balances agree from stored values."
                else:
                    status = "review_required"
                    explanation = f"Closing balances differ by ₹{difference.copy_abs():,.2f}. Investigate the period movement."
            else:
                status = "review_required"
                explanation = "One side has no closing balance, so no reconciliation conclusion is claimed."
            counts[status] += 1
            rows.append(
                {
                    "status": status,
                    "reason_code": "balance_agrees" if status == "matched" else "balance_variance",
                    "explanation": explanation,
                    "left": left,
                    "right": right,
                    "differences": {
                        "amount": _float(difference.copy_abs()) if difference is not None else None,
                        "amount_signed": _float(difference),
                        "date_days": None,
                    },
                    "exception_categories": [] if status == "matched" else ["balance_variance"],
                }
            )
        elif left:
            counts["left_only"] += 1
            rows.append(
                {
                    "status": "left_only",
                    "reason_code": "no_subledger",
                    "explanation": "The control account has no corresponding sub-ledger group.",
                    "left": left,
                    "right": None,
                    "differences": {"amount": left["closing"], "date_days": None},
                    "exception_categories": ["balance_variance"],
                }
            )
        else:
            counts["right_only"] += 1
            rows.append(
                {
                    "status": "right_only",
                    "reason_code": "no_control_account",
                    "explanation": "The sub-ledger group has no corresponding control account.",
                    "left": None,
                    "right": right,
                    "differences": {"amount": right["closing"], "date_days": None},
                    "exception_categories": ["balance_variance"],
                }
            )
    left_total = ZERO
    right_total = ZERO
    for items in control.values():
        aggregate = _aggregate_balance(items)
        if aggregate and aggregate.get("closing") is not None:
            left_total += Decimal(str(aggregate["closing"]))
    for items in subledger.values():
        aggregate = _aggregate_balance(items)
        if aggregate and aggregate.get("closing") is not None:
            right_total += Decimal(str(aggregate["closing"]))
    return {
        "engine_version": ENGINE_VERSION,
        "rules": rules,
        "rule_notes": rule_summary(rules),
        "rows": rows,
        "counts": counts,
        "totals": {
            "left_amount": float(left_total),
            "right_amount": float(right_total),
            "difference": float(left_total - right_total),
            "matched_amount": 0.0,
            "unresolved_amount": float((left_total - right_total).copy_abs()),
            "debit_total": 0.0,
            "credit_total": 0.0,
            "left_rows": sum(len(items) for items in control.values()),
            "right_rows": sum(len(items) for items in subledger.values()),
            "matched_records": counts["matched"],
            "unmatched_records": counts["left_only"] + counts["right_only"],
            "proposed_records": counts["review_required"],
            "duplicate_records": 0,
        },
        "checks": [],
    }


def _aggregate_balance(items: Sequence[Mapping[str, Any]]) -> dict | None:
    if not items:
        return None
    parties = {
        str(item.get("party") or "")
        for item in items
        if item.get("party")
    }
    subledger_parties = len(parties) > 1
    opening = ZERO if subledger_parties else None
    movement = ZERO
    closing = ZERO if subledger_parties else None
    has_opening = False
    has_movement = False
    has_closing = False
    for item in items:
        if item.get("opening") is not None:
            if subledger_parties:
                opening = (opening or ZERO) + Decimal(str(item["opening"]))
            elif opening is None:
                opening = Decimal(str(item["opening"]))
            has_opening = True
        if item.get("movement") is not None:
            movement += Decimal(str(item["movement"]))
            has_movement = True
        if item.get("closing") is not None:
            if subledger_parties:
                closing = (closing or ZERO) + Decimal(str(item["closing"]))
            else:
                closing = Decimal(str(item["closing"]))
            has_closing = True
    if not subledger_parties:
        # A single account/transaction row carries a position, not a movement.
        # Where several transaction rows exist for one account, the last
        # explicit closing value is the running position.
        closing = closing if has_closing else None
    if closing is None and opening is not None and has_movement:
        closing = opening + movement
    return {
        "account": items[0].get("account") or "",
        "opening": float(opening) if has_opening and opening is not None else None,
        "movement": float(movement) if has_movement else None,
        "closing": float(closing) if closing is not None else None,
        "rows": [dict(item) for item in items],
        "source_count": len(items),
    }


def compare_pair(
    left_rows: Sequence[Mapping[str, Any]],
    right_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> dict:
    """Compare one left group with one right group for manual decisions."""

    rules = normalise_rules(config)
    left = [build_record(row, index, "left") for index, row in enumerate(left_rows or [])]
    right = [build_record(row, index, "right") for index, row in enumerate(right_rows or [])]
    if not left or not right:
        raise ValueError("Both sides need at least one record.")
    proposal = _evaluate_pair(
        left[0],
        right[0],
        rules,
        partial_allowed=True,
    )
    if len(left) > 1 or len(right) > 1:
        left_total = sum((record.amount or ZERO for record in left), ZERO)
        right_total = sum((record.amount or ZERO for record in right), ZERO)
        proposal.left = left
        proposal.right = right
        proposal.match_type = "manual_allocation"
        proposal.allocations = _build_allocations(left, right)
        proposal.differences = {
            "amount": float((left_total - right_total).copy_abs()),
            "amount_signed": float(left_total - right_total),
            "date_days": _date_difference(left[0].date, right[0].date),
            "outstanding": None,
        }
    return proposal.to_payload()


def match_dataset(
    left_rows: Sequence[Mapping[str, Any]],
    right_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
    *,
    mode: str = "invoice",
) -> dict:
    if mode == "bank":
        return match_bank_ledger(left_rows, right_rows, config)
    if mode == "balance":
        return compare_balances(left_rows, right_rows, config)
    return match_records(
        left_rows,
        right_rows,
        config,
        partial_allowed=mode in {"vendor", "bank"},
    )
