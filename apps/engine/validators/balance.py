from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def _d(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _row_flag_list(row: dict) -> list[str]:
    raw = row.get("flags")
    if raw is None:
        raw = row.get("validation_flags") or []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return list(raw)


def _stamp(row: dict, *extra: str) -> list[str]:
    flags = _row_flag_list(row)
    for item in extra:
        if item and item not in flags:
            flags.append(item)
    row["flags"] = flags
    row["validation_flags"] = flags
    return flags


def check_balance(rows: list[dict], opening: float | None, stated_closing: float | None) -> dict:
    flags: list[str] = []
    opening_inferred = opening is None
    running = _d(opening) if opening is not None else None
    if running is None and rows:
        first = rows[0]
        running = _d(first.get("balance")) + _d(first.get("debit")) - _d(first.get("credit"))

    computed = running if running is not None else Decimal("0")
    broken_at = None
    for index, row in enumerate(rows):
        computed = computed - _d(row.get("debit")) + _d(row.get("credit"))
        stated = row.get("balance")
        extra: list[str] = []
        if stated is None:
            extra.append("missing_balance")
            _stamp(row, *extra)
            continue
        if (computed - _d(stated)).copy_abs() > Decimal("1.00"):
            flags.append("balance_mismatch")
            extra.append("balance_mismatch")
            if broken_at is None:
                broken_at = index + 1
        computed = _d(stated)
        _stamp(row, *extra)

    last = _d(rows[-1].get("balance")) if rows else computed
    printed_open = opening is not None
    printed_close = stated_closing is not None
    stated_close = _d(stated_closing) if printed_close else None
    close_ok = (
        printed_close
        and stated_close is not None
        and (last - stated_close).copy_abs() <= Decimal("1.00")
    )
    if printed_close and not close_ok:
        flags.append("closing_mismatch")
        if rows:
            _stamp(rows[-1], "closing_mismatch")
    if not printed_open or not printed_close:
        match = False
        status = "unverified"
        flags.append("could_not_verify")
    elif "balance_mismatch" in flags or not close_ok:
        match = False
        status = "mismatch"
    else:
        match = True
        status = "match"

    def money(value: Decimal | None) -> float | None:
        if value is None:
            return None
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "opening_balance": money(running) if opening is not None or rows else None,
        "opening_inferred": opening_inferred,
        "stated_closing": money(stated_close) if printed_close else None,
        "computed_closing": money(last),
        "match": match,
        "status": status,
        "broken_at_row": broken_at,
        "flags": list(dict.fromkeys(flags)),
        "row_count": len(rows),
    }
