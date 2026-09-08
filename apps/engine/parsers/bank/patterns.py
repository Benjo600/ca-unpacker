from __future__ import annotations

import re

from apps.engine.parsers.bank.money import DATE_RE, amounts_in

SKIP_LINE = re.compile(
    r"page\s+\d+|statement of account|account statement|customer id|"
    r"nomination|gstin of bank|relationship manager|continued on next|"
    r"computer generated|end of statement|confidential|"
    r"^summary\b|debits\s+\d+|opening\s+[\d,]+|this statement is system",
    re.I,
)
HEADERISH = re.compile(
    r"txn date|narration|withdrawal|transaction remarks|closing balance|"
    r"debit credit|chq / ref|description|particulars|withdrawals|deposits",
    re.I,
)
OPENING_RE = re.compile(r"opening\s+balance", re.I)
CLOSING_RE = re.compile(r"closing\s+balance", re.I)
ACCOUNT_RE = re.compile(r"\b(?:a/?c|account)\s*(?:no|number|#)?\.?\s*[:\-]?\s*(\d{9,18})\b", re.I)
IFSC_RE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
AMOUNT_LINE = re.compile(r"^[\d,.\s₹CrDr/-]+$", re.I)


def clean_text(text: str) -> str:
    return " ".join((text or "").split())


def is_boilerplate(text: str) -> bool:
    if not text or SKIP_LINE.search(text):
        return True
    if OPENING_RE.search(text) or CLOSING_RE.search(text):
        return True
    if HEADERISH.search(text) and not DATE_RE.search(text) and not amounts_in(text):
        return True
    return False


def looks_like_txn(text: str) -> bool:
    if len(text) < 8 or is_boilerplate(text):
        return False
    if not DATE_RE.search(text):
        return False
    return len(amounts_in(text)) >= 2


def is_continuation(text: str) -> bool:
    if len(text) < 4 or SKIP_LINE.search(text) or HEADERISH.search(text):
        return False
    if OPENING_RE.search(text) or CLOSING_RE.search(text):
        return False
    if AMOUNT_LINE.fullmatch(text):
        return False
    return True


def is_amount_line(text: str) -> bool:
    if not text or DATE_RE.search(text):
        return False
    if SKIP_LINE.search(text) or HEADERISH.search(text):
        return False
    if OPENING_RE.search(text) or CLOSING_RE.search(text):
        return False
    if not amounts_in(text):
        return False
    return bool(AMOUNT_LINE.fullmatch(text) or re.fullmatch(r"[\d,.\s₹CrDr/-]+", text, re.I))
