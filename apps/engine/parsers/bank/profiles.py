from __future__ import annotations

import re

from dataclasses import dataclass


@dataclass(frozen=True)
class BankProfile:
    key: str
    label: str
    hints: tuple[str, ...]
    debit_words: tuple[str, ...]
    credit_words: tuple[str, ...]


@dataclass(frozen=True)
class ComplianceProfile:
    key: str
    label: str
    gstin_pattern: str | None = None
    hsn_lengths: tuple[int, ...] | None = None
    tax_exempt_flags: tuple[str, ...] | None = None
    invoice_arithmetic_check: bool = True
    other_flags: tuple[str, ...] | None = None


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


COMPLIANCE_PROFILES = (
    ComplianceProfile(
        key="gst_starter",
        label="GST Starter (999/month)",
        gstin_pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$",
        hsn_lengths=(4, 6, 8),
        tax_exempt_flags=("tax_exempt",),
        invoice_arithmetic_check=True,
        other_flags=("warning_high_value",),
    ),
    ComplianceProfile(
        key="gst_pro",
        label="GST Pro (2500/unlimited)",
        gstin_pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$",
        hsn_lengths=(4, 6, 8),
        tax_exempt_flags=("tax_exempt",),
        invoice_arithmetic_check=True,
        other_flags=(),
    ),
    ComplianceProfile(
        key="gst_suite",
        label="GST Suite (6000)",
        gstin_pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$",
        hsn_lengths=(4, 6, 8),
        tax_exempt_flags=("tax_exempt",),
        invoice_arithmetic_check=True,
        other_flags=(),
    ),
)


def detect_profile(text: str, filename: str = "") -> BankProfile:
    name = filename.lower()
    for profile in PROFILES:
        if any(hint in name for hint in profile.hints):
            return profile

    header = text[:4000]
    ifsc_match = re.search(r"\b([A-Za-z]{4})0[A-Za-z0-9]{6}\b", header)
    if ifsc_match:
        prefix = ifsc_match.group(1).lower()
        _IFSC_MAP = {"kkbk": "kotak", "hdfc": "hdfc", "icic": "icici", "sbin": "sbi", "utib": "axis"}
        if prefix in _IFSC_MAP:
            target_key = _IFSC_MAP[prefix]
            for profile in PROFILES:
                if profile.key == target_key:
                    return profile

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


def detect_profile_with_client(text: str, filename: str = "", client_id: int | None = None) -> BankProfile:
    from apps.engine.clients import get_client

    if client_id is not None:
        client = get_client(client_id)
        if client and client.get("bank_profile_key"):
            key = client["bank_profile_key"]
            for profile in PROFILES:
                if profile.key == key:
                    return profile

    return detect_profile(text, filename)


def detect_compliance_with_client(client_id: int | None = None) -> ComplianceProfile | None:
    """Detect compliance profile for a client, falling back to default if not set."""
    from apps.engine.clients import get_client

    if client_id is not None:
        client = get_client(client_id)
        if client and client.get("compliance_profile_key"):
            key = client["compliance_profile_key"]
            for profile in COMPLIANCE_PROFILES:
                if profile.key == key:
                    return profile

    # Fall back to first default compliance profile
    return COMPLIANCE_PROFILES[0] if COMPLIANCE_PROFILES else None