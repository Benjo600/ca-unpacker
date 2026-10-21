from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from apps.engine.parsers.bank.money import normalize_date, parse_amount
from apps.engine.parsers.sap.signatures import AGING_FIELDS, report_label
from apps.engine.parsers.sap.tables import ParsedTable, TableRecord

_MONEY_FIELDS = (
    "debit",
    "credit",
    "amount",
    "balance",
    "opening_balance",
    "closing_balance",
    *sorted(AGING_FIELDS),
)
_TOLERANCE = Decimal("0.01")
_ISO_DATE = re.compile(r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$")
_COMPACT_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def normalize_table(
    table: ParsedTable,
    report_type: str,
    *,
    source: str,
) -> list[dict]:
    rows: list[dict] = []
    for record in table.records:
        if record.is_total:
            continue
        row = normalize_record(record, report_type, source=source, table=table)
        if row is not None:
            rows.append(row)
    return rows


def normalize_record(
    record: TableRecord,
    report_type: str,
    *,
    source: str,
    table: ParsedTable,
) -> dict | None:
    values = record.values
    posting_date = _date(values.get("posting_date"))
    document_date = _date(values.get("document_date"))
    entry_date = _date(values.get("entry_date"))
    due_date = _date(values.get("due_date"))
    transaction_date = posting_date or document_date or entry_date

    debit = _money(values.get("debit"))
    credit = _money(values.get("credit"))
    amount = _money(values.get("amount"))
    indicator = _indicator(values.get("debit_credit_indicator"))
    if amount is not None and indicator is not None and debit is None and credit is None:
        if indicator == "debit":
            debit = amount
        else:
            credit = amount

    balance = _money(values.get("balance"))
    opening_balance = _money(values.get("opening_balance"))
    closing_balance = _money(values.get("closing_balance"))
    aging = {field: _money(values.get(field)) for field in AGING_FIELDS}
    aging = {field: value for field, value in aging.items() if value is not None}

    gl_account = _optional_text(values.get("gl_account"))
    account_number = _optional_text(values.get("account_number"))
    vendor_number = _optional_text(values.get("vendor_number"))
    customer_number = _optional_text(values.get("customer_number"))
    party_code = _optional_text(values.get("party_code"))
    if report_type in {"vendor", "accounts_payable"}:
        party_code = party_code or vendor_number or account_number
    elif report_type in {"customer", "accounts_receivable"}:
        party_code = party_code or customer_number or account_number
    elif gl_account is None:
        gl_account = account_number

    party_name = _optional_text(values.get("party_name"))
    document_number = _optional_text(values.get("document_number"))
    invoice_number = _optional_text(values.get("invoice_number"))
    reference = _optional_text(values.get("reference"))
    description = _optional_text(values.get("description"))
    account_name = _optional_text(values.get("account_name"))

    has_identifier = any(
        (
            gl_account,
            account_number,
            vendor_number,
            customer_number,
            party_code,
            party_name,
            document_number,
            invoice_number,
            account_name,
        )
    )
    has_money = any(
        value is not None
        for value in (debit, credit, amount, balance, opening_balance, closing_balance, *aging.values())
    )
    has_date = any((posting_date, document_date, entry_date, due_date))
    if not has_money and not (has_identifier and has_date):
        return None
    if not has_identifier and not has_money:
        return None
    # A lone page header such as "Vendor: Acme" has an identifier but no
    # transaction date or amount.  It is not a transaction.
    if not has_money and not has_date:
        return None

    currency = _currency(values.get("currency"))
    gstin = _optional_text(values.get("gstin"))
    flags: list[str] = []
    if indicator is not None:
        if debit is not None and indicator == "credit" and debit != 0:
            flags.append("sap_debit_credit_conflict")
        if credit is not None and indicator == "debit" and credit != 0:
            flags.append("sap_debit_credit_conflict")

    if table.kind == "pdf":
        source_name = f"{source}#p{record.page}" if record.page else source
    else:
        source_name = source
    if table.sheet:
        source_name = f"{source}:{table.sheet}"

    row = {
        "report_type": report_type,
        "report_type_label": report_label(report_type),
        "company_code": _optional_text(values.get("company_code")),
        "gl_account": gl_account,
        "account_name": account_name,
        "document_number": document_number,
        "document_type": _optional_text(values.get("document_type")),
        "posting_date": posting_date,
        "document_date": document_date,
        "entry_date": entry_date,
        "due_date": due_date,
        "baseline_date": _date(values.get("baseline_date")),
        "clearing_date": _date(values.get("clearing_date")),
        "clearing_document": _optional_text(values.get("clearing_document")),
        "posting_key": _optional_text(values.get("posting_key")),
        "reference": reference,
        "assignment": _optional_text(values.get("assignment")),
        "description": description,
        "party_type": (
            "vendor"
            if report_type in {"vendor", "accounts_payable"}
            else "customer"
            if report_type in {"customer", "accounts_receivable"}
            else None
        ),
        "party_code": party_code,
        "party_name": party_name,
        "vendor_number": vendor_number,
        "customer_number": customer_number,
        "invoice_number": invoice_number,
        "invoice_date": document_date if invoice_number and document_date else None,
        "gstin": gstin,
        "supplier_gstin": gstin,
        "gstin_display": gstin,
        "debit": _f(debit),
        "credit": _f(credit),
        "amount": _f(amount),
        "balance": _f(balance),
        "opening_balance": _f(opening_balance),
        "closing_balance": _f(closing_balance),
        "aging_current": _f(aging.get("aging_current")),
        "aging_1_30": _f(aging.get("aging_1_30")),
        "aging_31_60": _f(aging.get("aging_31_60")),
        "aging_61_90": _f(aging.get("aging_61_90")),
        "aging_91_120": _f(aging.get("aging_91_120")),
        "aging_over_120": _f(aging.get("aging_over_120")),
        "currency": currency,
        "fiscal_year": _optional_text(values.get("fiscal_year")),
        "period": _optional_text(values.get("period")),
        "posting_key_display": _optional_text(values.get("posting_key")),
        "tax_code": _optional_text(values.get("tax_code")),
        "cost_center": _optional_text(values.get("cost_center")),
        "profit_center": _optional_text(values.get("profit_center")),
        "business_area": _optional_text(values.get("business_area")),
        "chart_of_accounts": _optional_text(values.get("chart_of_accounts")),
        "controlling_area": _optional_text(values.get("controlling_area")),
        "special_gl_indicator": _optional_text(values.get("special_gl_indicator")),
        "debit_credit_indicator": _optional_text(values.get("debit_credit_indicator")),
        "source": source_name,
        "source_page": int(record.page or 1),
        "source_bbox": record.bbox,
        "raw_excerpt": record.raw_text[:500],
        "source_values": {
            str(label): str(value)
            for label, value in (record.raw_values or {}).items()
        },
        "flags": flags,
        # Canonical aliases used by the existing books/reconciliation layer.
        "voucher_number": document_number,
        "voucher_type": _optional_text(values.get("document_type")),
        "date": transaction_date,
        "party_name": party_name,
    }
    if report_type in {"vendor", "accounts_payable"}:
        row["supplier_name"] = party_name
    elif report_type in {"customer", "accounts_receivable"}:
        row["customer_name"] = party_name
    return row


def stated_totals(records: list[TableRecord]) -> dict[str, float]:
    totals: dict[str, Decimal] = {}
    for record in records:
        if not record.is_total:
            continue
        for field in _MONEY_FIELDS:
            value = _money(record.values.get(field))
            if value is not None:
                # A later grand-total row supersedes an earlier page subtotal.
                totals[field] = value
    return {field: _f(value) for field, value in totals.items()}


def validate_rows(
    rows: list[dict],
    *,
    report_type: str,
    totals: dict[str, float],
) -> list[str]:
    warnings: list[str] = []

    def add(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    for field, stated in totals.items():
        computed = sum((_d(row.get(field)) for row in rows if row.get(field) is not None), Decimal("0"))
        if (computed - _d(stated)).copy_abs() > _TOLERANCE:
            add(f"sap_total_mismatch:{field}")

    if totals.get("debit") is not None and totals.get("credit") is not None:
        if (abs(_d(totals["debit"]) - _d(totals["credit"]))) > _TOLERANCE:
            add("sap_debit_credit_mismatch")

    if report_type == "trial_balance" and not (
        totals.get("debit") is not None and totals.get("credit") is not None
    ):
        debit_total = sum((_d(row.get("debit")) for row in rows), Decimal("0"))
        credit_total = sum((_d(row.get("credit")) for row in rows), Decimal("0"))
        if (debit_total or credit_total) and (
            debit_total - credit_total
        ).copy_abs() > _TOLERANCE:
            add("sap_debit_credit_mismatch")

    if report_type == "journal_entries":
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            document = str(row.get("document_number") or "").strip()
            if document:
                grouped.setdefault(document, []).append(row)
        for document, group in grouped.items():
            if len(group) < 2:
                continue
            debit = sum((_d(row.get("debit")) for row in group), Decimal("0"))
            credit = sum((_d(row.get("credit")) for row in group), Decimal("0"))
            if debit == 0 and credit == 0:
                continue
            if (debit - credit).copy_abs() > _TOLERANCE:
                add(f"sap_document_unbalanced:{document}")
                for row in group:
                    _flag_row(row, "sap_document_unbalanced")

    for row in rows:
        if all(
            row.get(field) is not None
            for field in ("opening_balance", "debit", "credit", "closing_balance")
        ):
            expected = _d(row["opening_balance"]) + _d(row["debit"]) - _d(row["credit"])
            if (expected - _d(row["closing_balance"])).copy_abs() > _TOLERANCE:
                _flag_row(row, "sap_balance_mismatch")
                add("sap_balance_mismatch")

        buckets = [row.get(field) for field in AGING_FIELDS if row.get(field) is not None]
        if len(buckets) >= 2 and row.get("balance") is not None:
            bucket_total = sum((_d(value) for value in buckets), Decimal("0"))
            if (bucket_total - _d(row["balance"])).copy_abs() > _TOLERANCE:
                _flag_row(row, "sap_aging_total_mismatch")
                add("sap_aging_total_mismatch")

    return warnings


def _flag_row(row: dict, flag: str) -> None:
    flags = list(row.get("flags") or [])
    if flag not in flags:
        flags.append(flag)
    row["flags"] = flags


def _money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, (date, datetime)):
        return None
    text = str(value).strip()
    if not text:
        return None
    return parse_amount(text)


def _date(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return None
    compact = _COMPACT_DATE.match(text)
    if compact:
        year, month, day = compact.groups()
        return f"{year}-{month}-{day}"
    iso = _ISO_DATE.match(text)
    if iso:
        year, month, day = iso.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return normalize_date(text) or text


def _currency(value) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    compact = text.upper().strip()
    return compact if re.fullmatch(r"[A-Z]{3}", compact) else text


def _indicator(value) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    compact = re.sub(r"[^A-Za-z]", "", text).upper()
    if compact in {"S", "D", "DR", "DEBIT", "SOLL"}:
        return "debit"
    if compact in {"H", "C", "CR", "CREDIT", "HABEN"}:
        return "credit"
    return None


def _optional_text(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def _d(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
