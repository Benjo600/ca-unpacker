from __future__ import annotations

import json
import re
from pathlib import Path

from apps.engine.library import get_library_path, init_library


def settings_path() -> Path:
    return get_library_path() / "settings.json"


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: dict) -> dict:
    init_library()
    path = settings_path()
    current = load_settings()
    current.update(data)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def get_output_root() -> Path | None:
    raw = (load_settings().get("output_root") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def is_guide_dismissed() -> bool:
    return bool(load_settings().get("guide_dismissed"))


def set_guide_dismissed(dismissed: bool = True) -> None:
    save_settings({"guide_dismissed": bool(dismissed)})


def path_sync_warnings(*raw_paths: str) -> list[str]:
    """Warn when a library or output folder sits on OneDrive or Desktop sync."""
    notes: list[str] = []
    for raw in raw_paths:
        text = str(raw or "").strip()
        if not text:
            continue
        lowered = text.replace("/", "\\").lower()
        if "onedrive" in lowered and not any("onedrive" in n.lower() for n in notes):
            notes.append(
                "This folder is in OneDrive. Packs can sync or clash if two PCs write at once. "
                "Prefer a local folder, or keep only one writer."
            )
        desktopish = "\\desktop\\" in lowered or lowered.endswith("\\desktop")
        if desktopish and not any("desktop" in n.lower() for n in notes):
            notes.append(
                "Desktop is often OneDrive-backed. A local Documents folder is safer for this firm."
            )
    return notes


def set_output_root(raw: str) -> Path:
    path = Path((raw or "").strip())
    if not str(path):
        raise ValueError("Choose a folder for the cleaned Excels.")
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".ca_unpacker_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise ValueError(f"That folder cannot be written to. {exc}") from exc
    save_settings({"output_root": str(path)})
    return path


def safe_folder_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\\\|?*]+', " ", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "Untitled")[:80]


def period_output_dir(client_name: str, period_label: str) -> Path:
    root = get_output_root()
    if root is None:
        root = get_library_path() / "packs"
    dest = root / safe_folder_name(client_name) / safe_folder_name(period_label)
    dest.mkdir(parents=True, exist_ok=True)
    return dest
