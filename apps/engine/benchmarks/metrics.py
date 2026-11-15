"""Benchmark metrics: CER, WER, field accuracy, amount accuracy, row recall.

Amount/number metrics are graded separately from text metrics, with the
principle that monetary accuracy is the primary grade for a financial
extraction engine (Phase 13).
"""

from __future__ import annotations

import re
from decimal import Decimal


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a):
        current = [i + 1]
        for j, char_b in enumerate(b):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j + 1] + 1, current[j] + 1, previous[j] + cost))
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate against the ground-truth text."""
    reference = reference or ""
    hypothesis = hypothesis or ""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / max(len(reference), 1)


def wer(reference: str, hypothesis: str) -> float:
    ref_words = re.findall(r"\S+", reference or "")
    hyp_words = re.findall(r"\S+", hypothesis or "")
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return levenshtein(" ".join(ref_words), " ".join(hyp_words)) / max(
        len(" ".join(ref_words)), 1
    )


def _norm_amount(value) -> str | None:
    if value is None:
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except Exception:
        return str(value)


def field_match(expected, actual) -> bool:
    """Exact-normalised comparison: trims, Decimal-quantises amounts."""
    if expected is None:
        return actual is None
    if isinstance(expected, Decimal) or (isinstance(expected, (int, float)) and not isinstance(expected, bool)):
        return _norm_amount(expected) == _norm_amount(actual)
    return str(expected or "").strip() == str(actual or "").strip()


def amount_accuracy(expected_amounts: list, actual_amounts: list) -> float:
    """Share of expected amounts found exactly (value-normalised).

    Matching consumes matches (multiset): a value found once satisfies one
    expected occurrence, so two expected 1,014.00 entries (CGST + SGST) really
    need two occurrences — dropping SGST cannot borrow CGST's match.
    """
    if not expected_amounts:
        return 1.0
    available: list[str] = [_norm_amount(value) or "" for value in actual_amounts if value is not None]
    hits = 0
    for value in expected_amounts:
        wanted = _norm_amount(value)
        if wanted is None:
            continue
        if wanted in available:
            hits += 1
            available.remove(wanted)
    return hits / len(expected_amounts)


def row_recall(expected_keys: list[set], actual_keys: list[set]) -> float:
    """Share of expected rows matched by a key tuple (e.g. {date, balance}).

    Keys are compared value-normalised (amounts quantised to 2 decimals) so a
    Decimal ground truth matches the parser's float output.
    """
    if not expected_keys:
        return 1.0

    def norm(item) -> str:
        if isinstance(item, Decimal) or (isinstance(item, (int, float)) and not isinstance(item, bool)):
            return _norm_amount(item) or str(item)
        return str(item)

    remaining = [frozenset(norm(part) for part in item) for item in actual_keys]
    hits = 0
    for expected in expected_keys:
        wanted = frozenset(norm(part) for part in expected)
        for index, candidate in enumerate(remaining):
            if candidate == wanted:
                hits += 1
                remaining.pop(index)
                break
    return hits / len(expected_keys)


def duplicate_rate(rows: list[dict], key_fields: tuple[str, ...] = ("date", "balance", "credit", "debit")) -> float:
    """Repeated identical-key rows over total rows."""
    if not rows:
        return 0.0
    seen: set[tuple] = set()
    duplicates = 0
    for row in rows:
        key = tuple(str(row.get(field)) for field in key_fields)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates / len(rows)
