from __future__ import annotations

from datetime import date

from apps.engine.clients import get_client
from apps.engine.db import Period, get_session


def suggested_period_label(today: date | None = None) -> str:
    when = today or date.today()
    return when.strftime("%b %Y")


def list_periods(client_id: int) -> list[dict]:
    session = get_session()
    try:
        rows = (
            session.query(Period)
            .filter(Period.client_id == client_id)
            .order_by(Period.created_at.desc())
            .all()
        )
        return [{"id": row.id, "client_id": row.client_id, "label": row.label} for row in rows]
    finally:
        session.close()


def get_period(period_id: int) -> dict | None:
    session = get_session()
    try:
        row = session.get(Period, period_id)
        if row is None:
            return None
        return {"id": row.id, "client_id": row.client_id, "label": row.label}
    finally:
        session.close()


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
        return {"id": row.id, "client_id": row.client_id, "label": row.label}
    finally:
        session.close()
