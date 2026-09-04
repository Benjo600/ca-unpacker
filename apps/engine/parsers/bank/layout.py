from __future__ import annotations

import re
from decimal import Decimal

from apps.engine.parsers.bank.money import AMOUNT_RE, DATE_RE, amounts_in, is_plausible_iso_date, normalize_date, parse_amount
from apps.engine.parsers.bank.patterns import (
    clean_text,
    is_amount_line,
    is_boilerplate,
    is_continuation,
    looks_like_txn,
)
from apps.engine.parsers.bank.profiles import BankProfile
from apps.engine.pdf_extract import WordBox

COL_HINTS = (
    ("date", ("txn date", "trans date", "transaction date", "value date", "tran date")),
    ("narration", ("narration", "particulars", "description", "remarks", "details")),
    ("cheque", ("chq", "cheque", "ref no", "instrument", "chq / ref")),
    ("debit", ("withdrawal", "withdrawals", "debit", "dr amount", "withdraw")),
    ("credit", ("deposit", "deposits", "credit", "cr amount")),
    ("balance", ("balance",)),
)


def has_column_spread(words: list[WordBox]) -> bool:
    if len(words) < 6:
        return False
    xs = [word.x for word in words]
    return max(xs) - min(xs) >= 40


def rows_from_words(words: list[WordBox], profile: BankProfile, filename: str) -> list[dict]:
    if not has_column_spread(words):
        return []
    by_page: dict[int, list[WordBox]] = {}
    for word in words:
        if (word.text or "").strip():
            by_page.setdefault(word.page, []).append(word)

    columns = _detect_columns(words)
    rows: list[dict] = []
    for page in sorted(by_page):
        bands = _y_bands(by_page[page])
        index = 0
        while index < len(bands):
            band = bands[index]
            text = _band_text(band)
            if not DATE_RE.search(text) or is_boilerplate(text):
                index += 1
                continue
            gathered = list(band)
            cursor = index + 1
            while cursor < len(bands) and cursor - index < 8:
                nxt = bands[cursor]
                nxt_text = _band_text(nxt)
                if DATE_RE.search(nxt_text) or is_boilerplate(nxt_text):
                    break
                combined = clean_text(" ".join(word.text for word in gathered))
                if looks_like_txn(combined) and not amounts_in(nxt_text) and not is_continuation(nxt_text):
                    break
                if looks_like_txn(combined) and is_amount_line(nxt_text):
                    break
                gathered.extend(nxt)
                cursor += 1
            row = _words_to_row(gathered, columns, profile, filename)
            if row is not None:
                rows.append(row)
            index = cursor
    return rows


def _band_text(band: list[WordBox]) -> str:
    return clean_text(" ".join(word.text for word in sorted(band, key=lambda item: item.x)))


def _y_bands(words: list[WordBox]) -> list[list[WordBox]]:
    ordered = sorted(words, key=lambda word: (-(word.y + word.height / 2.0), word.x))
    bands: list[list[WordBox]] = []
    for word in ordered:
        placed = False
        for band in bands:
            height = max(word.height, band[0].height, 4.0)
            if abs(word.y - band[0].y) <= max(3.0, height * 0.55):
                band.append(word)
                placed = True
                break
        if not placed:
            bands.append([word])
    return bands


def _detect_columns(words: list[WordBox]) -> dict[str, float]:
    bands = []
    by_page: dict[int, list[WordBox]] = {}
    for word in words:
        by_page.setdefault(word.page, []).append(word)
    for page in sorted(by_page)[:2]:
        bands.extend(_y_bands(by_page[page])[:40])

    best: dict[str, float] = {}
    best_hits = 0
    for band in bands:
        found: dict[str, float] = {}
        for word in band:
            lowered = word.text.lower().strip(":.")
            for key, hints in COL_HINTS:
                if key in found:
                    continue
                if any(hint == lowered or hint in lowered for hint in hints):
                    found[key] = word.x + word.width / 2.0
        hits = len(found)
        if "debit" in found and "credit" in found:
            hits += 1
        if "balance" in found:
            hits += 1
        if hits > best_hits and hits >= 3:
            best_hits = hits
            best = found
    return best


def _words_in_column(words: list[WordBox], columns: dict[str, float], key: str) -> list[WordBox]:
    if key not in columns:
        return []
    centers = sorted(columns.items(), key=lambda item: item[1])
    xpos = columns[key]
    left = xpos - 36
    right = xpos + 36
    for other_key, other_x in centers:
        if other_key == key:
            continue
        if other_x < xpos:
            left = max(left, (other_x + xpos) / 2.0)
        else:
            right = min(right, (other_x + xpos) / 2.0)
    picked = []
    for word in words:
        mid = word.x + word.width / 2.0
        if left <= mid <= right:
            picked.append(word)
    return picked


def _words_to_row(
    words: list[WordBox],
    columns: dict[str, float],
    profile: BankProfile,
    filename: str,
) -> dict | None:
    ordered = sorted(words, key=lambda word: (word.x, -word.y))
    text = clean_text(" ".join(word.text for word in ordered))
    date_match = DATE_RE.search(text)
    if not date_match or is_boilerplate(text):
        return None

    debit: Decimal | None = None
    credit: Decimal | None = None
    balance: Decimal | None = None
    used_columns = False
    if "balance" in columns and ("debit" in columns or "credit" in columns):
        used_columns = True
        debit = _first_amount(_words_in_column(words, columns, "debit"))
        credit = _first_amount(_words_in_column(words, columns, "credit"))
        balance = _first_amount(_words_in_column(words, columns, "balance"))
        if debit == 0:
            debit = None
        if credit == 0:
            credit = None

    amounts = amounts_in(text)
    if not used_columns or balance is None or (debit is None and credit is None):
        if len(amounts) < 2:
            return None
        balance = amounts[-1]
        debit, credit = _debit_credit(amounts, text, profile)

    if debit is None and credit is None:
        return None

    description_words = []
    for word in ordered:
        if DATE_RE.fullmatch(word.text.strip()):
            continue
        if AMOUNT_RE.fullmatch(word.text.replace("₹", "").strip()):
            continue
        description_words.append(word.text)
    description = clean_text(" ".join(description_words)) or text

    cheque = None
    chq = re.search(r"\b(?:chq|cheque|ref)[^\d]{0,6}(\d{4,})\b", text, re.I)
    if chq:
        cheque = chq.group(1)

    xs = [word.x for word in words]
    ys = [word.y for word in words]
    rights = [word.x + word.width for word in words]
    tops = [word.y + word.height for word in words]
    bbox = f"{min(xs):.1f},{min(ys):.1f},{max(rights) - min(xs):.1f},{max(tops) - min(ys):.1f}"
    date = normalize_date(date_match.group(1))
    if not is_plausible_iso_date(date):
        return None
    page = words[0].page
    return {
        "date": date,
        "description": description,
        "cheque_ref": cheque,
        "debit": float(debit) if debit is not None else None,
        "credit": float(credit) if credit is not None else None,
        "balance": float(balance) if balance is not None else None,
        "source_page": page,
        "source_bbox": bbox,
        "source": f"{filename}#p{page}@{bbox}",
        "raw_text": text,
        "flags": [],
    }


def _first_amount(words: list[WordBox]) -> Decimal | None:
    for word in sorted(words, key=lambda item: item.x):
        found = amounts_in(word.text)
        if found:
            return found[0]
        parsed = parse_amount(word.text)
        if parsed is not None:
            return parsed
    return None


def _debit_credit(
    amounts: list[Decimal], text: str, profile: BankProfile
) -> tuple[Decimal | None, Decimal | None]:
    lowered = text.lower()
    if len(amounts) >= 3:
        first, second = amounts[-3], amounts[-2]
        if first and not second:
            return first, None
        if second and not first:
            return None, second
        if first == 0:
            return None, second or None
        if second == 0:
            return first or None, None
        return first, second
    amount = amounts[-2]
    if any(word in lowered for word in profile.credit_words) and not any(
        word in lowered for word in profile.debit_words
    ):
        return None, amount
    if any(word in lowered for word in ("deposit", "neft inward", "imps credit", "salary", "refund")):
        return None, amount
    return amount, None
