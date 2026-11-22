from __future__ import annotations

import re
from datetime import date

from apps.engine.clients import get_client
from apps.engine.db import Period, get_session

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_YEAR_RE = re.compile(
    r"^\s*(?P<month>[A-Za-z]{3,9})[\s\-/.,]*(?P<year>(?:19|20)\d{2})\s*$"
)
_NUMERIC_RE = re.compile(
    r"^\s*(?P<month>\d{1,2})[\s\-/.,]+(?P<year>(?:19|20)\d{2})\s*$"
)


def suggested_period_label(today: date | None = None) -> str:
    when = today or date.today()
    return when.strftime("%b %Y")


def normalize_period_label(label: str) -> str:
    """Return the canonical ``Mon YYYY`` form, or raise a plain-language error.

    A period name ends up in folder names, dashboard filters and the workbook
    cover, so a typo ("13 2026", "Oct-26") used to create a second, unusable
    month. Only a real month plus a four-digit year is accepted now.
    """
    cleaned = " ".join(str(label or "").split())
    if not cleaned:
        raise ValueError("Give the month a name, e.g. Aug 2026.")
    if len(cleaned) > 80:
        raise ValueError("That month name is too long.")

    match = _MONTH_YEAR_RE.match(cleaned)
    if match:
        month = _MONTHS.get(match.group("month").lower())
        year = int(match.group("year"))
    else:
        match = _NUMERIC_RE.match(cleaned)
        month = int(match.group("month")) if match else None
        year = int(match.group("year")) if match else None
        if month is not None and not 1 <= month <= 12:
            month = None
    if not month:
        raise ValueError(
            "Use a month and year, e.g. Oct 2026. "
            "Numbers must look like 10/2026."
        )
    return date(year, month, 1).strftime("%b %Y")



def _period_dict(row: Period) -> dict:
    return {
        "id": row.id,
        "client_id": row.client_id,
        "label": row.label,
        "tolerance_days_override": row.tolerance_days_override,
        "tolerance_amount_override": row.tolerance_amount_override,
    }


def list_periods(client_id: int) -> list[dict]:
    session = get_session()
    try:
        rows = (
            session.query(Period)
            .filter(Period.client_id == client_id)
            .order_by(Period.created_at.desc())
            .all()
        )
        return [_period_dict(row) for row in rows]
    finally:
        session.close()


def get_period(period_id: int) -> dict | None:
    session = get_session()
    try:
        row = session.get(Period, period_id)
        if row is None:
            return None
        return _period_dict(row)
    finally:
        session.close()


def set_period_tolerances(period_id: int, days=None, amount=None) -> dict:
    """Set (or clear, with None) this month's allowance override."""
    from apps.engine.clients import _clean_amount, _clean_days

    days_value = None if days in (None, "") else _clean_days(days)
    amount_value = None if amount in (None, "") else _clean_amount(amount)
    session = get_session()
    try:
        row = session.get(Period, period_id)
        if row is None:
            raise ValueError("Period was not found.")
        row.tolerance_days_override = days_value
        row.tolerance_amount_override = amount_value
        session.commit()
        session.refresh(row)
        return _period_dict(row)
    finally:
        session.close()


def delete_period(period_id: int) -> dict:
    """Delete one month: its files, rows, pack and decisions, plus its folder.

    A mistyped period used to be permanent - the only way out was deleting the
    whole client. The client and the other months are left alone.
    """
    import shutil

    from apps.engine.db import DataPack, ExtractedRow, Job, ReconDecision, StoredFile
    from apps.engine.library import get_library_path
    from apps.engine.settings import get_output_root, safe_folder_name

    session = get_session()
    try:
        row = session.get(Period, period_id)
        if row is None:
            raise ValueError("Period was not found.")
        client = get_client(row.client_id) or {}
        label = row.label
        client_id = row.client_id
        busy = (
            session.query(Job)
            .filter(
                Job.period_id == period_id,
                Job.status.in_(("queued", "routing", "parsing", "cancel_requested")),
            )
            .count()
        )
        if busy:
            raise ValueError("This period is still being processed. Wait for it to finish.")
        session.query(ExtractedRow).filter(ExtractedRow.period_id == period_id).delete()
        session.query(DataPack).filter(DataPack.period_id == period_id).delete()
        session.query(ReconDecision).filter(ReconDecision.period_id == period_id).delete()
        session.query(StoredFile).filter(StoredFile.period_id == period_id).delete()
        session.query(Job).filter(Job.period_id == period_id).delete()
        session.delete(row)
        session.commit()
    finally:
        session.close()

    disk = get_library_path() / "files" / str(client_id) / str(period_id)
    if disk.exists():
        shutil.rmtree(disk, ignore_errors=True)
    root = get_output_root()
    if root is not None and client.get("name"):
        dest = root / safe_folder_name(client["name"]) / safe_folder_name(label)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
    return {"period_id": period_id, "client_id": client_id, "label": label}


def effective_tolerances(period_id: int) -> tuple[int, float]:
    """The allowance actually used: this month's override, else the client's."""
    period = get_period(period_id)
    if period is None:
        return (0, 1.0)
    if (
        period.get("tolerance_days_override") is not None
        and period.get("tolerance_amount_override") is not None
    ):
        return (
            int(period["tolerance_days_override"]),
            float(period["tolerance_amount_override"]),
        )
    client = get_client(period["client_id"]) or {}
    return (
        int(client.get("tolerance_days") or 0),
        float(client.get("tolerance_amount") if client.get("tolerance_amount") is not None else 1.0),
    )


def create_period(client_id: int, label: str) -> dict:
    if get_client(client_id) is None:
        raise ValueError("Client was not found.")
    cleaned = normalize_period_label(label)

    session = get_session()
    try:
        existing = (
            session.query(Period)
            .filter(Period.client_id == client_id, Period.label == cleaned)
            .first()
        )
        if existing is not None:
            raise ValueError(f"{cleaned} already exists for this client.")
        row = Period(client_id=client_id, label=cleaned)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _period_dict(row)
    finally:
        session.close()
