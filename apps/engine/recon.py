from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from apps.engine.recon_parsing import (
    DATE_FORMATS as _DATE_FMTS,
    parse_date_value,
    parse_money_value,
)

AMOUNT_TOLERANCE = Decimal("1.00")
COUNT_KEYS = (
    "matched",
    "books_only",
    "portal_only",
    "amount_mismatch",
    "likely",
    "tax_mismatch",
    "duplicate",
    "split_merged",
    "credit_note",
    "same_bill",
)
GENERIC_STATUS_KEYS = (
    "matched",
    "amount_mismatch",
    "review_required",
    "left_only",
    "right_only",
    "duplicate",
)
_COUNT_KEYS = COUNT_KEYS
_LEFTOVER_STATUSES = ("books_only", "portal_only")
_TAX_COMPONENTS = (
    ("taxable", ("taxable", "taxable_value"), "taxable value"),
    ("cgst", ("cgst",), "central tax"),
    ("sgst", ("sgst",), "state tax"),
    ("igst", ("igst",), "integrated tax"),
)


def normalize_gstin(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip().upper()


def normalize_invoice_number(value) -> str:
    if value is None:
        return ""
    alnum = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()

    def _digits(match: re.Match[str]) -> str:
        stripped = match.group(0).lstrip("0")
        return stripped or "0"

    return re.sub(r"\d+", _digits, alnum)


def parse_recon_date(value) -> date | None:
    """Compatibility wrapper for :func:`apps.engine.recon_parsing.parse_date_value`."""
    return parse_date_value(value)


def money(value) -> Decimal | None:
    """Compatibility wrapper for :func:`apps.engine.recon_parsing.parse_money_value`."""
    return parse_money_value(value)


def reconcile(
    books_rows: list[dict],
    gstr_2b_rows: list[dict],
    bank_rows: list[dict] | None = None,
    *,
    date_tolerance_days: int = 0,
    amount_tolerance=None,
) -> dict:
    books = list(books_rows or [])
    portal_all = list(gstr_2b_rows or [])
    credit_notes = [row for row in portal_all if _is_cdn(row)]
    twob = [row for row in portal_all if not _is_cdn(row)]
    bank = list(bank_rows or [])
    tolerance = money(amount_tolerance)
    if tolerance is None:
        tolerance = AMOUNT_TOLERANCE
    days = max(0, int(date_tolerance_days or 0))
    index = _ReconIndex(books, twob, days)
    book_facts = index.books
    portal_facts = index.portal

    used_books: set[int] = set()
    used_2b: set[int] = set()
    pairs: list[tuple[str, list[int], list[int], str, int, str]] = []

    def _claim(
        status: str,
        books_idx: list[int],
        portal_idx: list[int],
        side: str = "",
        size: int = 0,
        note: str = "",
    ) -> None:
        for bi in books_idx:
            used_books.add(bi)
        for gi in portal_idx:
            used_2b.add(gi)
        pairs.append((status, list(books_idx), list(portal_idx), side, size, note))

    # 1. Same supplier and invoice, date within the allowed days.
    for bi, book in enumerate(book_facts):
        if bi in used_books:
            continue
        for gi in index.portal_lines(book.gstin, book.invoice):
            if gi in used_2b:
                continue
            portal = portal_facts[gi]
            if not _dates_agree(book.date, portal.date, days):
                continue
            if not _amounts_close(book.amount, portal.amount, tolerance):
                continue
            status = "tax_mismatch" if _tax_gaps(books[bi], twob[gi], tolerance) else "matched"
            _claim(status, [bi], [gi])
            break

    # 2. One invoice split across several portal lines, or several bills
    #    merged into one portal line. This runs before the amount check so a
    #    two-line split is not mistaken for a single line with a wrong total.
    for bi in range(len(book_facts)):
        if bi in used_books:
            continue
        group = _split_portal_group(index, bi, used_2b, tolerance)
        if group:
            _claim("split_merged", [bi], group, "portal")
    for gi in range(len(portal_facts)):
        if gi in used_2b:
            continue
        group = _split_books_group(index, gi, used_books, tolerance)
        if group:
            _claim("split_merged", group, [gi], "books")

    # 3. Same key, but the invoice total differs. Skip this when the portal
    #    carries several lines for the same invoice; those are split or
    #    repeated lines, not a single wrong total.
    for bi, book in enumerate(book_facts):
        if bi in used_books:
            continue
        if index.unclaimed_portal_lines(book, used_2b) >= 2:
            continue
        for gi in index.portal_lines(book.gstin, book.invoice):
            if gi in used_2b:
                continue
            portal = portal_facts[gi]
            if not _dates_agree(book.date, portal.date, days):
                continue
            if _amounts_close(book.amount, portal.amount, tolerance):
                continue
            _claim("amount_mismatch", [bi], [gi])
            break

    # 4. Everything lines up except the invoice number itself.
    for bi, book in enumerate(book_facts):
        if bi in used_books:
            continue
        if not book.gstin or book.date is None or book.amount is None:
            continue
        for gi in index.portal_amount_candidates(book.gstin, book.amount, tolerance):
            if gi in used_2b:
                continue
            if _likely_pair(book, portal_facts[gi], days, tolerance):
                _claim("likely", [bi], [gi])
                break

    # 5. The same invoice repeated on one side, with the same amount each time.
    for index_pos, side, size in _duplicate_items(
        books, twob, used_books, used_2b, tolerance
    ):
        if side == "books":
            _claim("duplicate", [index_pos], [], "books", size)
        else:
            _claim("duplicate", [], [index_pos], "portal", size)

    # 5b. The same bill recorded twice in the books — once in the accounting
    #     ledger, once from the supplier's invoice PDF. When one copy is already
    #     reconciled, the leftover copy is the same bill under a different
    #     number, not credit claimed without support.
    reconciled_books = [
        (bi, gis[0])
        for status, bis, gis, _side, _size, _note in pairs
        if gis and status in {"matched", "tax_mismatch", "amount_mismatch", "likely"}
        for bi in bis
    ]
    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        twin = _same_bill_twin(book, books, reconciled_books, twob, days, tolerance)
        if twin is not None:
            _claim("same_bill", [bi], [], "books", 0, note=twin)

    # 6. Whatever is genuinely one-sided.
    for gi in range(len(twob)):
        if gi not in used_2b:
            _claim("portal_only", [], [gi])
    for bi in range(len(books)):
        if bi not in used_books:
            _claim("books_only", [bi], [])

    # Bank lines are read once here. Hinting used to re-parse every line for
    # every row, which is what stalled the 398-file month.
    bank_index = _BankHintIndex(bank)

    rows = []
    counts = {key: 0 for key in COUNT_KEYS}
    for status, bis, gis, side, size, note in pairs:
        book = books[bis[0]] if bis else {}
        portal = twob[gis[0]] if gis else {}
        extra = [twob[gi] for gi in gis[1:]]
        row = _recon_row(
            status,
            book,
            portal,
            extra_portal=extra,
            tolerance=tolerance,
            group_size=size or max(len(bis), len(gis)),
            side=side,
            same_bill_of=note,
        )
        row["bank_hint"] = _bank_hint(row, book, portal, bank_index, tolerance)
        rows.append(row)
        counts[status] = counts.get(status, 0) + 1
    for note in credit_notes:
        row = _recon_row("credit_note", {}, note)
        row["bank_hint"] = ""
        rows.append(row)
        counts["credit_note"] += 1
    return {"rows": rows, "counts": counts, "totals": _totals(rows)}


def _money_of(row: dict, key: str) -> Decimal | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _totals(rows: list[dict]) -> dict:
    portal = Decimal("0")
    books = Decimal("0")
    risk = Decimal("0")
    unsupported = Decimal("0")
    credit_notes = Decimal("0")
    same_bill = Decimal("0")
    for row in rows:
        status = str(row.get("status") or "")
        amt_2b = _money_of(row, "amount_2b")
        amt_books = _money_of(row, "amount_books")
        if status == "credit_note":
            if amt_2b is not None:
                credit_notes += amt_2b.copy_abs()
            continue
        if status == "same_bill":
            # One bill recorded twice in the books is one bill, not two, so it
            # must not inflate the books side of the comparison.
            if amt_books is not None:
                same_bill += amt_books
            continue
        if amt_2b is not None:
            portal += amt_2b
        if amt_books is not None:
            books += amt_books
        if status == "portal_only" and amt_2b is not None:
            risk += amt_2b
        if status == "books_only" and amt_books is not None:
            unsupported += amt_books
    return {
        "portal_total": float(portal),
        "books_total": float(books),
        "gap": float(portal - books),
        "credit_at_risk": float(risk),
        "unsupported_credit": float(unsupported),
        "same_bill_total": float(same_bill),
        "credit_note_total": float(credit_notes),
    }


def _is_cdn(row: dict) -> bool:
    return str(row.get("document_type") or "").strip().upper().startswith("CDN")


def _gstin(row: dict, *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return normalize_gstin(row.get(key))
    return ""


def _invoice(row: dict, *keys: str) -> str:
    for key in keys:
        if row.get(key) not in (None, ""):
            return normalize_invoice_number(row.get(key))
    return ""


def _row_date(row: dict, *keys: str) -> date | None:
    for key in keys:
        parsed = parse_recon_date(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _row_money(row: dict, *keys: str) -> Decimal | None:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return money(row.get(key))
    return None


def _books_gstin(row: dict) -> str:
    return _gstin(row, "supplier_gstin", "gstin")


def _books_invoice(row: dict) -> str:
    return _invoice(row, "invoice_number")


def _books_date(row: dict) -> date | None:
    return _row_date(row, "invoice_date", "date")


def _books_amount(row: dict) -> Decimal | None:
    return _row_money(row, "invoice_value", "amount")


def _gstr_gstin(row: dict) -> str:
    return _gstin(row, "gstin", "supplier_gstin")


def _gstr_invoice(row: dict) -> str:
    return _invoice(row, "invoice_number")


def _gstr_date(row: dict) -> date | None:
    return _row_date(row, "invoice_date", "date")


def _gstr_amount(row: dict) -> Decimal | None:
    return _row_money(row, "invoice_value", "amount")


# ---------------------------------------------------------------------------
# Row facts
#
# Reading a row's GSTIN, invoice number, date and amount costs several regular
# expressions and a Decimal parse.  Every rule below needs those four values on
# every comparison, so each row is read once into :class:`_RowFacts` at the
# start of a run and the rules work on the parsed values.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _RowFacts:
    gstin: str
    invoice: str
    date: date | None
    amount: Decimal | None


def _books_facts(row: dict) -> _RowFacts:
    return _RowFacts(
        _books_gstin(row), _books_invoice(row), _books_date(row), _books_amount(row)
    )


def _gstr_facts(row: dict) -> _RowFacts:
    return _RowFacts(
        _gstr_gstin(row), _gstr_invoice(row), _gstr_date(row), _gstr_amount(row)
    )


def _dates_agree(left: date | None, right: date | None, days: int = 0) -> bool:
    if left is None or right is None:
        return True
    return abs((left - right).days) <= max(0, int(days or 0))


def _amounts_close(
    left: Decimal | None, right: Decimal | None, tolerance: Decimal | None = None
) -> bool:
    if left is None or right is None:
        return False
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    return (left - right).copy_abs() <= limit


def _likely_pair(
    book: _RowFacts,
    portal: _RowFacts,
    days: int = 0,
    tolerance: Decimal | None = None,
) -> bool:
    if not book.gstin or book.date is None:
        return False
    if book.gstin != portal.gstin or not _dates_agree(book.date, portal.date, days):
        return False
    if not _amounts_close(book.amount, portal.amount, tolerance):
        return False
    left = book.invoice
    right = portal.invoice
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _tax_value(row: dict, keys: tuple[str, ...]) -> Decimal | None:
    for key in keys:
        if row.get(key) not in (None, ""):
            value = money(row.get(key))
            if value is not None:
                return value
    return None


def _tax_gaps(book: dict, portal: dict, tolerance: Decimal) -> list[tuple[str, Decimal]]:
    """Tax components that differ beyond the amount allowance."""
    gaps: list[tuple[str, Decimal]] = []
    for _slug, keys, label in _TAX_COMPONENTS:
        left = _tax_value(book, keys)
        right = _tax_value(portal, keys)
        if left is None or right is None:
            continue
        diff = right - left
        if diff.copy_abs() > tolerance:
            gaps.append((label, diff))
    return gaps


def _amount_index(
    facts: list[_RowFacts], indices: list[int]
) -> tuple[list[Decimal], list[int]]:
    """Amounts and their row positions in ascending order, for bisecting."""
    pairs: list[tuple[Decimal, int]] = []
    for index in indices:
        amount = facts[index].amount
        if amount is not None:
            pairs.append((amount, index))
    pairs.sort()
    return [amount for amount, _index in pairs], [index for _amount, index in pairs]


class _ReconIndex:
    """Lookups so no rule has to walk the whole file to find its candidates.

    ``portal_lines`` answers the exact-invoice rules from one bucket,
    ``book_pool`` gives the split-merge rule the rows that can share a portal
    line's supplier and date, and the amount indexes turn "which rows add up
    to this?" into a bisected window instead of a comparison against every
    row in the month.
    """

    __slots__ = (
        "books",
        "portal",
        "days",
        "_portal_key",
        "_portal_by_gstin",
        "_book_by_gstin",
        "_book_by_gstin_date",
        "_book_undated",
        "_portal_amount",
        "_book_amount",
        "_pool_cache",
    )

    def __init__(self, books: list[dict], portal: list[dict], days: int) -> None:
        self.days = max(0, int(days or 0))
        self.books = [_books_facts(row) for row in books]
        self.portal = [_gstr_facts(row) for row in portal]
        self._portal_key: dict[tuple[str, str], list[int]] = defaultdict(list)
        self._portal_by_gstin: dict[str, list[int]] = defaultdict(list)
        self._book_by_gstin: dict[str, list[int]] = defaultdict(list)
        self._book_by_gstin_date: dict[tuple[str, date], list[int]] = defaultdict(list)
        self._book_undated: dict[str, list[int]] = defaultdict(list)
        for position, facts in enumerate(self.portal):
            if not facts.gstin:
                continue
            self._portal_by_gstin[facts.gstin].append(position)
            if facts.invoice:
                self._portal_key[(facts.gstin, facts.invoice)].append(position)
        for position, facts in enumerate(self.books):
            if not facts.gstin:
                continue
            self._book_by_gstin[facts.gstin].append(position)
            if facts.date is None:
                self._book_undated[facts.gstin].append(position)
            else:
                self._book_by_gstin_date[(facts.gstin, facts.date)].append(position)
        self._portal_amount = {
            gstin: _amount_index(self.portal, indices)
            for gstin, indices in self._portal_by_gstin.items()
        }
        self._book_amount = {
            gstin: _amount_index(self.books, indices)
            for gstin, indices in self._book_by_gstin.items()
        }
        self._pool_cache: dict[tuple[str, date | None], list[int]] = {}

    def portal_lines(self, gstin: str, invoice: str) -> list[int]:
        """Portal rows carrying this exact supplier and invoice number."""
        return self._portal_key.get((gstin, invoice), [])

    def unclaimed_portal_lines(self, book: _RowFacts, used_2b: set[int]) -> int:
        if not book.gstin or not book.invoice:
            return 0
        return sum(
            1
            for position in self.portal_lines(book.gstin, book.invoice)
            if position not in used_2b
        )

    def book_pool(self, portal_pos: int) -> list[int]:
        """Book rows that share this portal line's supplier and agree on date.

        Rows come back in file order, which is the order the split rules have
        always reported their group in.
        """
        facts = self.portal[portal_pos]
        key = (facts.gstin, facts.date)
        cached = self._pool_cache.get(key)
        if cached is not None:
            return cached
        pool = self._build_pool(facts)
        self._pool_cache[key] = pool
        return pool

    def _build_pool(self, facts: _RowFacts) -> list[int]:
        gstin = facts.gstin
        undated = self._book_undated.get(gstin, [])
        if facts.date is None:
            # Without a portal date every book row of this supplier agrees.
            return self._book_by_gstin.get(gstin, [])
        buckets: list[list[int]] = [undated] if undated else []
        for offset in range(-self.days, self.days + 1):
            bucket = self._book_by_gstin_date.get(
                (gstin, facts.date + timedelta(days=offset))
            )
            if bucket:
                buckets.append(bucket)
        if not buckets:
            return []
        if len(buckets) == 1:
            return buckets[0]
        # A row keeps one date, so it sits in one bucket only: sort, no dedupe.
        return sorted(position for bucket in buckets for position in bucket)

    def portal_amount_candidates(
        self, gstin: str, amount: Decimal, tolerance: Decimal
    ) -> list[int]:
        """Portal rows of this supplier whose total is within the allowance."""
        entry = self._portal_amount.get(gstin)
        if entry is None:
            return []
        values, order = entry
        start = bisect_left(values, amount - tolerance)
        stop = bisect_right(values, amount + tolerance)
        if stop - start <= 1:
            return order[start:stop]
        return sorted(order[start:stop])

    def amount_pair(
        self, portal_pos: int, used_books: set[int], tolerance: Decimal
    ) -> tuple[int, int] | None:
        """Two unused book bills that add up to this portal line, in file order."""
        portal = self.portal[portal_pos]
        target = portal.amount
        entry = self._book_amount.get(portal.gstin)
        if target is None or entry is None:
            return None
        values, order = entry
        if not values:
            return None
        # A partner's amount is one of these values, so this candidate can only
        # pair when its own amount leaves room for one. Cheap, exact pruning:
        # it skips the bisect on months where no pair can add up at all.
        lowest = target - values[-1] - tolerance
        highest = target - values[0] + tolerance
        for position in self.book_pool(portal_pos):
            if position in used_books:
                continue
            amount = self.books[position].amount
            if amount is None:
                continue
            if amount < lowest or amount > highest:
                continue
            start = bisect_left(values, target - amount - tolerance)
            stop = bisect_right(values, target - amount + tolerance)
            partner: int | None = None
            for slot in range(start, stop):
                other = order[slot]
                if other <= position or other in used_books:
                    continue
                if not _dates_agree(self.books[other].date, portal.date, self.days):
                    continue
                if partner is None or other < partner:
                    partner = other
            if partner is not None:
                return (position, partner)
        return None

    def amount_triple(
        self, portal_pos: int, used_books: set[int], tolerance: Decimal
    ) -> tuple[int, int, int] | None:
        """Three unused book bills that add up to this portal line, in file order."""
        portal = self.portal[portal_pos]
        target = portal.amount
        entry = self._book_amount.get(portal.gstin)
        if target is None or entry is None:
            return None
        values, order = entry
        if not values:
            return None
        pool = [
            position
            for position in self.book_pool(portal_pos)
            if position not in used_books and self.books[position].amount is not None
        ]
        for slot, position in enumerate(pool):
            first = self.books[position].amount
            if first is None:  # pragma: no cover - filtered above
                continue
            # The other two bills must fall between the lowest and highest book
            # amount for this supplier, so most candidates drop out here.
            if first < target - 2 * values[-1] - tolerance:
                continue
            if first > target - 2 * values[0] + tolerance:
                continue
            for second_slot in range(slot + 1, len(pool)):
                second = pool[second_slot]
                second_amount = self.books[second].amount
                if second_amount is None:  # pragma: no cover - filtered above
                    continue
                running = first + second_amount
                start = bisect_left(values, target - running - tolerance)
                stop = bisect_right(values, target - running + tolerance)
                partner: int | None = None
                for index in range(start, stop):
                    third = order[index]
                    if third <= second or third in used_books:
                        continue
                    if not _dates_agree(self.books[third].date, portal.date, self.days):
                        continue
                    if partner is None or third < partner:
                        partner = third
                if partner is not None:
                    return (position, second, partner)
        return None


def _split_portal_group(
    index: "_ReconIndex",
    book_pos: int,
    used_2b: set[int],
    tolerance: Decimal,
) -> list[int]:
    """Portal lines that together add up to this one books invoice."""
    book = index.books[book_pos]
    if not book.gstin or not book.invoice or book.amount is None:
        return []
    group: list[int] = []
    for portal_pos in index.portal_lines(book.gstin, book.invoice):
        if portal_pos in used_2b:
            continue
        if not _dates_agree(book.date, index.portal[portal_pos].date, index.days):
            continue
        group.append(portal_pos)
    if len(group) < 2:
        return []
    total = Decimal("0")
    for portal_pos in group:
        value = index.portal[portal_pos].amount
        if value is None:
            return []
        total += value
    return group if (total - book.amount).copy_abs() <= tolerance else []


#: A three-bill split is only searched while the candidate set is small.  Each
#: extra candidate multiplies the work, so one supplier with hundreds of bills
#: on the same date would otherwise crawl through every combination for every
#: portal line in the month.  Past this cap the row falls through to the
#: ordinary books_only / portal_only answer, which is honest: the split was not
#: proven, and the CA sees the row as unsupported rather than a guess.
_TRIPLE_CANDIDATE_CAP = 40


def _split_books_group(
    index: "_ReconIndex",
    portal_pos: int,
    used_books: set[int],
    tolerance: Decimal,
) -> list[int]:
    """Several books bills that add up to this one portal line.

    Each candidate's amount is read once, and a pair is found by looking the
    partner's amount up instead of trying every combination of bills.
    """
    portal = index.portal[portal_pos]
    if not portal.gstin or portal.amount is None:
        return []
    pool = index.book_pool(portal_pos)
    if len(pool) < 2:
        return []
    pair = index.amount_pair(portal_pos, used_books, tolerance)
    if pair is not None:
        return list(pair)
    if len(pool) > _TRIPLE_CANDIDATE_CAP:
        return []
    triple = index.amount_triple(portal_pos, used_books, tolerance)
    return list(triple) if triple is not None else []


_NAME_STOPWORDS = frozenset(
    {"pvt", "ltd", "limited", "private", "and", "the", "co", "company", "traders", "trading",
     "enterprises", "enterprise", "india", "inc", "llp"}
)


def _party_tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    return {word for word in words if len(word) >= 3 and word not in _NAME_STOPWORDS}


def _same_party(left: str, right: str) -> bool:
    a = _party_tokens(left)
    b = _party_tokens(right)
    if not a or not b:
        return False
    return bool(a & b)


def _books_party(row: dict) -> str:
    return str(row.get("supplier_name") or row.get("party_name") or row.get("trade_name") or "")


def _supplier_agrees(
    book: dict,
    other_book: dict,
    portal: dict | None,
) -> bool:
    """Can these two rows be the same supplier?

    One source often knows only the GSTIN (an invoice PDF) and the other only
    the name (a Tally ledger), so the portal line the matched copy reconciled
    against is used as the shared identity when the books disagree on shape.
    """
    book_gstin = _books_gstin(book)
    other_gstin = _books_gstin(other_book)
    portal_gstin = _gstr_gstin(portal) if portal else ""
    book_party = _books_party(book)
    other_party = _books_party(other_book)
    portal_party = (
        str(portal.get("trade_name") or portal.get("supplier_name") or "") if portal else ""
    )
    if book_gstin:
        if other_gstin and book_gstin == other_gstin:
            return True
        if portal_gstin and book_gstin == portal_gstin:
            return True
    if book_party:
        if other_party and _same_party(book_party, other_party):
            return True
        if portal_party and _same_party(book_party, portal_party):
            return True
    return False


def _same_bill_twin(
    book: dict,
    books: list[dict],
    candidates: list[tuple[int, int]],
    twob: list[dict],
    days: int,
    tolerance: Decimal,
) -> str | None:
    """Return the invoice number of an already-reconciled copy of this bill.

    Two book entries are the same bill when they share a supplier, agree on the
    amount, and sit within a few days of each other — the only difference being
    the invoice number each source happened to record.
    """
    amount = _books_amount(book)
    if amount is None or not candidates:
        return None
    when = _books_date(book)
    window = max(int(days or 0), 7)
    for other_index, portal_index in candidates:
        other = books[other_index]
        other_amount = _books_amount(other)
        if other_amount is None or (other_amount - amount).copy_abs() > tolerance:
            continue
        portal = twob[portal_index] if 0 <= portal_index < len(twob) else None
        if not _supplier_agrees(book, other, portal):
            continue
        other_when = _books_date(other)
        if when and other_when and abs((when - other_when).days) > window:
            continue
        invoice = str(other.get("invoice_number") or "").strip()
        if not invoice and portal:
            invoice = str(portal.get("invoice_number") or "").strip()
        if invoice:
            return invoice
    return None


def _duplicate_items(
    books: list[dict],
    twob: list[dict],
    used_books: set[int],
    used_2b: set[int],
    tolerance: Decimal,
) -> list[tuple[int, str, int]]:
    """Unmatched rows that are extra copies of the same invoice on one side.

    A real duplicate carries the same invoice number and the same amount. When
    the amounts differ the rows are partial lines (a split that does not add
    up), so they are left to the ordinary one-sided groups instead.
    """
    found: list[tuple[int, str, int]] = []
    for side, rows, used in (("books", books, used_books), ("portal", twob, used_2b)):
        groups: dict[tuple[str, str], list[int]] = {}
        for index, row in enumerate(rows):
            gstin = _books_gstin(row) if side == "books" else _gstr_gstin(row)
            inv = _books_invoice(row) if side == "books" else _gstr_invoice(row)
            if not gstin or not inv:
                continue
            groups.setdefault((gstin, inv), []).append(index)
        for indices in groups.values():
            if len(indices) < 2:
                continue
            amounts = [
                _books_amount(rows[i]) if side == "books" else _gstr_amount(rows[i])
                for i in indices
            ]
            if any(value is None for value in amounts):
                continue
            first = amounts[0]
            if any((value - first).copy_abs() > tolerance for value in amounts[1:]):
                continue
            for index in indices:
                if index in used:
                    continue
                found.append((index, side, len(indices)))
    return found


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def _fmt_amount(value: Decimal | None):
    if value is None:
        return None
    return float(value)


def _recon_row(
    status: str,
    book: dict,
    portal: dict,
    *,
    extra_portal: list[dict] | None = None,
    tolerance: Decimal | None = None,
    group_size: int = 1,
    side: str = "",
    same_bill_of: str = "",
) -> dict:
    extra = list(extra_portal or [])
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    amt_2b = _gstr_amount(portal) if portal else None
    if extra:
        total = amt_2b if amt_2b is not None else Decimal("0")
        for line in extra:
            value = _gstr_amount(line)
            if value is not None:
                total += value
        amt_2b = total
    amt_books = _books_amount(book) if book else None
    diff = None
    if amt_2b is not None and amt_books is not None:
        diff = amt_2b - amt_books
    party = ""
    if portal:
        party = str(portal.get("trade_name") or portal.get("supplier_name") or portal.get("party_name") or "")
    if not party and book:
        party = str(book.get("supplier_name") or book.get("party_name") or book.get("trade_name") or "")
    gstin = _gstr_gstin(portal) if portal else ""
    if not gstin and book:
        gstin = _books_gstin(book)
    gaps = _tax_gaps(book, portal, limit) if status == "tax_mismatch" else []
    row = {
        "status": status,
        "gstin": gstin,
        "party": party,
        "invoice_2b": str(portal.get("invoice_number") or "") if portal else "",
        "invoice_books": str(book.get("invoice_number") or "") if book else "",
        "date_2b": _fmt_date(_gstr_date(portal) if portal else None),
        "date_books": _fmt_date(_books_date(book) if book else None),
        "amount_2b": _fmt_amount(amt_2b),
        "amount_books": _fmt_amount(amt_books),
        "amount_diff": _fmt_amount(diff),
        "reason": _reason(
            status,
            book,
            portal,
            diff,
            str(book.get("invoice_number") or "") if book else "",
            str(portal.get("invoice_number") or "") if portal else "",
            gaps=gaps,
            group_size=group_size,
            side=side,
            same_bill_of=same_bill_of,
        ),
        "bank_hint": "",
        "source_2b": str(portal.get("source") or "") if portal else "",
        "source_books": str(book.get("source") or "") if book else "",
    }
    if status != "credit_note" and not extra:
        for slug, keys, _label in _TAX_COMPONENTS:
            row[f"tax_{slug}_2b"] = _fmt_amount(_tax_value(portal, keys) if portal else None)
            row[f"tax_{slug}_books"] = _fmt_amount(_tax_value(book, keys) if book else None)
    return row


def _reason(
    status: str,
    book: dict,
    portal: dict,
    diff: Decimal | None,
    invoice_books: str,
    invoice_2b: str,
    *,
    gaps: list[tuple[str, Decimal]] | None = None,
    group_size: int = 1,
    side: str = "",
    same_bill_of: str = "",
) -> str:
    if status == "matched":
        return "Supplier, invoice number, date and amount all agree."
    if status == "amount_mismatch":
        size = diff.copy_abs() if diff is not None else Decimal("0")
        return f"Invoice number, date and supplier agree, but the amounts differ by {size:.2f}."
    if status == "tax_mismatch":
        parts = [
            f"{label} differs by {value.copy_abs():.2f}" for label, value in (gaps or [])
        ]
        detail = " and ".join(parts) if parts else "a tax component differs"
        return f"Supplier, invoice, date and total agree, but {detail}."
    if status == "likely":
        return (
            "Date and amount agree, but the invoice numbers differ "
            f"(books '{invoice_books}' vs portal '{invoice_2b}') — confirm this is the same invoice."
        )
    if status == "same_bill":
        other = (same_bill_of or "").strip()
        if other:
            return (
                f"This is the same bill as invoice {other}, which is already matched; "
                "it is a second copy from another book source, not extra credit."
            )
        return (
            "This looks like the same bill already matched through another book "
            "source, not extra credit."
        )
    if status == "books_only":
        return "This invoice appears only in the books; the GST portal download shows nothing like it."
    if status == "portal_only":
        return "This invoice appears only in the GST portal download; the books have no entry for it."
    if status == "credit_note":
        invoice = str(portal.get("invoice_number") or "").strip()
        where = f"Credit note {invoice}" if invoice else "A credit note"
        party = str(portal.get("trade_name") or portal.get("supplier_name") or "").strip()
        if party:
            where = f"{where} from {party}"
        return f"{where}: kept on its own so the credit is not lost; it is not matched to a purchase."
    if status == "duplicate":
        invoice = invoice_books or invoice_2b
        where = "books" if side == "books" else "2B download"
        times = "twice" if side == "books" and group_size == 2 else f"{group_size} times"
        return (
            f"Invoice {invoice} appears {times} in the {where}; "
            "only one entry is expected, so each copy is shown separately."
        )
    if status == "split_merged":
        if side == "books":
            return (
                f"These {group_size} bills add up to a single line in the 2B download; "
                "they are shown together so the money is not counted twice."
            )
        return (
            f"This invoice is split across {group_size} lines in the 2B download; "
            "together they add up to the books amount."
        )
    return ""


@dataclass(frozen=True, slots=True)
class _BankLine:
    """One bank line, read once so hinting never re-parses it."""

    position: int
    date: date | None
    debit: Decimal | None
    credit: Decimal | None
    amount: Decimal | None
    narration: str
    words: frozenset[str]


class _BankHintIndex:
    """Bank lines looked up by amount, so a hint never scans the statement.

    Every reconciliation row used to score every bank line, re-parsing that
    line's date and amounts on every comparison; a 398-file month spent hours
    here.  The lines are read once instead, and a row only looks at lines
    whose amount is within the rupee allowance.  That window loses nothing:
    the amount match is worth 50 of the 100 points, so a line outside it can
    never reach the 70 a hint needs.
    """

    __slots__ = ("lines", "_amounts", "_order")

    def __init__(self, bank_rows: list[dict]) -> None:
        self.lines: list[_BankLine] = []
        for position, row in enumerate(bank_rows):
            debit = money(row.get("debit"))
            credit = money(row.get("credit"))
            narration = str(row.get("narration") or row.get("description") or "")
            self.lines.append(
                _BankLine(
                    position=position,
                    date=parse_recon_date(row.get("date")),
                    debit=debit,
                    credit=credit,
                    amount=debit if debit not in (None, Decimal("0")) else credit,
                    narration=narration,
                    words=_party_word_tokens(narration),
                )
            )
        usable = sorted(
            (line.amount, line.position) for line in self.lines if line.amount is not None
        )
        self._amounts = [amount for amount, _position in usable]
        self._order = [position for _amount, position in usable]

    def best(
        self,
        amount: Decimal | None,
        when: date | None,
        party: str,
        tolerance: Decimal | None = None,
    ) -> _BankLine | None:
        """The highest-scoring line, and the earliest line on a tie."""
        if amount is None or not self._order:
            return None
        limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
        start = bisect_left(self._amounts, amount - limit)
        stop = bisect_right(self._amounts, amount + limit)
        if start >= stop:
            return None
        candidates = self._order[start:stop]
        if len(candidates) > 1:
            # Amount order is not file order; a tie must keep the old winner.
            candidates = sorted(candidates)
        party_words = _party_word_tokens(party)
        best_score = 0
        best_line: _BankLine | None = None
        for position in candidates:
            line = self.lines[position]
            score = _bank_score(line, amount, when, party_words, limit)
            if score > best_score:
                best_score = score
                best_line = line
        if best_score < 70 or best_line is None:
            return None
        return best_line


def _bank_hint(
    row: dict,
    book: dict,
    portal: dict,
    bank: _BankHintIndex,
    tolerance: Decimal | None = None,
) -> str:
    amount = _books_amount(book) if book else None
    if amount is None and portal:
        amount = _gstr_amount(portal)
    if amount is None:
        # A line can earn the 50 amount points only when the row has an amount,
        # so nothing can reach the 70 needed: there is nothing to look up.
        return ""
    when = _books_date(book) if book else None
    if when is None and portal:
        when = _gstr_date(portal)
    best_line = bank.best(amount, when, str(row.get("party") or ""), tolerance)
    if best_line is None:
        return ""
    shown = best_line.debit if best_line.debit else best_line.credit
    narr = best_line.narration.strip()
    snippet = re.sub(r"\s+", " ", narr)[:40]
    parts = []
    if best_line.date:
        parts.append(best_line.date.isoformat())
    if shown is not None:
        parts.append(f"{shown:.2f}")
    if snippet:
        parts.append(snippet)
    return " | ".join(parts)


def _bank_score(
    line: _BankLine,
    amount: Decimal | None,
    when: date | None,
    party_words: frozenset[str],
    tolerance: Decimal | None = None,
) -> int:
    score = 0
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    if amount is not None and line.amount is not None and (amount - line.amount).copy_abs() <= limit:
        score += 50
    if when is not None and line.date is not None and abs((when - line.date).days) <= 7:
        score += 20
    if party_words and line.words and (party_words & line.words):
        score += 20
    if line.debit not in (None, Decimal("0")):
        score += 10
    return score


def _party_word_tokens(value: str) -> frozenset[str]:
    return frozenset(re.findall(r"[A-Za-z]{3,}", (value or "").upper()))


def _name_overlap(party: str, narration: str) -> bool:
    return bool(_party_word_tokens(party) & _party_word_tokens(narration))


# ---------------------------------------------------------------------------
# Generic comparison engine
#
# The GST reconciliation above is deliberately narrow: GSTR-2B against books,
# with the statuses the existing pack writer already understands.  The helpers
# below compare any two extracted datasets (purchase invoices, purchase
# registers, bank statements) without changing the source rows.  Matching is
# one-to-one, keyed on identifiers first, and only falls back to a candidate
# that a human must review.  Amount similarity alone never produces a match.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ValueRecord:
    index: int
    row: dict
    gstin: str
    reference: str
    reference_display: str
    date: date | None
    date_display: str
    party: str
    amount: Decimal | None
    taxable: Decimal | None
    tax: Decimal | None
    source: str
    currency: str


@dataclass(frozen=True)
class _BankRecord:
    index: int
    row: dict
    date: date | None
    date_display: str
    text: str
    reference: str
    amount: Decimal | None
    direction: str
    source: str
    currency: str


def _tax_total(row: dict) -> Decimal | None:
    direct = _row_money(row, "tax", "tax_amount")
    if direct is not None:
        return direct
    parts = [
        _row_money(row, "igst"),
        _row_money(row, "cgst"),
        _row_money(row, "sgst"),
        _row_money(row, "cess"),
    ]
    present = [value for value in parts if value is not None]
    if not present:
        return None
    return sum(present, Decimal("0"))


def _first_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _value_record(row: dict, index: int) -> _ValueRecord:
    reference_display = _first_text(
        row, "invoice_number", "voucher_number", "reference", "bill_number"
    )
    date_raw = _first_text(
        row, "invoice_date", "voucher_date", "date", "posting_date", "document_date"
    )
    parsed_date = _row_date(
        row, "invoice_date", "voucher_date", "date", "posting_date", "document_date"
    )
    party = _first_text(
        row,
        "supplier_name",
        "party_name",
        "trade_name",
        "customer_name",
        "vendor_name",
    )
    return _ValueRecord(
        index=index,
        row=row,
        gstin=_gstin(row, "supplier_gstin", "gstin", "party_gstin"),
        reference=_invoice(
            row, "invoice_number", "voucher_number", "reference", "bill_number"
        ),
        reference_display=reference_display,
        date=parsed_date,
        date_display=parsed_date.isoformat() if parsed_date else date_raw,
        party=party,
        amount=_row_money(row, "invoice_value", "amount", "total"),
        taxable=_row_money(row, "taxable_value", "taxable"),
        tax=_tax_total(row),
        source=_first_text(row, "source"),
        currency=_first_text(row, "currency_code", "currency"),
    )


def _bank_record(row: dict, index: int) -> _BankRecord:
    debit = money(row.get("debit"))
    credit = money(row.get("credit"))
    if debit is not None and debit != 0:
        amount = debit.copy_abs()
        direction = "debit"
    elif credit is not None and credit != 0:
        amount = credit.copy_abs()
        direction = "credit"
    elif debit is not None:
        amount = debit.copy_abs()
        direction = "debit"
    elif credit is not None:
        amount = credit.copy_abs()
        direction = "credit"
    else:
        amount = None
        direction = ""
    text = _first_text(row, "description", "narration", "detail")
    parsed_date = _row_date(row, "date", "transaction_date", "value_date")
    date_raw = _first_text(row, "date", "transaction_date", "value_date")
    return _BankRecord(
        index=index,
        row=row,
        date=parsed_date,
        date_display=parsed_date.isoformat() if parsed_date else date_raw,
        text=text,
        reference=_first_text(row, "cheque_ref", "reference"),
        amount=amount,
        direction=direction,
        source=_first_text(row, "source"),
        currency=_first_text(row, "currency_code", "currency"),
    )


def _row_meta(row: dict, key: str):
    return row.get(f"_ca_{key}")


def _public_record(record: _ValueRecord) -> dict:
    return {
        "row_id": _row_meta(record.row, "row_id"),
        "file_id": _row_meta(record.row, "file_id"),
        "file_name": _row_meta(record.row, "file_name"),
        "kind": _row_meta(record.row, "kind"),
        "reference": record.reference_display,
        "normalized_reference": record.reference,
        "date": record.date_display,
        "party": record.party,
        "gstin": record.gstin,
        "amount": _fmt_amount(record.amount),
        "taxable": _fmt_amount(record.taxable),
        "tax": _fmt_amount(record.tax),
        "currency": record.currency,
        "source": record.source,
        "source_page": _row_meta(record.row, "page") or record.row.get("source_page"),
        "source_bbox": _row_meta(record.row, "bbox") or record.row.get("source_bbox"),
    }


def _public_bank(record: _BankRecord) -> dict:
    return {
        "row_id": _row_meta(record.row, "row_id"),
        "file_id": _row_meta(record.row, "file_id"),
        "file_name": _row_meta(record.row, "file_name"),
        "kind": _row_meta(record.row, "kind") or "bank",
        "reference": record.reference,
        "normalized_reference": normalize_invoice_number(record.reference),
        "date": record.date_display,
        "description": record.text,
        "direction": record.direction,
        "amount": _fmt_amount(record.amount),
        "currency": record.currency,
        "source": record.source,
        "source_page": _row_meta(record.row, "page") or record.row.get("source_page"),
        "source_bbox": _row_meta(record.row, "bbox") or record.row.get("source_bbox"),
    }


def _abs_diff(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return (left - right).copy_abs()


def _date_diff(left: date | None, right: date | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left - right).days)


def _date_within(
    left: date | None, right: date | None, days: int, *, missing_ok: bool = True
) -> bool:
    difference = _date_diff(left, right)
    if difference is None:
        return missing_ok
    return difference <= days


def _currencies_match(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left.strip().upper() == right.strip().upper()


def _amount_close(
    left: Decimal | None,
    right: Decimal | None,
    tolerance: Decimal = AMOUNT_TOLERANCE,
) -> bool:
    difference = _abs_diff(left, right)
    return difference is not None and difference <= tolerance


def _name_overlap_count(left: str, right: str) -> int:
    left_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (left or "").upper())}
    right_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (right or "").upper())}
    return len(left_tokens & right_tokens)


def _reference_prefix(left: str, right: str) -> bool:
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _differences(
    left: _ValueRecord, right: _ValueRecord
) -> dict:
    return {
        "amount": _fmt_amount(_abs_diff(left.amount, right.amount)),
        "taxable": _fmt_amount(_abs_diff(left.taxable, right.taxable)),
        "tax": _fmt_amount(_abs_diff(left.tax, right.tax)),
        "date_days": _date_diff(left.date, right.date),
    }


def _pair_status(
    left: _ValueRecord,
    right: _ValueRecord,
    tolerance: Decimal,
    date_window_days: int,
) -> tuple[str, str]:
    if not _currencies_match(left.currency, right.currency):
        return "review_required", "currency_differs"
    amount_difference = _abs_diff(left.amount, right.amount)
    if amount_difference is None:
        return "review_required", "amount_missing"
    if amount_difference > tolerance:
        return "amount_mismatch", "total_differs"
    tax_difference = _abs_diff(left.tax, right.tax)
    if tax_difference is not None and tax_difference > tolerance:
        return "review_required", "tax_differs"
    taxable_difference = _abs_diff(left.taxable, right.taxable)
    if taxable_difference is not None and taxable_difference > tolerance:
        return "review_required", "taxable_differs"
    date_difference = _date_diff(left.date, right.date)
    if date_difference is not None and date_difference > date_window_days:
        return "review_required", "date_differs"
    return "matched", "values_agree"


def _explain(
    status: str,
    reason: str,
    left: _ValueRecord | _BankRecord | None,
    right: _ValueRecord | _BankRecord | None,
) -> str:
    if status == "matched":
        if reason == "bank_reference":
            return "The reference found in the bank narration and the amount agree."
        return "GSTIN/reference, date and amount agree."
    if status == "amount_mismatch":
        difference = _abs_diff(
            getattr(left, "amount", None), getattr(right, "amount", None)
        )
        shown = _fmt_amount(difference)
        tail = f" Difference is {shown:.2f}." if shown is not None else ""
        return f"Same reference but the total does not agree.{tail}".strip()
    if status == "review_required":
        return {
            "tax_differs": "The totals agree but the tax value differs. Confirm before relying on this match.",
            "taxable_differs": "The totals agree but the taxable value differs. Confirm before relying on this match.",
            "date_differs": "The reference and amount agree but the dates are far apart. Confirm this match.",
            "currency_differs": "The reference agrees but the currencies differ. No conversion is performed.",
            "amount_missing": "The reference agrees but one side has no readable amount.",
            "same_reference": "The reference agrees but the GSTIN needs confirmation.",
            "reference_prefix": "The invoice numbers share a prefix and the amount agrees. Confirm this match.",
            "name_amount_date": "The party, amount and nearby date agree, but there is no shared reference. Confirm this match.",
            "bank_reference": "The bank narration mentions this voucher reference and the amount agrees.",
            "bank_fuzzy": "The amount, date and party overlap, but no reference is present. Confirm this match.",
            "multiple_candidates": "More than one record looks similar. Choose the correct match manually.",
        }.get(reason, "This record needs a human check before it can be relied on.")
    if status == "duplicate":
        return "This reference appears more than once. No automatic one-to-one pairing was made."
    if status == "left_only":
        return "No matching record was found in the comparison dataset."
    if status == "right_only":
        return "No matching record was found in the comparison dataset."
    return ""


def _pair_row(
    status: str,
    reason: str,
    left: _ValueRecord | _BankRecord | None = None,
    right: _ValueRecord | _BankRecord | None = None,
    explanation: str | None = None,
) -> dict:
    left_payload = None
    right_payload = None
    if isinstance(left, _ValueRecord):
        left_payload = _public_record(left)
    elif isinstance(left, _BankRecord):
        left_payload = _public_bank(left)
    if isinstance(right, _ValueRecord):
        right_payload = _public_record(right)
    elif isinstance(right, _BankRecord):
        right_payload = _public_bank(right)
    differences = {"amount": None, "taxable": None, "tax": None, "date_days": None}
    if isinstance(left, _ValueRecord) and isinstance(right, _ValueRecord):
        differences = _differences(left, right)
    elif isinstance(left, (_ValueRecord, _BankRecord)) and isinstance(
        right, (_ValueRecord, _BankRecord)
    ):
        differences["amount"] = _fmt_amount(
            _abs_diff(getattr(left, "amount", None), getattr(right, "amount", None))
        )
        differences["date_days"] = _date_diff(left.date, right.date)
    return {
        "status": status,
        "reason_code": reason,
        "explanation": explanation or _explain(status, reason, left, right),
        "left": left_payload,
        "right": right_payload,
        "differences": differences,
    }


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in GENERIC_STATUS_KEYS}


def _count_rows(rows: list[dict]) -> dict[str, int]:
    counts = _empty_counts()
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def compare_records(
    left_rows: list[dict],
    right_rows: list[dict],
    *,
    amount_tolerance: Decimal = AMOUNT_TOLERANCE,
    date_window_days: int = 30,
) -> dict:
    """Compare two invoice-like datasets one-to-one.

    Exact GSTIN + invoice-number groups are paired first.  Remaining rows may
    only become a review candidate when a reference, invoice-number prefix, or
    party name also supports the amount.  Similar amounts alone never match.
    """
    left = [_value_record(row, index) for index, row in enumerate(left_rows or [])]
    right = [_value_record(row, index) for index, row in enumerate(right_rows or [])]
    used_left: set[int] = set()
    used_right: set[int] = set()
    rows: list[dict] = []

    def claim(status: str, reason: str, li: int, ri: int) -> None:
        if li in used_left or ri in used_right:
            return
        used_left.add(li)
        used_right.add(ri)
        rows.append(_pair_row(status, reason, left[li], right[ri]))

    left_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    right_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record in left:
        if record.gstin and record.reference:
            left_groups[(record.gstin, record.reference)].append(record.index)
    for record in right:
        if record.gstin and record.reference:
            right_groups[(record.gstin, record.reference)].append(record.index)

    for key in sorted(set(left_groups) & set(right_groups)):
        pending_left = [i for i in left_groups[key] if i not in used_left]
        pending_right = [i for i in right_groups[key] if i not in used_right]
        if not pending_left or not pending_right:
            continue
        amount_pairs = [
            (li, ri)
            for li in pending_left
            for ri in pending_right
            if _amount_close(left[li].amount, right[ri].amount, amount_tolerance)
        ]
        left_candidates: dict[int, list[int]] = defaultdict(list)
        right_candidates: dict[int, list[int]] = defaultdict(list)
        for li, ri in amount_pairs:
            left_candidates[li].append(ri)
            right_candidates[ri].append(li)
        for li, ri in amount_pairs:
            if li in used_left or ri in used_right:
                continue
            if len(left_candidates[li]) != 1 or len(right_candidates[ri]) != 1:
                continue
            status, reason = _pair_status(
                left[li], right[ri], amount_tolerance, date_window_days
            )
            claim(status, reason, li, ri)

        pending_left = [i for i in left_groups[key] if i not in used_left]
        pending_right = [i for i in right_groups[key] if i not in used_right]
        if len(pending_left) == 1 and len(pending_right) == 1:
            status, reason = _pair_status(
                left[pending_left[0]],
                right[pending_right[0]],
                amount_tolerance,
                date_window_days,
            )
            # Reaching this branch means the amounts did not pair.  Preserve
            # that as an amount mismatch instead of calling it a likely match.
            if status == "matched":
                status, reason = "amount_mismatch", "total_differs"
            claim(status, reason, pending_left[0], pending_right[0])
            continue
        for li in pending_left:
            used_left.add(li)
            rows.append(_pair_row("duplicate", "duplicate_key", left[li], None))
        for ri in pending_right:
            used_right.add(ri)
            rows.append(_pair_row("duplicate", "duplicate_key", None, right[ri]))

    # Candidate pass: unique, supported, and explicitly left for review.
    for record in left:
        if record.index in used_left:
            continue
        candidates: list[tuple[int, str]] = []
        for other in right:
            if other.index in used_right:
                continue
            reason = _review_candidate(record, other, amount_tolerance)
            if reason:
                candidates.append((other.index, reason))
        if len(candidates) != 1:
            continue
        ri, reason = candidates[0]
        used_left.add(record.index)
        used_right.add(ri)
        rows.append(_pair_row("review_required", reason, record, right[ri]))

    for record in left:
        if record.index not in used_left:
            used_left.add(record.index)
            rows.append(_pair_row("left_only", "no_counterpart", record, None))
    for record in right:
        if record.index not in used_right:
            used_right.add(record.index)
            rows.append(_pair_row("right_only", "no_counterpart", None, record))

    return {"rows": rows, "counts": _count_rows(rows)}


def _review_candidate(
    left: _ValueRecord,
    right: _ValueRecord,
    amount_tolerance: Decimal,
) -> str | None:
    if not _currencies_match(left.currency, right.currency):
        return None
    if not _amount_close(left.amount, right.amount, amount_tolerance):
        return None
    same_reference = bool(
        left.reference and right.reference and left.reference == right.reference
    )
    if same_reference and _date_within(left.date, right.date, 30):
        if not left.gstin or not right.gstin or left.gstin != right.gstin:
            return "same_reference"
    if (
        left.gstin
        and right.gstin
        and left.gstin == right.gstin
        and _reference_prefix(left.reference, right.reference)
        and _date_within(left.date, right.date, 7)
    ):
        return "reference_prefix"
    overlap = _name_overlap_count(left.party, right.party)
    if overlap and _date_within(left.date, right.date, 3):
        if overlap >= 2 or any(
            len(token) >= 5
            for token in (
                set(re.findall(r"[A-Za-z]{3,}", left.party.upper()))
                & set(re.findall(r"[A-Za-z]{3,}", right.party.upper()))
            )
        ):
            return "name_amount_date"
    return None


def _bank_mentions_reference(text: str, reference: str) -> bool:
    normalised_reference = normalize_invoice_number(reference)
    if len(normalised_reference) < 4:
        return False
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9/\-]*", text or "")
    if any(normalize_invoice_number(token) == normalised_reference for token in tokens):
        return True
    if len(normalised_reference) < 6:
        return False
    return normalised_reference in normalize_invoice_number(text)


def _bank_pair_status(
    bank: _BankRecord,
    ledger: _ValueRecord,
    amount_tolerance: Decimal,
    reference_window_days: int,
) -> tuple[str, str]:
    if not _currencies_match(bank.currency, ledger.currency):
        return "review_required", "currency_differs"
    difference = _abs_diff(bank.amount, ledger.amount)
    if difference is None:
        return "review_required", "amount_missing"
    if difference > amount_tolerance:
        return "amount_mismatch", "total_differs"
    if not _date_within(bank.date, ledger.date, reference_window_days):
        return "review_required", "date_differs"
    return "matched", "bank_reference"


def compare_bank_ledger(
    bank_rows: list[dict],
    ledger_rows: list[dict],
    *,
    amount_tolerance: Decimal = AMOUNT_TOLERANCE,
    reference_window_days: int = 45,
    fuzzy_window_days: int = 3,
) -> dict:
    """Compare bank statement lines with accounting vouchers.

    A reference found in the narration plus an agreeing amount is a match.
    Amount + nearby date + party overlap without a reference is only ever a
    review candidate.  Amount similarity alone is not enough.
    """
    bank = [_bank_record(row, index) for index, row in enumerate(bank_rows or [])]
    ledger = [_value_record(row, index) for index, row in enumerate(ledger_rows or [])]
    used_bank: set[int] = set()
    used_ledger: set[int] = set()
    rows: list[dict] = []

    for line in bank:
        candidates = [
            other
            for other in ledger
            if other.index not in used_ledger
            and other.reference
            and _bank_mentions_reference(line.text, other.reference)
        ]
        if len(candidates) > 1:
            amount_candidates = [
                item
                for item in candidates
                if _amount_close(line.amount, item.amount, amount_tolerance)
            ]
            if len(amount_candidates) == 1:
                candidates = amount_candidates
        if len(candidates) > 1:
            used_bank.add(line.index)
            rows.append(
                _pair_row(
                    "review_required",
                    "multiple_candidates",
                    line,
                    None,
                    explanation="More than one accounting entry mentions a matching reference. Choose the correct match manually.",
                )
            )
            continue
        if len(candidates) == 1:
            other = candidates[0]
            status, reason = _bank_pair_status(
                line, other, amount_tolerance, reference_window_days
            )
            used_bank.add(line.index)
            used_ledger.add(other.index)
            rows.append(_pair_row(status, reason, line, other))
            continue

        fuzzy = [
            other
            for other in ledger
            if other.index not in used_ledger
            and _currencies_match(line.currency, other.currency)
            and _amount_close(line.amount, other.amount, amount_tolerance)
            and _date_within(line.date, other.date, fuzzy_window_days)
            and _name_overlap(line.text, other.party)
        ]
        if len(fuzzy) == 1:
            other = fuzzy[0]
            used_bank.add(line.index)
            used_ledger.add(other.index)
            rows.append(_pair_row("review_required", "bank_fuzzy", line, other))
        elif len(fuzzy) > 1:
            used_bank.add(line.index)
            rows.append(
                _pair_row(
                    "review_required",
                    "multiple_candidates",
                    line,
                    None,
                    explanation="Several accounting entries have this amount and a nearby date. Choose the correct match manually.",
                )
            )

    for line in bank:
        if line.index not in used_bank:
            used_bank.add(line.index)
            rows.append(_pair_row("left_only", "no_counterpart", line, None))
    for other in ledger:
        if other.index not in used_ledger:
            used_ledger.add(other.index)
            rows.append(_pair_row("right_only", "no_counterpart", None, other))

    return {"rows": rows, "counts": _count_rows(rows)}
