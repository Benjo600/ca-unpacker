from __future__ import annotations

from datetime import date

from apps.engine.clients import get_client
from apps.engine.db import Period, get_session


def suggested_period_label(today: date | None = None) -> str:
    when = today or date.today()
    return when.strftime("%b %Y")


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
    cleaned = (label or "").strip()
    if not cleaned:
        raise ValueError("Give the period a name, e.g. Aug 2026.")
    if len(cleaned) > 80:
        raise ValueError("Period name is too long.")

    session = get_session()
    try:
        existing = (
            session.query(Period)
            .filter(Period.client_id == client_id, Period.label == cleaned)
            .first()
        )
        if existing is not None:
            raise ValueError("That period already exists for this client.")
        row = Period(client_id=client_id, label=cleaned)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _period_dict(row)
    finally:
        session.close()
