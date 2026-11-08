from __future__ import annotations

import json
import re
import shutil

from apps.engine.db import Client, DataPack, ExtractedRow, Job, Period, StoredFile, get_session
from apps.engine.firm import get_firm, save_firm
from apps.engine.library import get_library_path
from apps.engine.profiles import EXTRA_FIELDS, normalize_profile, resolve_profile
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


def _stored_profile(row: Client) -> dict:
    extras: dict = {}
    try:
        parsed = json.loads(row.profile_json or "{}")
    except json.JSONDecodeError:
        parsed = {}
    if isinstance(parsed, dict):
        extras = parsed
    return {
        "profession_key": row.profession_key or "",
        "profession_label": row.profession_label or "",
        "entity_type": row.entity_type or "",
        "gst_registered": None if row.gst_registered is None else bool(row.gst_registered),
        "books": extras.get("books") or "",
        "banks": extras.get("banks") or [],
        "broker": extras.get("broker") or "",
        "notes": extras.get("notes") or "",
    }


def client_to_dict(row: Client) -> dict:
    profile = _stored_profile(row)
    resolved = resolve_profile({**profile, "gstin": row.gstin})
    return {
        "id": row.id,
        "name": row.name,
        "gstin": row.gstin,
        "profile": profile,
        "profile_summary": resolved["summary"],
        "profile_is_set": resolved["is_set"],
    }


def _apply_profile(row: Client, profile: dict | None) -> dict:
    normalized = normalize_profile(profile)
    row.profession_key = normalized["profession_key"] or None
    row.profession_label = normalized["profession_label"] or None
    row.entity_type = normalized["entity_type"] or None
    row.gst_registered = (
        None if normalized["gst_registered"] is None else int(normalized["gst_registered"])
    )
    extras = {
        name: normalized[name]
        for name in EXTRA_FIELDS
        if normalized[name] not in (None, "", [])
    }
    row.profile_json = json.dumps(extras)
    return normalized


def get_client(client_id: int) -> dict | None:
    session = get_session()
    try:
        row = session.get(Client, client_id)
        if row is None:
            return None
        return client_to_dict(row)
    finally:
        session.close()


def list_clients() -> list[dict]:
    session = get_session()
    try:
        rows = session.query(Client).order_by(Client.name.asc()).all()
        return [client_to_dict(row) for row in rows]
    finally:
        session.close()


def create_client(name: str, gstin: str | None = None, profile: dict | None = None) -> dict:
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
        _apply_profile(row, profile)
        session.add(row)
        session.commit()
        session.refresh(row)
        return client_to_dict(row)
    finally:
        session.close()


def update_client_profile(client_id: int, profile: dict | None) -> dict:
    session = get_session()
    try:
        row = session.get(Client, client_id)
        if row is None:
            raise ValueError("Client was not found.")
        _apply_profile(row, profile)
        session.commit()
        session.refresh(row)
        return client_to_dict(row)
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
