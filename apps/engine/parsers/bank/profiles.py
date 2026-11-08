from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BankProfile:
    key: str
    label: str
    hints: tuple[str, ...]
    debit_words: tuple[str, ...]
    credit_words: tuple[str, ...]


PROFILES = (
    BankProfile(
        key="hdfc",
        label="HDFC Bank",
        hints=("hdfc", "hdfc0"),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
    BankProfile(
        key="icici",
        label="ICICI Bank",
        hints=("icici", "icic0"),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
    BankProfile(
        key="sbi",
        label="State Bank of India",
        hints=("state bank", "sbi ", " sbi", "sbi_", "sbi-", "sbin0"),
        debit_words=("debit", "withdrawal", "dr", "to transfer", "atm wdl", "cheque wdl"),
        credit_words=("credit", "deposit", "cr", "by transfer", "cash deposit"),
    ),
    BankProfile(
        key="axis",
        label="Axis Bank",
        hints=("axis", "utib0"),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
    BankProfile(
        key="kotak",
        label="Kotak Mahindra Bank",
        hints=("kotak", "kkbk", "kkbk0", "crn"),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
)


import re

_IFSC_MAP = {
    "kkbk": "kotak",
    "hdfc": "hdfc",
    "icic": "icici",
    "sbin": "sbi",
    "utib": "axis",
}


def detect_profile(text: str, filename: str = "") -> BankProfile:
    name = filename.lower()
    for profile in PROFILES:
        if any(hint in name for hint in profile.hints):
            return profile

    header = text[:4000]
    # 1. Authoritative IFSC code detection
    ifsc_match = re.search(r"\b([A-Za-z]{4})0[A-Za-z0-9]{6}\b", header)
    if ifsc_match:
        prefix = ifsc_match.group(1).lower()
        if prefix in _IFSC_MAP:
            target_key = _IFSC_MAP[prefix]
            for profile in PROFILES:
                if profile.key == target_key:
                    return profile

    # 2. Header text branding check
    header_lower = header.lower()
    for profile in PROFILES:
        if any(re.search(rf"\b{re.escape(hint)}\b", header_lower) for hint in profile.hints):
            return profile
    return BankProfile(
        key="generic",
        label="Bank statement",
        hints=(),
        debit_words=("withdrawal", "debit", "dr"),
        credit_words=("deposit", "credit", "cr"),
    )
