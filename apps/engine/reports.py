from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apps.engine.db import Client, DataPack, Period, get_session


def _read_summary(path_text: str | None) -> dict:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def list_reports() -> dict:
    session = get_session()
    try:
        records = (
            session.query(DataPack, Period, Client)
            .join(Period, DataPack.period_id == Period.id)
            .join(Client, Period.client_id == Client.id)
            .order_by(DataPack.created_at.desc(), DataPack.id.desc())
            .all()
        )
        seen_periods: set[int] = set()
        packs = []
        for pack, period, client in records:
            if period.id in seen_periods:
                continue
            seen_periods.add(period.id)
            summary = _read_summary(pack.bank_xlsx_key)
            outputs = summary.get("outputs") or []
            if not outputs:
                continue
            packs.append(
                {
                    "pack_id": pack.id,
                    "period_id": period.id,
                    "period_label": period.label,
                    "client_name": client.name,
                    "folder": summary.get("folder") or "",
                    "row_count": int(pack.row_count or 0),
                    "created_at": pack.created_at.isoformat()
                    if pack.created_at
                    else None,
                    "outputs": [
                        {
                            "key": item.get("key") or "",
                            "label": item.get("label") or "",
                            "path": item.get("path") or "",
                            "rows": int(item.get("rows") or 0),
                            "status": item.get("status") or "",
                        }
                        for item in outputs
                    ],
                }
            )
    finally:
        session.close()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "packs": packs,
    }
