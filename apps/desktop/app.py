from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import webview

from apps.engine.clients import create_client, get_client, list_clients
from apps.engine.db import get_engine
from apps.engine.dump import (
    fail_job,
    get_job,
    ingest_paths,
    list_period_files,
    override_kind,
    reparse_period,
    start_job,
)
from apps.engine.firm import get_firm, save_firm
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.engine.library import get_library_path, init_library
from apps.engine.settings import (
    get_output_root,
    is_guide_dismissed,
    set_guide_dismissed,
    set_output_root,
)
from apps.engine.periods import create_period, get_period, list_periods, suggested_period_label
from apps.engine.pdf_passwords import set_file_password as store_file_password
from apps.engine.pipeline import (
    get_period_pack,
    get_period_preview,
    get_source_crop as crop_source,
    open_pack_folder,
    open_pack_path,
)
from apps.engine.wipe import wipe_all

_WINDOW: webview.Window | None = None


def _dialog_open():
    return getattr(webview, "FileDialog", None).OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG


def _dialog_folder():
    return getattr(webview, "FileDialog", None).FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG


class DesktopApi:
    def __init__(self) -> None:
        self._current_period_id: int | None = None

    def get_state(self) -> dict:
        init_library()
        output = get_output_root()
        return {
            "firm": get_firm(),
            "clients": list_clients(),
            "library_path": str(get_library_path()),
            "output_path": str(output) if output else "",
            "guide_dismissed": is_guide_dismissed(),
        }

    def save_firm(self, name: str) -> dict:
        try:
            firm = save_firm(name)
            return {"ok": True, "firm": firm, "clients": list_clients()}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def set_guide_dismissed(self, dismissed: bool = True) -> dict:
        set_guide_dismissed(bool(dismissed))
        return {"ok": True, "guide_dismissed": is_guide_dismissed()}

    def create_client(self, name: str, gstin: str = "") -> dict:
        try:
            client = create_client(name, gstin)
            return {"ok": True, "client": client, "clients": list_clients()}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def get_client_desk(self, client_id: int) -> dict:
        client = get_client(int(client_id))
        if client is None:
            return {"ok": False, "error": "Client was not found."}
        return {
            "ok": True,
            "client": client,
            "periods": list_periods(client["id"]),
            "suggested_period": suggested_period_label(),
        }

    def create_period(self, client_id: int, label: str) -> dict:
        try:
            period = create_period(int(client_id), label)
            return {
                "ok": True,
                "period": period,
                "periods": list_periods(int(client_id)),
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def get_period_desk(self, period_id: int) -> dict:
        period = get_period(int(period_id))
        if period is None:
            return {"ok": False, "error": "Period was not found."}
        self._current_period_id = period["id"]
        client = get_client(period["client_id"])
        return {
            "ok": True,
            "client": client,
            "period": period,
            "files": list_period_files(period["id"]),
            "kinds": [{"id": key, "label": KIND_LABELS[key]} for key in KINDS],
            "pack": get_period_pack(period["id"]),
            "preview": get_period_preview(period["id"], 10),
        }

    def pick_files(self) -> dict:
        if _WINDOW is None:
            return {"ok": False, "paths": [], "error": "Window is not ready."}
        try:
            picked = _WINDOW.create_file_dialog(
                _dialog_open(),
                allow_multiple=True,
                file_types=(
                    "Client documents (*.pdf;*.json;*.xml;*.zip;*.txt;*.csv;*.xlsx;*.jpg;*.jpeg;*.png)",
                    "All files (*.*)",
                ),
            )
        except Exception as exc:
            return {"ok": False, "paths": [], "error": str(exc)}
        return {"ok": True, "paths": list(picked or [])}

    def pick_output_folder(self) -> dict:
        if _WINDOW is None:
            return {"ok": False, "error": "Window is not ready."}
        try:
            picked = _WINDOW.create_file_dialog(_dialog_folder())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not picked:
            return {"ok": False, "error": "No folder was chosen."}
        try:
            path = set_output_root(picked[0])
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "output_path": str(path)}

    def set_output_folder(self, path: str) -> dict:
        try:
            dest = set_output_root(path)
            return {"ok": True, "output_path": str(dest)}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def pick_folder(self) -> dict:
        if _WINDOW is None:
            return {"ok": False, "paths": [], "error": "Window is not ready."}
        try:
            picked = _WINDOW.create_file_dialog(_dialog_folder())
        except Exception as exc:
            return {"ok": False, "paths": [], "error": str(exc)}
        return {"ok": True, "paths": list(picked or [])}

    def start_dump(self, period_id: int, paths: list[str]) -> dict:
        if not paths:
            return {"ok": False, "error": "No files were chosen."}
        try:
            job = start_job(int(period_id))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        _run_job_thread(job["id"], lambda: ingest_paths(job["id"], list(paths)))
        return {"ok": True, "job_id": job["id"]}

    def get_job(self, job_id: int) -> dict:
        job = get_job(int(job_id))
        if job is None:
            return {"ok": False, "error": "Job was not found."}
        return {"ok": True, "job": job}

    def override_kind(self, file_id: int, kind: str) -> dict:
        try:
            row = override_kind(int(file_id), kind)
            return {"ok": True, "file": row}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def reparse_period(self, period_id: int) -> dict:
        try:
            job = start_job(int(period_id))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        _run_job_thread(job["id"], lambda: reparse_period(int(period_id), job["id"]))
        return {"ok": True, "job_id": job["id"]}

    def open_bank_pack(self, period_id: int, key: str = "") -> dict:
        try:
            path = open_pack_path(int(period_id), key or None)
            _open_path(path)
            return {"ok": True, "path": path}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except OSError as exc:
            return {"ok": False, "error": f"Could not open Excel. {exc}"}

    def open_pack_folder(self, period_id: int) -> dict:
        try:
            path = open_pack_folder(int(period_id))
            _open_path(path)
            return {"ok": True, "path": path}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def set_file_password(self, file_id: int, password: str) -> dict:
        if not str(password or "").strip():
            return {"ok": False, "error": "Enter the PDF password."}
        store_file_password(int(file_id), str(password))
        return {"ok": True}

    def get_source_crop(self, file_id: int, page: int, bbox: str = "") -> dict:
        return crop_source(int(file_id), int(page), bbox or None)

    def tesseract_status(self) -> dict:
        try:
            from apps.engine.ocr import tesseract_status

            return {"ok": True, **tesseract_status()}
        except Exception:
            return {"ok": True, "found": False, "path": None, "note": "OCR module not loaded"}

    def wipe_and_restart(self) -> dict:
        try:
            wipe_all()
        except OSError as exc:
            return {"ok": False, "error": f"Could not delete the library folder. {exc}"}
        _spawn_fresh_app()
        if _WINDOW is not None:
            _WINDOW.destroy()
        return {"ok": True}


def _open_path(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _spawn_fresh_app() -> None:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", "start", "", str(exe)], cwd=str(exe.parent))
            return
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
        return
    root = _repo_root()
    if sys.platform == "win32":
        subprocess.Popen(
            ["cmd", "/c", "start", "", sys.executable, "-m", "apps.desktop"],
            cwd=str(root),
        )
        return
    subprocess.Popen([sys.executable, "-m", "apps.desktop"], cwd=str(root))


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def ui_index() -> str:
    return (_bundle_root() / "ui" / "index.html").as_uri()


def app_icon_path() -> str | None:
    path = _bundle_root() / "ui" / "app-icon.ico"
    return str(path) if path.is_file() else None


def _log_crash(message: str) -> None:
    log_path = get_library_path() / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(message, encoding="utf-8")


def _run_job_thread(job_id: int, fn) -> None:
    def work() -> None:
        try:
            fn()
        except Exception:
            import traceback

            _log_crash(traceback.format_exc())
            leftover = get_job(job_id)
            if leftover is None or leftover.get("status") in {"queued", "routing", "parsing"}:
                fail_job(job_id, "Could not process these files.")

    threading.Thread(target=work, daemon=True).start()


def _drop_paths(event) -> list[str]:
    files = (event or {}).get("dataTransfer", {}).get("files") or []
    paths: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("pywebviewFullPath") or item.get("path")
        if path:
            paths.append(path)
    return paths


def _bind_explorer_drop(api: DesktopApi) -> None:
    if _WINDOW is None:
        return
    try:
        from webview.dom import DOMEventHandler
    except Exception:
        return

    def on_zone_drop(_event) -> None:
        # Bind so WebView2 injects pywebviewFullPath into the JS File list.
        # JS startDump owns the job so the tray can poll.
        return None

    def _prevent(_event) -> None:
        return None

    try:
        zone = _WINDOW.dom.get_element("#drop-zone")
        if zone is not None:
            zone.events.drop += DOMEventHandler(on_zone_drop, True, True)
    except Exception:
        pass
    try:
        document = _WINDOW.dom.document
        document.events.dragover += DOMEventHandler(_prevent, True, False)
        document.events.drop += DOMEventHandler(_prevent, True, False)
    except Exception:
        pass


def main() -> None:
    import traceback

    try:
        init_library()
        get_engine()
        global _WINDOW
        api = DesktopApi()
        _WINDOW = webview.create_window(
            "CA Unpacker",
            ui_index(),
            js_api=api,
            width=1120,
            height=760,
            min_size=(880, 580),
            background_color="#2C3330",
        )
        _WINDOW.events.shown += lambda: _bind_explorer_drop(api)
        webview.start(icon=app_icon_path())
    except Exception:
        _log_crash(traceback.format_exc())
        raise
