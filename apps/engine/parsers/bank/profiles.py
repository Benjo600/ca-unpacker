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
        hints=("hdfc",),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
    BankProfile(
        key="icici",
        label="ICICI Bank",
        hints=("icici",),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
    BankProfile(
        key="sbi",
        label="State Bank of India",
        hints=("state bank", "sbi ", " sbi"),
        debit_words=("debit", "withdrawal", "dr", "to transfer", "atm wdl", "cheque wdl"),
        credit_words=("credit", "deposit", "cr", "by transfer", "cash deposit"),
    ),
    BankProfile(
        key="axis",
        label="Axis Bank",
        hints=("axis",),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
    BankProfile(
        key="kotak",
        label="Kotak Mahindra Bank",
        hints=("kotak",),
        debit_words=("withdrawal", "dr", "debit"),
        credit_words=("deposit", "cr", "credit"),
    ),
)


def detect_profile(text: str, filename: str = "") -> BankProfile:
    name = filename.lower()
    for profile in PROFILES:
        if any(hint in name for hint in profile.hints):
            return profile
    header = text[:500].lower()
    for profile in PROFILES:
        if any(hint in header for hint in profile.hints):
            return profile
    return BankProfile(
        key="generic",
        label="Bank statement",
        hints=(),
        debit_words=("withdrawal", "debit", "dr"),
        credit_words=("deposit", "credit", "cr"),
    )
