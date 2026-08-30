from __future__ import annotations

import re
import shutil

from apps.engine.db import Client, DataPack, ExtractedRow, Job, Period, StoredFile, get_session
from apps.engine.firm import get_firm, save_firm
from apps.engine.library import get_library_path
from apps.engine.settings import get_output_root, safe_folder_name

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")


def _normalize_gstin(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if len(cleaned) != 15:
        raise ValueError("GSTIN must be 15 characters if you enter one.")
    if not GSTIN_RE.match(cleaned):
        raise ValueError("That does not look like a GSTIN.")
    return cleaned


def get_client(client_id: int) -> dict | None:
    session = get_session()
    try:
        row = session.get(Client, client_id)
        if row is None:
            return None
        return {"id": row.id, "name": row.name, "gstin": row.gstin}
    finally:
        session.close()


def list_clients() -> list[dict]:
    session = get_session()
    try:
        rows = session.query(Client).order_by(Client.name.asc()).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "gstin": row.gstin,
            }
            for row in rows
        ]
    finally:
        session.close()


def create_client(name: str, gstin: str | None = None) -> dict:
    firm = get_firm()
    if firm is None:
        firm = save_firm("My firm")

    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("Client name is required.")
    if len(cleaned) > 200:
        raise ValueError("Client name is too long.")

    gstin_value = _normalize_gstin(gstin)

    session = get_session()
    try:
        existing = (
            session.query(Client)
            .filter(Client.firm_id == firm["id"], Client.name == cleaned)
            .first()
        )
        if existing is not None:
            raise ValueError("A client with that name already exists.")

        row = Client(firm_id=firm["id"], name=cleaned, gstin=gstin_value)
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"id": row.id, "name": row.name, "gstin": row.gstin}
    finally:
        session.close()


def delete_client(client_id: int) -> None:
    session = get_session()
    try:
        client = session.get(Client, client_id)
        if client is None:
            raise ValueError("Client was not found.")
        name = client.name
        cid = client.id
        period_ids = [
            row.id
            for row in session.query(Period).filter(Period.client_id == cid).all()
        ]
        for period_id in period_ids:
            session.query(ExtractedRow).filter(ExtractedRow.period_id == period_id).delete()
            session.query(DataPack).filter(DataPack.period_id == period_id).delete()
            session.query(StoredFile).filter(StoredFile.period_id == period_id).delete()
            session.query(Job).filter(Job.period_id == period_id).delete()
        session.query(Period).filter(Period.client_id == cid).delete()
        session.delete(client)
        session.commit()
    finally:
        session.close()

    disk = get_library_path() / "files" / str(cid)
    if disk.exists():
        shutil.rmtree(disk, ignore_errors=True)
    root = get_output_root()
    if root is not None:
        dest = root / safe_folder_name(name)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
