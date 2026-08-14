from __future__ import annotations

from apps.engine.db import Firm, get_session
from apps.engine.library import get_library_path


def get_firm() -> dict | None:
    session = get_session()
    try:
        firm = session.query(Firm).order_by(Firm.id.asc()).first()
        if firm is None:
            return None
        return {
            "id": firm.id,
            "name": firm.name,
            "library_path": firm.library_path,
        }
    finally:
        session.close()


def save_firm(name: str) -> dict:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("Firm name is required.")
    if len(cleaned) > 200:
        raise ValueError("Firm name is too long.")

    session = get_session()
    try:
        firm = session.query(Firm).order_by(Firm.id.asc()).first()
        if firm is None:
            firm = Firm(name=cleaned, library_path=str(get_library_path()))
            session.add(firm)
        else:
            firm.name = cleaned
        session.commit()
        session.refresh(firm)
        return {
            "id": firm.id,
            "name": firm.name,
            "library_path": firm.library_path,
        }
    finally:
        session.close()
