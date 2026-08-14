from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from apps.engine.parsers.bank.money import DATE_RE, amounts_in, normalize_date
from apps.engine.parsers.bank.profiles import BankProfile, detect_profile
from apps.engine.pdf_extract import ExtractedPdf, LineBox, extract_pdf

SKIP_LINE = re.compile(
    r"page\s+\d+|statement of account|account statement|customer id|"
    r"nomination|gstin of bank|relationship manager|continued on next|"
    r"computer generated|end of statement|confidential|"
    r"^summary\b|debits\s+\d+|opening\s+[\d,]+|this statement is system",
    re.I,
)
OPENING_RE = re.compile(r"opening\s+balance", re.I)
CLOSING_RE = re.compile(r"closing\s+balance", re.I)
ACCOUNT_RE = re.compile(r"\b(?:a/?c|account)\s*(?:no|number|#)?\.?\s*[:\-]?\s*(\d{9,18})\b", re.I)
IFSC_RE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")


def parse_bank_pdf(path: Path, filename: str | None = None) -> dict:
    extracted = extract_pdf(path)
    header = "\n".join(page.text for page in extracted.pages[:2])
    profile = detect_profile(header, filename or path.name)
    opening = _balance_near(extracted, OPENING_RE)
    closing = _balance_near(extracted, CLOSING_RE)
    account = _search(header, ACCOUNT_RE)
    ifsc = _search(header.upper(), IFSC_RE)

    rows: list[dict] = []
    running = opening
    for line in extracted.lines:
        text = " ".join(line.text.split())
        if rows and not DATE_RE.search(text) and _is_continuation(text):
            extra = text.strip()
            if extra:
                rows[-1]["description"] = f"{rows[-1]['description']} {extra}".strip()
                rows[-1]["raw_text"] = f"{rows[-1]['raw_text']} | {extra}"
            continue
        row = _line_to_row(line, profile, filename or path.name)
        if row is None:
            continue
        row = _align_to_running(row, running)
        if row is None:
            if rows and _is_continuation(text):
                rows[-1]["description"] = f"{rows[-1]['description']} {text}".strip()
                rows[-1]["raw_text"] = f"{rows[-1]['raw_text']} | {text}"
            continue
        row["account_number"] = account
        row["ifsc"] = ifsc
        row["account_name"] = profile.label
        rows.append(row)
        if row.get("balance") is not None:
            running = Decimal(str(row["balance"]))

    return {
        "profile": profile.key,
        "profile_label": profile.label,
        "engine": extracted.engine,
        "pdf_type": extracted.pdf_type,
        "page_count": extracted.page_count,
        "opening_balance": _dec(opening),
        "stated_closing": _dec(closing),
        "account_number": account,
        "ifsc": ifsc,
        "rows": rows,
    }


def _search(text: str, pattern: re.Pattern) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _balance_near(extracted: ExtractedPdf, pattern: re.Pattern) -> Decimal | None:
    for line in extracted.lines:
        if pattern.search(line.text):
            amounts = amounts_in(line.text)
            if amounts:
                return amounts[-1]
    for page in extracted.pages:
        for raw in page.text.splitlines():
            if pattern.search(raw):
                amounts = amounts_in(raw)
                if amounts:
                    return amounts[-1]
    return None


HEADERISH = re.compile(
    r"txn date|narration|withdrawal|transaction remarks|closing balance|"
    r"debit credit|chq / ref|description",
    re.I,
)


def _is_continuation(text: str) -> bool:
    if len(text) < 4 or SKIP_LINE.search(text) or HEADERISH.search(text):
        return False
    if OPENING_RE.search(text) or CLOSING_RE.search(text):
        return False
    if re.fullmatch(r"[\d,.\s]+", text):
        return False
    return True


def _align_to_running(row: dict, running: Decimal | None) -> dict | None:
    if running is None or row.get("balance") is None:
        return row
    stated = Decimal(str(row["balance"]))
    debit = Decimal(str(row["debit"])) if row.get("debit") else Decimal("0")
    credit = Decimal(str(row["credit"])) if row.get("credit") else Decimal("0")
    if (running - debit + credit - stated).copy_abs() <= Decimal("1.00"):
        return row

    txn = debit if debit else credit
    if txn:
        if (running - txn - stated).copy_abs() <= Decimal("1.00"):
            row["debit"] = float(txn)
            row["credit"] = None
            return row
        if (running + txn - stated).copy_abs() <= Decimal("1.00"):
            row["credit"] = float(txn)
            row["debit"] = None
            return row
    return None


def _line_to_row(line: LineBox, profile: BankProfile, filename: str) -> dict | None:
    text = " ".join(line.text.split())
    if len(text) < 8 or SKIP_LINE.search(text):
        return None
    if OPENING_RE.search(text) or CLOSING_RE.search(text):
        return None
    date_match = DATE_RE.search(text)
    if not date_match:
        return None
    amounts = amounts_in(text)
    if len(amounts) < 2:
        return None

    date = normalize_date(date_match.group(1))
    balance = amounts[-1]
    debit: Decimal | None = None
    credit: Decimal | None = None
    lowered = text.lower()

    if len(amounts) >= 3:
        first, second = amounts[-3], amounts[-2]
        if first and not second:
            debit = first
        elif second and not first:
            credit = second
        else:
            debit, credit = first, second
            if debit == 0:
                debit = None
            if credit == 0:
                credit = None
    else:
        amount = amounts[-2]
        if any(word in lowered for word in profile.credit_words) and not any(
            word in lowered for word in profile.debit_words
        ):
            credit = amount
        elif any(word in lowered for word in ("deposit", "neft inward", "imps", "salary", "refund")):
            credit = amount
        else:
            debit = amount

    description = DATE_RE.sub("", text, count=1)
    for amount in amounts[-3:]:
        description = description.replace(f"{amount:,}", "")
        description = description.replace(str(amount), "")
    description = re.sub(r"\s{2,}", " ", description).strip(" -|")

    cheque = None
    chq = re.search(r"\b(?:chq|cheque|ref)[^\d]{0,6}(\d{4,})\b", text, re.I)
    if chq:
        cheque = chq.group(1)

    bbox = None
    if line.width or line.height:
        bbox = f"{line.x:.1f},{line.y:.1f},{line.width:.1f},{line.height:.1f}"

    return {
        "date": date,
        "description": description or text,
        "cheque_ref": cheque,
        "debit": _dec(debit),
        "credit": _dec(credit),
        "balance": _dec(balance),
        "source_page": line.page,
        "source_bbox": bbox,
        "source": f"{filename}#p{line.page}" + (f"@{bbox}" if bbox else ""),
        "raw_text": text,
    }


def _dec(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
