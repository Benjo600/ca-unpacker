"""Currency metadata and evidence based currency detection.

The registry comes from Babel's bundled CLDR data, so detection works offline
and covers the broad ISO 4217 set rather than a small hand maintained list.
Nothing in this module converts money.  It only labels and formats amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Iterable, Mapping

from babel.core import get_global
from babel.numbers import (
    get_currency_name,
    get_currency_precision,
    get_currency_symbol,
)

# These are ISO 4217 codes but not ordinary transaction currencies.  Keeping
# them out of the symbol table avoids pointless ambiguity.
_NON_CASH_CODES = {
    "XAU",
    "XAG",
    "XPT",
    "XPD",
    "XDR",
    "XTS",
    "XSU",
    "XUA",
    "XXX",
    "XBA",
    "XBB",
    "XBC",
    "XBD",
}

# ISO codes that are also common English words.  They only count as explicit
# evidence when they appear next to an amount or in a labelled field.
_CODE_WORDS = {
    "ALL",
    "BAM",
    "BOB",
    "CUP",
    "GEL",
    "KES",
    "MAD",
    "MOP",
    "PEN",
    "SEK",
    "SOS",
    "TOP",
    "TRY",
}

# Symbols that are used by more than one currency in the real world even where
# CLDR's English symbol for one currency happens to look unique.
_KNOWN_SHARED_SYMBOLS: dict[str, set[str]] = {
    "$": {
        "USD",
        "CAD",
        "AUD",
        "NZD",
        "SGD",
        "HKD",
        "MXN",
        "ARS",
        "CLP",
        "COP",
        "UYU",
        "BMD",
        "BSD",
        "BBD",
        "BZD",
        "KYD",
        "LRD",
        "NAD",
        "TTD",
        "XCD",
        "FJD",
        "GYD",
        "JMD",
        "SBD",
        "SRD",
        "TWD",
        "CUP",
        "DOP",
    },
    "£": {"GBP", "EGP", "LBP", "SYP", "SSP", "SHP", "FKP", "GIP"},
    "¥": {"JPY", "CNY"},
    "₨": {"PKR", "LKR", "NPR", "MUR", "SCR", "INR"},
    "kr": {"SEK", "NOK", "DKK", "ISK"},
    "₩": {"KRW", "KPW"},
    "﷼": {"IRR", "SAR", "QAR", "OMR", "YER"},
}

# Qualified symbols are more useful than the bare symbol.  Babel supplies most
# of these; the extras cover forms commonly printed by banks.
_QUALIFIED_SYMBOLS: dict[str, str] = {
    "US$": "USD",
    "U$": "USD",
    "$US": "USD",
    "USD$": "USD",
    "C$": "CAD",
    "CA$": "CAD",
    "CAN$": "CAD",
    "A$": "AUD",
    "AU$": "AUD",
    "AUD$": "AUD",
    "S$": "SGD",
    "SG$": "SGD",
    "SGD$": "SGD",
    "HK$": "HKD",
    "HKD$": "HKD",
    "NZ$": "NZD",
    "NZD$": "NZD",
    "R$": "BRL",
    "RM": "MYR",
    "Rs": "INR",
    "Rs.": "INR",
    "₹": "INR",
    "CHF": "CHF",
    "Fr.": "CHF",
    "zł": "PLN",
    "Kč": "CZK",
    "Ft": "HUF",
    "lei": "RON",
    "лв": "BGN",
}

_COUNTRY_CURRENCIES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:united states|u\.?s\.?a?\.?|america|american)\b", re.I), "USD"),
    (re.compile(r"\b(?:canada|canadian)\b", re.I), "CAD"),
    (re.compile(r"\b(?:australia|australian)\b", re.I), "AUD"),
    (re.compile(r"\b(?:new zealand|new zealander)\b", re.I), "NZD"),
    (re.compile(r"\b(?:singapore|singaporean)\b", re.I), "SGD"),
    (re.compile(r"\b(?:hong kong)\b", re.I), "HKD"),
    (re.compile(r"\b(?:united kingdom|u\.?k\.?|britain|british|england)\b", re.I), "GBP"),
    (re.compile(r"\b(?:india|indian)\b", re.I), "INR"),
    (re.compile(r"\b(?:japan|japanese)\b", re.I), "JPY"),
    (re.compile(r"\b(?:china|chinese|prc)\b", re.I), "CNY"),
    (re.compile(r"\b(?:united arab emirates|u\.?a\.?e\.?|dubai|abu dhabi)\b", re.I), "AED"),
    (re.compile(r"\b(?:saudi arabia|saudi)\b", re.I), "SAR"),
    (re.compile(r"\b(?:qatar|qatari)\b", re.I), "QAR"),
    (re.compile(r"\b(?:kuwait|kuwaiti)\b", re.I), "KWD"),
    (re.compile(r"\b(?:bahrain|bahraini)\b", re.I), "BHD"),
    (re.compile(r"\b(?:oman|omani)\b", re.I), "OMR"),
    (re.compile(r"\b(?:south africa|south african)\b", re.I), "ZAR"),
    (re.compile(r"\b(?:switzerland|swiss)\b", re.I), "CHF"),
    (re.compile(r"\b(?:eurozone|euro area|european union|europe)\b", re.I), "EUR"),
    (re.compile(r"\b(?:bangladesh|bangladeshi)\b", re.I), "BDT"),
    (re.compile(r"\b(?:pakistan|pakistani)\b", re.I), "PKR"),
    (re.compile(r"\b(?:sri lanka|sri lankan)\b", re.I), "LKR"),
    (re.compile(r"\b(?:nepal|nepalese)\b", re.I), "NPR"),
    (re.compile(r"\b(?:malaysia|malaysian)\b", re.I), "MYR"),
    (re.compile(r"\b(?:thailand|thai)\b", re.I), "THB"),
    (re.compile(r"\b(?:indonesia|indonesian)\b", re.I), "IDR"),
    (re.compile(r"\b(?:philippines|filipino)\b", re.I), "PHP"),
    (re.compile(r"\b(?:vietnam|vietnamese)\b", re.I), "VND"),
    (re.compile(r"\b(?:south korea|korea|korean)\b", re.I), "KRW"),
    (re.compile(r"\b(?:turkey|turkish)\b", re.I), "TRY"),
    (re.compile(r"\b(?:russia|russian)\b", re.I), "RUB"),
    (re.compile(r"\b(?:brazil|brazilian)\b", re.I), "BRL"),
    (re.compile(r"\b(?:mexico|mexican)\b", re.I), "MXN"),
)

_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_CODE_RE = re.compile(r"\b[A-Z]{3}\b")
_LABEL_RE = re.compile(
    r"(?i)\b(?:currency|ccy|curr(?:ency)?(?:\s*code)?)\b\s*[:\-]?\s*"
    r"(?P<value>[A-Z]{3}|[^\s]{1,5})"
)
_AMOUNT_AFTER_CODE_RE = re.compile(r"\s*[-:]?\s*(?:\d|\(|[$€£¥₹])")
_AMOUNT_BEFORE_CODE_RE = re.compile(r"(?:\d|\))\s*$")


@dataclass(frozen=True)
class CurrencyInfo:
    code: str
    name: str
    symbol: str
    minor_units: int
    symbol_is_ambiguous: bool


@dataclass(frozen=True)
class Candidate:
    code: str
    confidence: float
    source: str
    evidence: str


@lru_cache(maxsize=1)
def active_currency_codes() -> tuple[str, ...]:
    """Return currencies currently used by at least one territory."""
    territory_currencies = get_global("territory_currencies") or {}
    today = date.today()
    codes: set[str] = set()
    for rows in territory_currencies.values():
        for row in rows:
            try:
                code, _start, end = row[0], row[1], row[2]
            except (IndexError, TypeError):
                continue
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code):
                continue
            if code in _NON_CASH_CODES:
                continue
            if end is not None and tuple(end) <= (today.year, today.month, today.day):
                continue
            codes.add(code)
    return tuple(sorted(codes))


@lru_cache(maxsize=1)
def _known_codes() -> frozenset[str]:
    """All ISO codes Babel knows, including historical ones for old statements."""
    return frozenset((get_global("all_currencies") or {}).keys())


def is_supported(code: str | None) -> bool:
    return bool(code) and str(code).strip().upper() in active_currency_codes()


def is_known(code: str | None) -> bool:
    return bool(code) and str(code).strip().upper() in _known_codes()


@lru_cache(maxsize=1)
def _symbol_map() -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for code in active_currency_codes():
        try:
            symbol = (get_currency_symbol(code, locale="en") or "").strip()
        except Exception:
            symbol = ""
        if symbol:
            mapping.setdefault(symbol, set()).add(code)

    # Babel's English symbol for some currencies is the ISO code itself; those
    # are handled by the explicit-code path instead of the symbol path.
    for symbol in list(mapping):
        if re.fullmatch(r"[A-Z]{3}", symbol) and symbol in mapping[symbol]:
            mapping[symbol].discard(symbol)

    for symbol, code in _QUALIFIED_SYMBOLS.items():
        if code in active_currency_codes() or is_known(code):
            mapping.setdefault(symbol, set()).add(code)

    for symbol, codes in _KNOWN_SHARED_SYMBOLS.items():
        mapping[symbol] = set(codes) | mapping.get(symbol, set())

    return {symbol: codes for symbol, codes in mapping.items() if symbol and codes}


@lru_cache(maxsize=1)
def _symbol_pattern() -> re.Pattern[str] | None:
    aliases = sorted(_symbol_map(), key=len, reverse=True)
    if not aliases:
        return None
    joined = "|".join(re.escape(alias) for alias in aliases)
    return re.compile(rf"(?<![A-Za-z])(?:{joined})(?![A-Za-z])")


def currency_info(code: str | None) -> CurrencyInfo | None:
    if not code:
        return None
    upper = str(code).strip().upper()
    if not is_known(upper):
        return None
    try:
        name = get_currency_name(upper, locale="en", count=1)
    except Exception:
        name = upper
    try:
        symbol = (get_currency_symbol(upper, locale="en") or "").strip()
    except Exception:
        symbol = ""
    try:
        minor = int(get_currency_precision(upper))
    except Exception:
        minor = 2
    candidates = _symbol_map().get(symbol, set()) if symbol else set()
    return CurrencyInfo(
        code=upper,
        name=name or upper,
        symbol=symbol,
        minor_units=max(0, min(minor, 4)),
        symbol_is_ambiguous=len(candidates) > 1,
    )


def symbol_is_ambiguous(symbol: str | None) -> bool:
    if not symbol:
        return False
    return len(_symbol_map().get(symbol, set())) > 1


def minor_units(code: str | None) -> int:
    info = currency_info(code)
    return info.minor_units if info is not None else 2


def currency_symbol(code: str | None) -> str | None:
    info = currency_info(code)
    return info.symbol if info is not None else None


def excel_number_format(code: str | None, *, inferred: bool = False) -> str:
    """Build an Excel number format that never changes the numeric value."""
    info = currency_info(code)
    digits = info.minor_units if info is not None else 2
    decimals = ""
    if digits > 0:
        decimals = "." + ("0" * digits)
    base = "#,##0" + decimals
    prefix = ""
    suffix = ""
    if info is not None:
        symbol = info.symbol
        if symbol and not info.symbol_is_ambiguous and not re.fullmatch(r"[A-Z]{3}", symbol):
            prefix = f'"{symbol}"'
        else:
            suffix = f'"{info.code}"'
    positive = f"{prefix}{base}"
    if suffix:
        positive = f"{positive} {suffix}"
    negative = f"[Red]-{positive}"
    fmt = f"{positive};{negative}"
    if inferred:
        fmt = f'{positive} "(inferred)";{negative} "(inferred)"'
    return fmt


def excel_neutral_number_format(inferred: bool = False) -> str:
    fmt = "#,##0.00;[Red]-#,##0.00"
    if inferred:
        fmt = '#,##0.00 "(inferred)";[Red]-#,##0.00 "(inferred)"'
    return fmt


def currency_label(decision: Mapping[str, Any] | None) -> str:
    """Short, human readable currency label for UI and workbook cells."""
    data = decision or {}
    code = data.get("currency_code")
    status = str(data.get("currency_status") or "unknown")
    if code:
        if status == "confirmed":
            return str(code)
        return f"{code} ({status})"
    if status == "ambiguous":
        symbols = data.get("currency_symbols") or []
        if symbols:
            return f"Unknown ({', '.join(str(item) for item in symbols)} ambiguous)"
        return "Unknown (ambiguous)"
    return "Unknown"


def currency_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for code in active_currency_codes():
        info = currency_info(code)
        if info is None:
            continue
        label = f"{code} — {info.name}"
        if info.symbol and not info.symbol_is_ambiguous:
            label = f"{code} {info.symbol} — {info.name}"
        options.append({"code": code, "label": label})
    return options


def detect_currency(
    text: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer a statement currency from explicit and corroborating evidence.

    The function never guesses from the application's own location and never
    converts amounts.  A bare ``$`` remains ambiguous unless country metadata
    resolves it.  Conflicting explicit codes produce an ``ambiguous`` result.
    """
    body = _normalise_text(text)
    meta = metadata or {}
    candidates: list[Candidate] = []
    ambiguous_symbols: set[str] = set()

    # 1. Labelled currency fields outrank most other signals.
    for match in _LABEL_RE.finditer(body):
        value = (match.group("value") or "").strip()
        code = value.upper()
        if is_known(code):
            candidates.append(
                Candidate(code, 1.0, "labelled_field", f"currency field: {value}")
            )
            continue
        symbol_codes = _symbol_map().get(value)
        if symbol_codes:
            for symbol_code in symbol_codes:
                weight = 0.9 if len(symbol_codes) == 1 else 0.65
                candidates.append(
                    Candidate(
                        symbol_code,
                        weight,
                        "labelled_field",
                        f"currency field symbol: {value}",
                    )
                )
            if len(symbol_codes) > 1:
                ambiguous_symbols.add(value)

    # 2. Explicit ISO codes.  Numeric adjacency and labels are stronger than a
    #    standalone three letter token.
    upper_body = body.upper()
    seen_codes: dict[str, float] = {}
    for code in _known_codes():
        if code in _NON_CASH_CODES:
            continue
        token_re = re.compile(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])")
        for match in token_re.finditer(upper_body):
            before = upper_body[max(0, match.start() - 24) : match.start()]
            after = upper_body[match.end() : match.end() + 24]
            labelled = bool(
                re.search(r"(?:CURRENCY|CCY|CURR)\s*[:\-]?\s*$", before)
            )
            numeric = bool(_AMOUNT_AFTER_CODE_RE.match(after)) or bool(
                _AMOUNT_BEFORE_CODE_RE.search(before)
            )
            if code in _CODE_WORDS and not (numeric or labelled):
                continue
            if labelled:
                weight = 1.0
            elif numeric:
                weight = 0.95
            else:
                # A standalone uppercase ISO-looking token is useful evidence
                # but weaker than a code attached to an amount.
                weight = 0.65
            previous = seen_codes.get(code, 0.0)
            if weight > previous:
                seen_codes[code] = weight
    for code, weight in seen_codes.items():
        source = "explicit_code"
        if weight >= 1.0:
            evidence = f"ISO code {code} in a currency field"
        elif weight >= 0.95:
            evidence = f"ISO code {code} next to an amount"
        else:
            evidence = f"ISO code {code}"
        candidates.append(Candidate(code, weight, source, evidence))

    # 3. Currency symbols.  A bare shared symbol stays ambiguous.
    pattern = _symbol_pattern()
    if pattern is not None:
        symbol_hits: dict[str, int] = {}
        for match in pattern.finditer(body):
            symbol_hits[match.group(0)] = symbol_hits.get(match.group(0), 0) + 1
        for symbol, count in symbol_hits.items():
            codes = _symbol_map().get(symbol, set())
            if not codes:
                continue
            if len(codes) == 1:
                code = next(iter(codes))
                weight = 0.75 if count >= 2 else 0.7
                candidates.append(
                    Candidate(
                        code,
                        weight,
                        "qualified_symbol" if _is_qualified(symbol) else "symbol",
                        f"symbol {symbol}" + (f" x{count}" if count > 1 else ""),
                    )
                )
            else:
                ambiguous_symbols.add(symbol)
                for code in sorted(codes):
                    candidates.append(
                        Candidate(
                            code,
                            0.3,
                            "ambiguous_symbol",
                            f"bare symbol {symbol}",
                        )
                    )

    # 4. Country wording in the statement or supplied metadata.
    country_codes: dict[str, str] = {}
    haystack = f"{body}\n{meta.get('country') or ''}\n{meta.get('address') or ''}"
    for regex, code in _COUNTRY_CURRENCIES:
        match = regex.search(haystack)
        if match:
            country_codes[code] = match.group(0)
            candidates.append(
                Candidate(
                    code,
                    0.55,
                    "country_metadata",
                    f"country wording: {match.group(0)}",
                )
            )

    # 5. Bank metadata is only a weak corroborating signal.  In particular it
    #    must not turn a bare ``$`` into INR.
    ifsc = str(meta.get("ifsc") or "").strip().upper()
    if not ifsc:
        found_ifsc = _IFSC_RE.search(upper_body)
        ifsc = found_ifsc.group(0) if found_ifsc else ""
    if ifsc and _IFSC_RE.fullmatch(ifsc):
        candidates.append(
            Candidate("INR", 0.6, "bank_metadata", f"Indian IFSC {ifsc}")
        )
    profile_key = str(meta.get("profile_key") or "").strip().lower()
    if profile_key in {"hdfc", "icici", "sbi", "axis", "kotak"}:
        candidates.append(
            Candidate(
                "INR",
                0.45,
                "bank_metadata",
                f"bank profile {meta.get('profile_label') or profile_key}",
            )
        )

    decision = _resolve(candidates, ambiguous_symbols)
    decision["currency_candidates"] = _candidates_payload(candidates)
    decision["currency_symbols"] = sorted(ambiguous_symbols)
    info = currency_info(decision.get("currency_code"))
    decision["currency_symbol"] = info.symbol if info else None
    decision["currency_minor_units"] = info.minor_units if info else 2
    decision["currency_name"] = info.name if info else None
    decision["currency_label"] = currency_label(decision)
    return decision


def apply_override(
    decision: Mapping[str, Any] | None, code: str | None
) -> dict[str, Any]:
    """Apply a user's manual currency choice without touching amounts."""
    result = dict(decision or {})
    chosen = (code or "").strip().upper() or None
    if chosen is None:
        return result
    if not is_known(chosen):
        raise ValueError("That is not a known ISO currency code.")
    result.update(
        {
            "currency_code": chosen,
            "currency_source": "manual_override",
            "currency_confidence": 1.0,
            "currency_status": "confirmed",
            "currency_ambiguous": False,
            "currency_symbol": currency_symbol(chosen),
            "currency_minor_units": minor_units(chosen),
            "currency_name": (currency_info(chosen) or CurrencyInfo(chosen, chosen, "", 2, False)).name,
        }
    )
    result["currency_label"] = currency_label(result)
    return result


def _normalise_text(text: str | None) -> str:
    value = str(text or "")
    return (
        value.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2007", " ")
        .replace("\r", "\n")
    )


def _is_qualified(symbol: str) -> bool:
    if symbol in _QUALIFIED_SYMBOLS:
        return True
    return symbol not in _KNOWN_SHARED_SYMBOLS and not re.fullmatch(
        r"[$€£¥₹₩₺₽₦₱฿₫₴₪₡₲₵₸₼₾৳₨﷼]", symbol
    )


def _resolve(
    candidates: Iterable[Candidate], ambiguous_symbols: set[str]
) -> dict[str, Any]:
    grouped: dict[str, Candidate] = {}
    for candidate in candidates:
        current = grouped.get(candidate.code)
        if current is None or candidate.confidence > current.confidence:
            grouped[candidate.code] = candidate

    if not grouped:
        return {
            "currency_code": None,
            "currency_source": "none",
            "currency_confidence": 0.0,
            "currency_status": "unknown",
            "currency_ambiguous": False,
        }

    ordered = sorted(grouped.values(), key=lambda item: item.confidence, reverse=True)
    explicit_sources = {"labelled_field", "explicit_code", "qualified_symbol"}
    explicit = [item for item in ordered if item.source in explicit_sources]

    if explicit:
        top = explicit[0]
        competing = [
            item
            for item in explicit[1:]
            if item.code != top.code and item.confidence >= 0.6
        ]
        if competing and top.confidence - competing[0].confidence < 0.2:
            return {
                "currency_code": None,
                "currency_source": "conflict",
                "currency_confidence": 0.0,
                "currency_status": "ambiguous",
                "currency_ambiguous": True,
            }
        status = "confirmed" if top.confidence >= 0.8 else "inferred"
        return {
            "currency_code": top.code,
            "currency_source": top.source,
            "currency_confidence": round(top.confidence, 2),
            "currency_status": status,
            "currency_ambiguous": False,
        }

    unambiguous = [
        item
        for item in ordered
        if item.source == "symbol" and item.confidence >= 0.7
    ]
    if unambiguous:
        top = unambiguous[0]
        competing = [
            item for item in unambiguous[1:] if item.code != top.code and item.confidence >= 0.7
        ]
        if competing:
            return {
                "currency_code": None,
                "currency_source": "conflict",
                "currency_confidence": 0.0,
                "currency_status": "ambiguous",
                "currency_ambiguous": True,
            }
        return {
            "currency_code": top.code,
            "currency_source": "symbol",
            "currency_confidence": round(top.confidence, 2),
            "currency_status": "inferred",
            "currency_ambiguous": False,
        }

    if ambiguous_symbols:
        symbol_codes = set()
        for symbol in ambiguous_symbols:
            symbol_codes.update(_symbol_map().get(symbol, set()))
        country_matches = [
            item
            for item in ordered
            if item.source == "country_metadata" and item.code in symbol_codes
        ]
        if country_matches:
            top = country_matches[0]
            return {
                "currency_code": top.code,
                "currency_source": "ambiguous_symbol+country_metadata",
                "currency_confidence": round(top.confidence, 2),
                "currency_status": "inferred",
                "currency_ambiguous": False,
            }
        return {
            "currency_code": None,
            "currency_source": "ambiguous_symbol",
            "currency_confidence": 0.0,
            "currency_status": "ambiguous",
            "currency_ambiguous": True,
        }

    bank = [item for item in ordered if item.source == "bank_metadata"]
    if bank:
        top = bank[0]
        return {
            "currency_code": top.code,
            "currency_source": "bank_metadata",
            "currency_confidence": round(top.confidence, 2),
            "currency_status": "inferred",
            "currency_ambiguous": False,
        }

    country = [item for item in ordered if item.source == "country_metadata"]
    if country:
        top = country[0]
        return {
            "currency_code": top.code,
            "currency_source": "country_metadata",
            "currency_confidence": round(top.confidence, 2),
            "currency_status": "inferred",
            "currency_ambiguous": False,
        }

    return {
        "currency_code": None,
        "currency_source": "none",
        "currency_confidence": 0.0,
        "currency_status": "unknown",
        "currency_ambiguous": False,
    }


def _candidates_payload(candidates: Iterable[Candidate]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    payload: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
        key = (candidate.code, candidate.source)
        if key in seen:
            continue
        seen.add(key)
        payload.append(
            {
                "code": candidate.code,
                "confidence": round(candidate.confidence, 2),
                "source": candidate.source,
                "evidence": candidate.evidence,
            }
        )
        if len(payload) >= 20:
            break
    return payload
