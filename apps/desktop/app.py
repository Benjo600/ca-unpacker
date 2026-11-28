from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import webview
from sqlalchemy import func

from apps.desktop import updater
from apps.engine import updates
from apps.engine.clients import (
    create_client,
    delete_client,
    get_client,
    list_clients,
    set_client_tolerances,
    update_client_profile,
)
from apps.engine.currency import currency_options
from apps.engine.dashboard import get_dashboard as dashboard_state
from apps.engine.db import ExtractedRow, Period, StoredFile, get_engine, get_session
from apps.engine.firm import get_firm, save_firm
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.desktop.protocol import ensure_registered, is_registered
from apps.engine import auth
from apps.engine.auth_config import CA_UNPACKER_AUTH_URL
from apps.engine.license import activate_key, assert_can_ingest, get_license_status
from apps.engine.library import (
    get_library_path,
    init_library,
    resolve_storage_key,
)
from apps.engine.recon_datasets import reconciliation_workspace
from apps.engine.recon_service import (
    accept_match as recon_accept_match,
    add_exception_note as recon_add_exception_note,
    add_match_note as recon_add_match_note,
    cancel_run as recon_cancel_run,
    compare_runs as recon_compare_runs,
    control_centre as recon_control_centre,
    get_exception_detail as recon_exception_detail,
    get_exceptions as recon_exceptions,
    get_match_detail as recon_match_detail,
    get_run as recon_get_run,
    get_run_rows as recon_run_rows,
    list_rule_sets as recon_rule_sets,
    list_runs as recon_list_runs,
    manual_match as recon_manual_match,
    recon_filter_options as recon_filter_options_service,
    reject_match as recon_reject_match,
    rerun as recon_rerun,
    run_audit as recon_run_audit,
    save_rule_set as recon_save_rule_set,
    start_reconciliation as recon_start,
    unmatch as recon_unmatch,
    update_exception as recon_update_exception,
)
from apps.engine.recon_workflows import (
    run_reconciliation as run_recon_workflow,
)
from apps.engine.reports import list_reports as report_packs
from apps.engine import decisions
from apps.engine.settings import (
    get_output_root,
    get_snapshot_retention_days,
    get_ui_location,
    is_guide_dismissed,
    path_sync_warnings,
    save_ui_location,
    set_guide_dismissed,
    set_output_root,
    set_snapshot_retention_days,
)
from apps.engine.periods import (
    create_period,
    delete_period,
    get_period,
    list_periods,
    set_period_tolerances,
    suggested_period_label,
)
from apps.engine.pdf_passwords import (
    get_file_password,
    set_file_password as store_file_password,
)
from apps.engine.profiles import profile_options
from apps.engine.preview import preview_file as build_preview, source_file_path
from apps.engine.wipe import wipe_all
from apps.version import APP_VERSION

if TYPE_CHECKING:  # annotations only; the dataclass stays behind its function
    from apps.engine.dump import IntakePreflight

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deferred engine entry points
#
# Creating the window and answering the first ``get_state`` need the database
# and nothing else. Everything below reaches the parse pipeline, an Excel
# writer or the reconciliation exporters — and behind them openpyxl, numpy and a
# PDF engine, which together cost about five seconds of import time on a cold
# machine. A CA who has not dropped a file yet should not pay for any of it.
#
# The names stay in this module (rather than being imported inside each method)
# because the window's tests and the update gate use them as seams: patching
# ``apps.desktop.app.start_job`` must still stop the work from starting.
# ---------------------------------------------------------------------------


def fail_job(job_id: int, message: str) -> None:
    from apps.engine.dump import fail_job as run

    run(job_id, message)


def get_job(job_id: int) -> dict | None:
    from apps.engine.dump import get_job as read

    return read(job_id)


def ingest_paths(job_id: int, paths: list[str]) -> dict:
    from apps.engine.dump import ingest_paths as run

    return run(job_id, paths)


def list_period_files(period_id: int) -> list[dict]:
    from apps.engine.dump import list_period_files as read

    return read(period_id)


def override_kind(file_id: int, kind: str) -> dict:
    from apps.engine.dump import override_kind as run

    return run(file_id, kind)


def preflight_paths(raw_paths: list[str]) -> IntakePreflight:
    from apps.engine.dump import preflight_paths as run

    return run(raw_paths)


def reconcile_interrupted_work(grace_minutes: int = 0) -> int:
    from apps.engine.dump import reconcile_interrupted_work as run

    return run(grace_minutes)


def reparse_period(period_id: int, job_id: int | None = None) -> dict:
    from apps.engine.dump import reparse_period as run

    return run(period_id, job_id)


def set_file_currency(file_id: int, code: str | None) -> dict:
    from apps.engine.dump import set_file_currency as run

    return run(file_id, code)


def start_job(period_id: int) -> dict:
    from apps.engine.dump import start_job as run

    return run(period_id)


def get_period_pack(period_id: int) -> dict | None:
    from apps.engine.pipeline import get_period_pack as read

    return read(period_id)


def get_period_preview(period_id: int, limit: int = 8) -> dict:
    from apps.engine.pipeline import get_period_preview as read

    return read(period_id, limit)


def get_source_crop(file_id: int, page: int, bbox: str | None) -> dict:
    from apps.engine.pipeline import get_source_crop as read

    return read(file_id, page, bbox)


def list_pack_versions(period_id: int) -> list[dict]:
    from apps.engine.pipeline import list_pack_versions as read

    return read(period_id)


def open_pack_folder(period_id: int) -> str:
    from apps.engine.pipeline import open_pack_folder as run

    return run(period_id)


def open_pack_path(period_id: int, key: str | None = None) -> str:
    from apps.engine.pipeline import open_pack_path as run

    return run(period_id, key)


def restore_pack_version(period_id: int, snapshot_id: str) -> dict:
    from apps.engine.pipeline import restore_pack_version as run

    return run(period_id, snapshot_id)


def remove_period_file(file_id: int) -> dict:
    from apps.engine.removal import remove_period_file as run

    return run(file_id)


def export_reconciliation(run_id: int) -> dict:
    from apps.engine.recon_report import export_reconciliation as run

    return run(run_id)


def write_exceptions_workbook(
    path: Path,
    *,
    client_name: str,
    period_label: str,
    recon: dict,
    firm: str = "",
) -> Path:
    from apps.engine.recon_exports import write_exceptions_workbook as run

    return run(
        path,
        client_name=client_name,
        period_label=period_label,
        recon=recon,
        firm=firm,
    )


def write_audit_summary(
    path: Path,
    *,
    client_name: str,
    period_label: str,
    recon: dict,
    firm: str = "",
) -> Path:
    from apps.engine.recon_exports import write_audit_summary as run

    return run(
        path,
        client_name=client_name,
        period_label=period_label,
        recon=recon,
        firm=firm,
    )


_WINDOW: webview.Window | None = None
_PENDING_AUTH_CALLBACK_FILE = "pending_auth_callback.url"
_SINGLE_INSTANCE_MUTEX_NAME = "Global\\CAUnpackerSingleInstance"
_startup_deep_link: str | None = None
_mutex_handle: int | None = None

# Bumped every time the library is wiped in place. Background job threads
# capture the epoch when they start; if it changed underneath them, their
# output belongs to a deleted library and gets wiped again (see
# _run_job_thread), so a reset always ends with an empty library.
_wipe_epoch = 0
_job_threads: set[threading.Thread] = set()
_job_threads_lock = threading.Lock()

_UPDATE_HELPER_NAME = "CAUnpackerUpdater.exe"
_UPDATE_MANIFEST_FIELDS = (
    "version",
    "title",
    "release_notes",
    "installer_url",
    "installer_sha256",
    "installer_size",
    "mandatory",
    "published_at",
    "minimum_supported_version",
)

_CHECK_FAILED_MESSAGE = (
    "Could not check for updates. Check your internet connection and try again."
)
_DOWNLOAD_FAILED_MESSAGE = (
    "Could not download the update. Check your internet connection and try again."
)
_CANCELLED_NOTE = "Update download cancelled."
_NOTHING_TO_DOWNLOAD = "There is no update ready to download."
_NO_DOWNLOAD_RUNNING = "No update download is running."
_NOT_DOWNLOADED = "The update has not been downloaded yet."
_UPDATE_BUSY = "An update task is already running. Wait for it to finish."
_DEV_MODE_MESSAGE = (
    "Updates install only in the packaged CA Unpacker app, not in a development copy."
)
_HELPER_MISSING = (
    "The update helper is missing from this installation. Reinstall CA Unpacker."
)
_DAMAGED_INSTALLER = "The downloaded update is damaged. Download it again."
_LAUNCH_FAILED = "Could not start the update helper. CA Unpacker is still open."
_UPDATE_READ_FAILED = "Could not read the update status."


class UpdateRefused(Exception):
    """A user-facing refusal that leaves the stored update state unchanged."""


def _copy_update_state(state: updates.UpdateState) -> updates.UpdateState:
    return updates.UpdateState(
        status=state.status,
        version=state.version,
        title=state.title,
        notes=state.notes,
        mandatory=bool(state.mandatory),
        progress=float(state.progress),
        error=state.error,
        downloaded_path=state.downloaded_path,
        installer_sha256=state.installer_sha256,
        installer_size=int(state.installer_size),
    )


def _update_payload(state: updates.UpdateState) -> dict:
    """The only update shape the web view ever sees: no paths, tokens or cache."""

    return {
        "status": state.status,
        "version": state.version,
        "title": state.title,
        "notes": state.notes,
        "mandatory": bool(state.mandatory),
        "progress": float(state.progress),
        "error": state.error,
        "available": bool(state.available),
    }


def _manifest_from_cache(cache: dict) -> updates.ReleaseManifest | None:
    entry = cache.get("manifest") if isinstance(cache, dict) else None
    if not isinstance(entry, dict):
        return None
    values = {key: entry[key] for key in _UPDATE_MANIFEST_FIELDS if key in entry}
    try:
        return updates.ReleaseManifest(**values)
    except TypeError:
        return None


class UpdateController:
    """One process-wide update state machine driven by a single worker thread.

    Every state change happens under ``self._lock``; long work (network check,
    download, helper launch) runs outside it. Repeated calls while a worker is
    busy return the current state instead of starting a second worker.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = updates.UpdateState()
        self._manifest: updates.ReleaseManifest | None = None
        self._installer: Path | None = None
        self._worker: threading.Thread | None = None
        self._cancel: threading.Event | None = None
        self._busy = False

    # -- reading ---------------------------------------------------------

    def snapshot(self) -> updates.UpdateState:
        with self._lock:
            return _copy_update_state(self._state)

    def wait_idle(self, timeout: float = 10.0) -> bool:
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout)
        with self._lock:
            return not self._busy

    # -- checking --------------------------------------------------------

    def check(self, force: bool = False) -> updates.UpdateState:
        with self._lock:
            if self._busy:
                return _copy_update_state(self._state)
            previous = self._state
            self._state = updates.UpdateState(
                status="checking",
                version=previous.version,
                title=previous.title,
                notes=previous.notes,
                mandatory=bool(previous.mandatory),
            )
            self._busy = True
            self._worker = threading.Thread(
                target=self._run_check,
                args=(bool(force),),
                name="update-check",
                daemon=True,
            )
            self._worker.start()
            return _copy_update_state(self._state)

    def _run_check(self, force: bool) -> None:
        try:
            state = updates.check_for_update(force=force)
            manifest = None
            if state.status == "available":
                manifest = _manifest_from_cache(updates.load_update_cache())
        except ValueError as exc:
            state = updates.UpdateState(status="error", error=str(exc))
            manifest = None
        except Exception:
            state = updates.UpdateState(status="error", error=_CHECK_FAILED_MESSAGE)
            manifest = None
        with self._lock:
            self._state = _copy_update_state(state)
            self._manifest = manifest
            self._installer = None
            self._cancel = None
            self._busy = False

    # -- downloading -----------------------------------------------------

    def download(self) -> updates.UpdateState:
        with self._lock:
            if self._busy:
                return _copy_update_state(self._state)
            if self._state.status != "available" or self._manifest is None:
                raise UpdateRefused(_NOTHING_TO_DOWNLOAD)
            self._busy = True
            self._cancel = threading.Event()
            self._state = _copy_update_state(self._state)
            self._state.status = "downloading"
            self._state.progress = 0.0
            self._state.error = ""
            self._state.downloaded_path = None
            manifest = self._manifest
            cancel = self._cancel
            self._worker = threading.Thread(
                target=self._run_download,
                args=(manifest, cancel),
                name="update-download",
                daemon=True,
            )
            self._worker.start()
            return _copy_update_state(self._state)

    def _report_progress(self, fraction: float) -> None:
        try:
            value = max(0.0, min(1.0, float(fraction)))
        except (TypeError, ValueError):
            return
        with self._lock:
            if self._state.status == "downloading":
                self._state.progress = value

    def _run_download(
        self, manifest: updates.ReleaseManifest, cancel: threading.Event
    ) -> None:
        try:
            path = updates.download_update(
                manifest,
                progress_callback=self._report_progress,
                cancel_event=cancel,
            )
        except updates.UpdateCancelled:
            with self._lock:
                self._state = updates.UpdateState(
                    status="available",
                    version=manifest.version,
                    title=manifest.title,
                    notes=manifest.release_notes,
                    mandatory=bool(self._state.mandatory),
                    error=_CANCELLED_NOTE,
                    installer_sha256=manifest.installer_sha256,
                    installer_size=manifest.installer_size,
                )
                self._installer = None
        except ValueError as exc:
            with self._lock:
                self._state = updates.UpdateState(status="error", error=str(exc))
                self._installer = None
        except Exception:
            with self._lock:
                self._state = updates.UpdateState(
                    status="error", error=_DOWNLOAD_FAILED_MESSAGE
                )
                self._installer = None
        else:
            with self._lock:
                self._state = updates.UpdateState(
                    status="ready",
                    version=manifest.version,
                    title=manifest.title,
                    notes=manifest.release_notes,
                    mandatory=bool(self._state.mandatory),
                    progress=1.0,
                    installer_sha256=manifest.installer_sha256,
                    installer_size=manifest.installer_size,
                )
                self._installer = Path(path)
        finally:
            with self._lock:
                self._cancel = None
                self._busy = False

    def cancel_download(self) -> updates.UpdateState:
        with self._lock:
            if self._state.status != "downloading" or self._cancel is None:
                raise UpdateRefused(_NO_DOWNLOAD_RUNNING)
            self._cancel.set()
            return _copy_update_state(self._state)

    # -- installing ------------------------------------------------------

    def install(self, window=None) -> updates.UpdateState:
        with self._lock:
            if self._busy:
                raise UpdateRefused(_UPDATE_BUSY)
            state = _copy_update_state(self._state)
            manifest = self._manifest
            installer = self._installer
            if state.status != "ready" or manifest is None or installer is None:
                raise UpdateRefused(_NOT_DOWNLOADED)
            self._busy = True
        try:
            return self._run_install(manifest, installer, window)
        finally:
            with self._lock:
                self._busy = False

    def _run_install(
        self,
        manifest: updates.ReleaseManifest,
        installer: Path,
        window,
    ) -> updates.UpdateState:
        if not getattr(sys, "frozen", False):
            raise UpdateRefused(_DEV_MODE_MESSAGE)

        try:
            updater.verify_installer(
                installer, manifest.installer_size, manifest.installer_sha256
            )
        except (updater.UpdaterError, OSError):
            with self._lock:
                self._state = updates.UpdateState(
                    status="available",
                    version=manifest.version,
                    title=manifest.title,
                    notes=manifest.release_notes,
                    mandatory=bool(self._state.mandatory),
                    error=_DAMAGED_INSTALLER,
                    installer_sha256=manifest.installer_sha256,
                    installer_size=manifest.installer_size,
                )
                self._installer = None
            raise UpdateRefused(_DAMAGED_INSTALLER)

        helper_source = Path(sys.executable).resolve().parent / _UPDATE_HELPER_NAME
        if not helper_source.is_file():
            raise UpdateRefused(_HELPER_MISSING)
        helper_target = installer.parent / _UPDATE_HELPER_NAME
        try:
            shutil.copyfile(helper_source, helper_target)
        except OSError:
            raise UpdateRefused(_HELPER_MISSING)

        command = [
            str(helper_target),
            "--installer",
            str(installer),
            "--parent-pid",
            str(os.getpid()),
            "--app-exe",
            str(Path(sys.executable)),
            "--expected-version",
            manifest.version,
            "--expected-size",
            str(manifest.installer_size),
            "--expected-sha256",
            manifest.installer_sha256,
        ]
        try:
            process = subprocess.Popen(command, cwd=str(helper_target.parent))
        except OSError:
            raise UpdateRefused(_LAUNCH_FAILED)
        if process is None:
            raise UpdateRefused(_LAUNCH_FAILED)

        with self._lock:
            self._state = updates.UpdateState(
                status="installing",
                version=manifest.version,
                title=manifest.title,
                notes=manifest.release_notes,
                mandatory=bool(self._state.mandatory),
                progress=1.0,
                installer_sha256=manifest.installer_sha256,
                installer_size=manifest.installer_size,
            )
            result = _copy_update_state(self._state)

        # Only close the app once the helper is really running.
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass
        return result


_UPDATE_CONTROLLER: UpdateController | None = None
_UPDATE_CONTROLLER_LOCK = threading.Lock()


def update_controller() -> UpdateController:
    global _UPDATE_CONTROLLER
    if _UPDATE_CONTROLLER is None:
        with _UPDATE_CONTROLLER_LOCK:
            if _UPDATE_CONTROLLER is None:
                _UPDATE_CONTROLLER = UpdateController()
    return _UPDATE_CONTROLLER


def _update_response(state: updates.UpdateState) -> dict:
    payload = _update_payload(state)
    if state.status == "error" and state.error:
        return {"ok": False, "error": state.error, "update": payload}
    return {"ok": True, "update": payload}


def _update_refusal_response(message: str, state: updates.UpdateState) -> dict:
    return {"ok": False, "error": message, "update": _update_payload(state)}


def _schedule_startup_update_check() -> None:
    """One silent, non-blocking check once the window exists and the user is in."""

    def work() -> None:
        try:
            if not auth.get_auth_state().get("signed_in"):
                return
            update_controller().check()
        except Exception as exc:
            # Silent by design (nobody asked for this check), but an update
            # path that never runs must still leave a trace in the log.
            _log.warning("Startup update check failed: %s", exc)

    try:
        threading.Thread(
            target=work, name="update-startup-check", daemon=True
        ).start()
    except Exception as exc:
        _log.warning("Could not start the startup update check: %s", exc)


def extract_deep_link_url(argv: list[str] | None = None) -> str | None:
    args = argv if argv is not None else sys.argv
    for arg in args[1:]:
        text = str(arg)
        if text.startswith("caunpacker://"):
            return text
    return None


def _dialog_open():
    return getattr(webview, "FileDialog", None).OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG


def _dialog_folder():
    return getattr(webview, "FileDialog", None).FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG


_MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _period_month_sort_key(period: Period) -> tuple:
    """Order months by the month they name, not by when the row was created."""
    parts = str(period.label or "").replace(",", " ").split()
    month = _MONTH_NUMBERS.get(parts[0][:3].lower()) if len(parts) == 2 else None
    year = parts[1] if len(parts) == 2 else ""
    try:
        stamp = period.created_at.timestamp() if period.created_at else 0.0
    except (AttributeError, OSError, ValueError):
        stamp = 0.0
    if month and year.isdigit() and len(year) == 4:
        return (1, int(year), month, stamp)
    return (0, 0, 0, stamp)


def _client_document_summary() -> dict[int, dict]:
    """Documents per client and the newest month, in two queries total.

    The client list shows a document count and a latest month for every row.
    Counting per row would be one query per client, which is what a practice
    with a hundred clients cannot afford.
    """
    session = get_session()
    try:
        counts = dict(
            session.query(Period.client_id, func.count(StoredFile.id))
            .outerjoin(StoredFile, StoredFile.period_id == Period.id)
            .group_by(Period.client_id)
            .all()
        )
        periods = session.query(Period).all()
    finally:
        session.close()

    summary: dict[int, dict] = {}
    newest: dict[int, tuple] = {}
    for period in periods:
        key = _period_month_sort_key(period)
        if period.client_id not in newest or key > newest[period.client_id]:
            newest[period.client_id] = key
            bucket = summary.setdefault(
                period.client_id, {"document_count": 0, "latest_period": ""}
            )
            bucket["latest_period"] = str(period.label or "")
    for client_id, count in counts.items():
        bucket = summary.setdefault(
            client_id, {"document_count": 0, "latest_period": ""}
        )
        bucket["document_count"] = int(count or 0)
    return summary


def _clients_payload() -> list[dict]:
    """list_clients() plus the two numbers the client table shows."""
    clients = list_clients()
    summary = _client_document_summary()
    for client in clients:
        info = summary.get(client["id"]) or {}
        client["document_count"] = int(info.get("document_count") or 0)
        client["latest_period"] = info.get("latest_period") or ""
    return clients


class DesktopApi:
    def __init__(self) -> None:
        self._current_period_id: int | None = None

    def get_auth_state(self) -> dict:
        return auth.get_auth_state()

    # -- updates ---------------------------------------------------------

    def get_update_state(self, force_check: bool = False) -> dict:
        controller = update_controller()
        try:
            if force_check:
                state = controller.check(force=True)
            else:
                state = controller.snapshot()
        except Exception:
            return {"ok": False, "error": _UPDATE_READ_FAILED}
        return _update_response(state)

    def download_update(self) -> dict:
        controller = update_controller()
        try:
            state = controller.download()
        except UpdateRefused as exc:
            return _update_refusal_response(str(exc), controller.snapshot())
        except Exception:
            return _update_refusal_response(
                _DOWNLOAD_FAILED_MESSAGE, controller.snapshot()
            )
        return _update_response(state)

    def cancel_update_download(self) -> dict:
        controller = update_controller()
        try:
            state = controller.cancel_download()
        except UpdateRefused as exc:
            return _update_refusal_response(str(exc), controller.snapshot())
        except Exception:
            return _update_refusal_response(
                _NO_DOWNLOAD_RUNNING, controller.snapshot()
            )
        return _update_response(state)

    def install_update(self) -> dict:
        controller = update_controller()
        try:
            state = controller.install(window=_WINDOW)
        except UpdateRefused as exc:
            return _update_refusal_response(str(exc), controller.snapshot())
        except Exception:
            return _update_refusal_response(_LAUNCH_FAILED, controller.snapshot())
        return _update_response(state)

    def open_signup(self) -> dict:
        # Browser signup flow removed. Use in-app signup_with_password.
        return {"ok": False, "error": "Use the in-app sign up form."}

    def open_login(self) -> dict:
        # Browser login flow removed. Use in-app login_with_password.
        return {"ok": False, "error": "Use the in-app login form."}

    def check_protocol_registered(self) -> dict:
        """Check if the caunpacker:// protocol is registered for browser handoff."""
        try:
            registered = is_registered()
        except Exception:
            registered = False
        return {"ok": True, "registered": registered}

    def login_with_password(self, email: str, password: str) -> dict:
        address = str(email or "").strip()
        secret = str(password or "")
        if not address:
            return {"ok": False, "error": "Enter your email address."}
        if not secret:
            return {"ok": False, "error": "Enter your password."}
        try:
            auth.sign_in_with_password(address, secret)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not reach the sign-in service. Try again."}
        try:
            auth.fetch_quota()
        except Exception:
            pass
        return {"ok": True, **auth.get_auth_state()}

    def signup_with_password(self, email: str, password: str) -> dict:
        address = str(email or "").strip()
        secret = str(password or "")
        if not address:
            return {"ok": False, "error": "Enter your email address."}
        if not secret:
            return {"ok": False, "error": "Choose a password."}
        try:
            created = auth.sign_up_with_password(address, secret)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not reach the sign-up service. Try again."}
        if isinstance(created, dict) and created.get("confirmation_required"):
            return {
                "ok": True,
                "confirmation_required": True,
                "signed_in": False,
                "email": created.get("email") or address,
            }
        try:
            auth.fetch_quota()
        except Exception:
            pass
        return {"ok": True, "confirmation_required": False, **auth.get_auth_state()}

    def request_password_reset(self, email: str) -> dict:
        address = str(email or "").strip()
        if not address:
            return {"ok": False, "error": "Enter your email address first."}
        try:
            auth.send_password_reset(address)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not send the reset email. Try again."}
        return {"ok": True}

    def open_account(self) -> dict:
        webbrowser.open(f"{CA_UNPACKER_AUTH_URL}/app")
        return {"ok": True}

    def logout(self) -> dict:
        auth.logout()
        return {"ok": True, **auth.get_auth_state()}

    def handle_auth_callback(self, url: str) -> dict:
        parsed = urlparse(str(url or ""))
        frag_or_q = (parsed.fragment or parsed.query or "").lstrip("?#")
        params = parse_qs(frag_or_q)
        access = (params.get("access_token") or [None])[0]
        refresh = (params.get("refresh_token") or [None])[0]
        try:
            if access and refresh:
                auth.login_via_tokens(str(access), str(refresh))
            else:
                # tolerate callbacks without tokens (e.g. some confirmation redirects); refresh any session
                try:
                    auth.refresh_session()
                except Exception:
                    pass
            try:
                auth.fetch_quota()
                auth.send_heartbeat()
            except Exception:
                pass
            state = auth.get_auth_state()
            if not state.get("signed_in"):
                return {"ok": False, "error": "Sign-in callback did not include tokens and no active session."}
            return {"ok": True, **state}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def check_pending_auth_callback(self) -> dict:
        """Manual check for pending deep-link auth (e.g. browser signup complete button in gate)."""
        pending = _read_pending_deep_link()
        if pending:
            return _process_deep_link(self, pending)
        return {"ok": False, "error": "No pending auth callback found."}

    def drain_ui_events(self) -> list:
        """Background work waiting for the UI thread (auth refresh, errors).

        The page polls this instead of letting worker threads touch the window.
        """
        return _drain_ui_events()

    def get_state(self) -> dict:
        init_library()
        output = get_output_root()
        library = get_library_path()
        return {
            "app_version": APP_VERSION,
            "firm": get_firm(),
            "clients": _clients_payload(),
            "library_path": str(library),
            "output_path": str(output) if output else "",
            "snapshot_retention_days": get_snapshot_retention_days(),
            "guide_dismissed": is_guide_dismissed(),
            "license": get_license_status(),
            "auth": auth.get_auth_state(),
            "profile_options": profile_options(),
            "path_warnings": path_sync_warnings(
                str(library), str(output) if output else ""
            ),
            "ui_last_nav": get_ui_location(),
        }

    def get_dashboard(self) -> dict:
        try:
            return {"ok": True, **dashboard_state()}
        except Exception:
            return {"ok": False, "error": "Could not load the dashboard."}

    def get_reconciliation_workspace(self) -> dict:
        try:
            return {"ok": True, **reconciliation_workspace()}
        except Exception:
            return {
                "ok": False,
                "error": "Could not load reconciliation data.",
            }

    def run_reconciliation(self, period_id: int, workflow_id: str) -> dict:
        try:
            period_key = int(period_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Period was not found."}
        try:
            result = run_recon_workflow(period_key, str(workflow_id or ""))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {
                "ok": False,
                "error": "Could not calculate this reconciliation.",
            }
        return {"ok": True, **result}

    # ------------------------------------------------------------------
    # Reconciliation Control Centre / Workbench / Exceptions / Rules
    # ------------------------------------------------------------------

    def get_recon_workspace(self) -> dict:
        try:
            return {"ok": True, **reconciliation_workspace()}
        except Exception:
            return {"ok": False, "error": "Could not load the reconciliation workspace."}

    def get_recon_filter_options(self) -> dict:
        try:
            return {"ok": True, **recon_filter_options_service()}
        except Exception:
            return {"ok": False, "error": "Could not load reconciliation filters."}

    def get_recon_control_centre(self, filters: dict | None = None) -> dict:
        try:
            return {"ok": True, **recon_control_centre(filters or {})}
        except Exception:
            return {"ok": False, "error": "Could not load the reconciliation control centre."}

    def get_recon_rules(self, workflow_id: str = "") -> dict:
        try:
            return {"ok": True, **recon_rule_sets(str(workflow_id or "") or None)}
        except Exception:
            return {"ok": False, "error": "Could not load reconciliation rules."}

    def save_recon_rules(self, payload: dict | None = None) -> dict:
        try:
            result = recon_save_rule_set(payload or {}, self._actor())
            return {"ok": True, "ruleset": result}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not save the reconciliation rule set."}

    def start_recon_run(
        self,
        period_id: int,
        workflow_id: str,
        ruleset_id: int | None = None,
    ) -> dict:
        try:
            period_key = int(period_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Period was not found."}
        try:
            result = recon_start(
                period_key,
                str(workflow_id or ""),
                ruleset_id=int(ruleset_id) if ruleset_id not in (None, "") else None,
                actor=self._actor(),
                background=True,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not start this reconciliation."}
        if not result.get("available"):
            return {
                "ok": False,
                "available": False,
                "error": result.get("message") or "Required source data is missing.",
                **result,
            }
        return {"ok": True, **result}

    def get_recon_run(self, run_id: int) -> dict:
        try:
            return {"ok": True, **recon_get_run(int(run_id))}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not load this reconciliation run."}

    def cancel_recon_run(self, run_id: int) -> dict:
        try:
            return {"ok": True, **recon_cancel_run(int(run_id), self._actor())}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not cancel this reconciliation."}

    def get_recon_run_rows(self, run_id: int, filters: dict | None = None) -> dict:
        try:
            return {"ok": True, **recon_run_rows(int(run_id), filters or {})}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not load these reconciliation rows."}

    def get_recon_match(self, match_id: int) -> dict:
        try:
            return {"ok": True, **recon_match_detail(int(match_id))}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not load this reconciliation row."}

    def get_recon_exceptions(self, filters: dict | None = None) -> dict:
        try:
            return {"ok": True, **recon_exceptions(filters or {})}
        except Exception:
            return {"ok": False, "error": "Could not load the exception queue."}

    def get_recon_exception(self, exception_id: int) -> dict:
        try:
            return {"ok": True, **recon_exception_detail(int(exception_id))}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not load this exception."}

    def recon_decide(self, payload: dict | None = None) -> dict:
        data = payload or {}
        action = str(data.get("action") or "").strip()
        reason = str(data.get("reason") or "").strip()
        try:
            if action == "accept":
                result = recon_accept_match(int(data.get("match_id")), reason, self._actor())
            elif action == "reject":
                result = recon_reject_match(int(data.get("match_id")), reason, self._actor())
            elif action == "unmatch":
                result = recon_unmatch(int(data.get("match_id")), reason, self._actor())
            elif action == "manual_match":
                result = recon_manual_match(data, self._actor())
            else:
                return {"ok": False, "error": "That reconciliation action is not available."}
            return {"ok": True, "result": result}
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not save this reconciliation decision."}

    def recon_update_exception(self, payload: dict | None = None) -> dict:
        try:
            return {
                "ok": True,
                "exception": recon_update_exception(payload or {}, self._actor()),
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not update this exception."}

    def recon_add_note(self, payload: dict | None = None) -> dict:
        data = payload or {}
        try:
            if data.get("match_id"):
                result = recon_add_match_note(data, self._actor())
            else:
                result = recon_add_exception_note(data, self._actor())
            return {"ok": True, **result}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not save this note."}

    def list_recon_runs(self, filters: dict | None = None) -> dict:
        try:
            data = filters or {}
            return {
                "ok": True,
                **recon_list_runs(
                    data,
                    page=int(data.get("page") or 1),
                    page_size=int(data.get("page_size") or 50),
                ),
            }
        except Exception:
            return {"ok": False, "error": "Could not load reconciliation history."}

    def compare_recon_runs(self, run_a: int, run_b: int) -> dict:
        try:
            return {"ok": True, **recon_compare_runs(int(run_a), int(run_b))}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not compare these reconciliation runs."}

    def rerun_reconciliation(self, run_id: int) -> dict:
        try:
            result = recon_rerun(int(run_id), self._actor(), background=True)
            if not result.get("available"):
                return {
                    "ok": False,
                    "available": False,
                    "error": result.get("message") or "Required source data is missing.",
                    **result,
                }
            return {"ok": True, **result}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not re-run this reconciliation."}

    def get_recon_audit(self, run_id: int) -> dict:
        try:
            return {"ok": True, **recon_run_audit(int(run_id))}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not load the audit trail."}

    def export_recon_run(self, run_id: int) -> dict:
        try:
            result = export_reconciliation(int(run_id))
            return {"ok": True, "export": result}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not export this reconciliation."}

    def open_recon_export(self, run_id: int) -> dict:
        result = self.export_recon_run(run_id)
        if not result.get("ok"):
            return result
        path = (result.get("export") or {}).get("xlsx") or ""
        try:
            _open_path(str(path))
        except OSError:
            return {"ok": False, "error": "The export was created but could not be opened."}
        return result

    def _actor(self) -> str:
        try:
            state = auth.get_auth_state()
            email = str(state.get("email") or "").strip()
            if email:
                return email
        except Exception:
            pass
        return "local user"

    def get_reports(self) -> dict:
        try:
            return {"ok": True, **report_packs()}
        except Exception:
            return {"ok": False, "error": "Could not load generated packs."}

    def approve_bank_row(self, row_id: int, decision: str = "approved", note: str = "") -> dict:
        """Approve or reject one inferred bank row.

        Inferred rows are not printed in the statement, so a person has to
        accept them before they can leave the approval sheet.
        """
        try:
            from apps.engine.row_approvals import decide_row

            result = decide_row(int(row_id), decision, note or None)
        except Exception:
            return {"ok": False, "error": "Could not save that decision. Try again."}
        if not result.get("ok"):
            return result
        return result

    def get_extracted_record(self, row_id: int) -> dict:
        try:
            row_pk = int(row_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "That extracted record was not found."}
        session = get_session()
        try:
            extracted = session.get(ExtractedRow, row_pk)
            if extracted is None:
                return {"ok": False, "error": "That extracted record was not found."}
            stored = session.get(StoredFile, extracted.file_id)
            try:
                payload = json.loads(extracted.payload_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {"raw": extracted.payload_json}
            return {
                "ok": True,
                "record": payload,
                "file": {
                    "id": stored.id if stored else None,
                    "name": stored.original_name if stored else "",
                    "kind": extracted.kind,
                },
                "source_page": extracted.source_page,
                "source_bbox": extracted.source_bbox,
            }
        finally:
            session.close()

    def open_source_file(self, file_id: int) -> dict:
        try:
            file_pk = int(file_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "That source file was not found."}
        session = get_session()
        try:
            stored = session.get(StoredFile, file_pk)
            if stored is None:
                return {"ok": False, "error": "That source file was not found."}
            path = resolve_storage_key(stored.storage_key)
            if not path.is_file():
                return {
                    "ok": False,
                    "error": "The stored source file is missing.",
                }
            _open_path(str(path))
            return {"ok": True, "name": stored.original_name}
        except OSError as exc:
            return {"ok": False, "error": f"Could not open the source file. {exc}"}
        finally:
            session.close()

    def save_ui_location(self, entry: dict | None) -> dict:
        try:
            save_ui_location(entry if isinstance(entry, dict) else None)
            return {"ok": True}
        except Exception:
            return {"ok": False}

    def save_firm(self, name: str) -> dict:
        try:
            firm = save_firm(name)
            return {
                "ok": True,
                "firm": firm,
                "clients": _clients_payload(),
                "license": get_license_status(),
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def set_guide_dismissed(self, dismissed: bool = True) -> dict:
        set_guide_dismissed(bool(dismissed))
        return {"ok": True, "guide_dismissed": is_guide_dismissed()}

    def create_client(self, name: str, gstin: str = "", profile: dict | None = None) -> dict:
        try:
            client = create_client(name, gstin, profile)
            return {"ok": True, "client": client, "clients": _clients_payload()}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def update_client_profile(self, client_id: int, profile: dict | None = None) -> dict:
        try:
            client = update_client_profile(int(client_id), profile)
            return {"ok": True, "client": client, "clients": _clients_payload()}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def get_profile_options(self) -> dict:
        return {"ok": True, **profile_options()}

    def delete_client_desk(self, client_id: int) -> dict:
        try:
            delete_client(int(client_id))
            return {"ok": True, "clients": _clients_payload()}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def activate_license(self, key: str) -> dict:
        try:
            license_state = activate_key(str(key or ""))
            return {"ok": True, "license": license_state}
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

    def delete_period_desk(self, period_id: int) -> dict:
        try:
            removed = delete_period(int(period_id))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "removed": removed,
            "periods": list_periods(removed["client_id"]),
        }

    def set_client_tolerances(self, client_id: int, days, amount) -> dict:
        try:
            client = set_client_tolerances(int(client_id), days, amount)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "client": client}

    def set_period_tolerances(self, period_id: int, days=None, amount=None) -> dict:
        try:
            period = set_period_tolerances(int(period_id), days, amount)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "period": period,
            "periods": list_periods(period["client_id"]),
        }

    def get_period_desk(self, period_id: int) -> dict:
        period = get_period(int(period_id))
        if period is None:
            return {"ok": False, "error": "Period was not found."}
        self._current_period_id = period["id"]
        client = get_client(period["client_id"])
        try:
            versions = list_pack_versions(period["id"])
        except Exception:
            versions = []
        return {
            "ok": True,
            "client": client,
            "period": period,
            "files": list_period_files(period["id"]),
            "kinds": [{"id": key, "label": KIND_LABELS[key]} for key in KINDS],
            "currencies": currency_options(),
            "pack": get_period_pack(period["id"]),
            "pack_versions": versions,
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
                    "All files (*.*)",
                    "Client documents (*.pdf;*.json;*.xml;*.zip;*.txt;*.csv;*.xlsx;*.xls;*.jpg;*.jpeg;*.png;*.webp;*.tif;*.tiff;*.docx)",
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
        return {
            "ok": True,
            "output_path": str(path),
            "path_warnings": path_sync_warnings(str(path)),
        }

    def set_output_folder(self, path: str) -> dict:
        try:
            dest = set_output_root(path)
            return {
                "ok": True,
                "output_path": str(dest),
                "path_warnings": path_sync_warnings(str(dest)),
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def pick_folder(self) -> dict:
        if _WINDOW is None:
            return {"ok": False, "paths": [], "error": "Window is not ready."}
        try:
            picked = _WINDOW.create_file_dialog(_dialog_folder(), allow_multiple=True)
        except TypeError:
            try:
                picked = _WINDOW.create_file_dialog(_dialog_folder())
            except Exception as exc:
                return {"ok": False, "paths": [], "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "paths": [], "error": str(exc)}
        return {"ok": True, "paths": list(picked or [])}

    def take_drop_paths(self) -> dict:
        try:
            from webview.dom import _dnd_state
        except Exception:
            return {"ok": True, "paths": []}
        leftover = list(_dnd_state.get("paths") or [])
        _dnd_state["paths"] = []
        paths: list[str] = []
        for item in leftover:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                paths.append(str(item[1]))
            elif isinstance(item, str) and item:
                paths.append(item)
        return {"ok": True, "paths": paths}

    def start_dump(self, period_id: int, paths: list[str]) -> dict:
        try:
            updates.assert_update_allows_ingest()
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if not paths:
            return {"ok": False, "error": "No files or folders were chosen."}
        try:
            preflight = preflight_paths(list(paths))
            assert_can_ingest(preflight.accepted_count)
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

    def set_file_currency(self, file_id: int, code: str = "") -> dict:
        try:
            row = set_file_currency(int(file_id), code or None)
            return {"ok": True, "file": row}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    def remove_period_file(self, file_id: int) -> dict:
        try:
            removed = remove_period_file(int(file_id))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not remove this file. Nothing was changed."}
        desk = self.get_period_desk(removed["period_id"])
        if not desk.get("ok"):
            # The file is gone; let the caller refresh rather than claim failure.
            return {"ok": True, "removed_file_id": removed["file_id"], "refresh": True}
        return {**desk, "removed_file_id": removed["file_id"]}

    def reparse_period(self, period_id: int) -> dict:
        try:
            updates.assert_update_allows_ingest()
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            job = start_job(int(period_id))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        _run_job_thread(job["id"], lambda: reparse_period(int(period_id), job["id"]))
        return {"ok": True, "job_id": job["id"]}

    def cancel_job(self, job_id: int) -> dict:
        """Ask the running import to stop after the file it is on."""
        try:
            from apps.engine.dump import cancel_job

            result = cancel_job(int(job_id))
            return {"ok": True, **result}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            return {"ok": False, "error": "Could not cancel this job."}

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

    def set_recon_decision(
        self,
        period_id: int,
        row_key: str,
        decision: str,
        reason_code: str = "",
        note: str = "",
    ) -> dict:
        try:
            pid = int(period_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Period was not found."}
        if get_period(pid) is None:
            return {"ok": False, "error": "Period was not found."}
        record: dict | None = None
        saved: dict[str, dict] = {}
        session = get_session()
        try:
            record = decisions.save(
                session,
                pid,
                row_key,
                decision,
                reason_code=reason_code,
                note=note,
                decided_by=_firm_name(),
            )
            session.commit()
            # The pack summary on disk was written at parse time, so re-attach
            # the saved decisions here; otherwise the tray would not show the
            # decision until the month was run again.
            saved = decisions.load(session, pid)
        except ValueError as exc:
            session.rollback()
            return {"ok": False, "error": str(exc)}
        except Exception:
            session.rollback()
            return {"ok": False, "error": "Could not save that decision."}
        finally:
            session.close()
        try:
            pack = decisions.refresh_pack(get_period_pack(pid), saved)
        except Exception:
            pack = None
        return {"ok": True, "pack": pack, "decision": record}

    def clear_recon_decision(self, period_id: int, row_key: str) -> dict:
        return self.set_recon_decision(period_id, row_key, "", "", "")

    def export_recon_exceptions(self, period_id: int) -> dict:
        return self._export_recon_file(period_id, "exceptions")

    def export_recon_audit_summary(self, period_id: int) -> dict:
        return self._export_recon_file(period_id, "summary")

    def _export_recon_file(self, period_id: int, kind: str) -> dict:
        try:
            pid = int(period_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Period was not found."}
        pack = get_period_pack(pid)
        if not pack or not pack.get("recon"):
            return {
                "ok": False,
                "error": "Run the month first; there is no reconciliation to export.",
            }
        period = get_period(pid)
        client = get_client(period["client_id"]) if period else None
        folder = Path(pack.get("path") or "")
        name = (
            "Exceptions_Only.xlsx"
            if kind == "exceptions"
            else "Reconciliation_Summary.xlsx"
        )
        dest = folder / name
        firm_name = ""
        try:
            firm_name = str((get_firm() or {}).get("name") or "").strip()
        except Exception:  # a missing firm only leaves the masthead line out
            firm_name = ""
        try:
            if kind == "exceptions":
                write_exceptions_workbook(
                    dest,
                    client_name=(client or {}).get("name") or "",
                    period_label=(period or {}).get("label") or "",
                    recon=pack.get("recon") or {},
                    firm=firm_name,
                )
            else:
                write_audit_summary(
                    dest,
                    client_name=(client or {}).get("name") or "",
                    period_label=(period or {}).get("label") or "",
                    recon=pack.get("recon") or {},
                    firm=firm_name,
                )
        except OSError as exc:
            return {"ok": False, "error": f"Could not write the file: {exc}"}
        try:
            _open_path(str(dest))
        except OSError:
            pass
        return {"ok": True, "path": str(dest)}
    def list_pack_versions(self, period_id: int) -> dict:
        try:
            return {"ok": True, "versions": list_pack_versions(int(period_id))}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def restore_pack_version(self, period_id: int, snapshot_id: str) -> dict:
        try:
            result = restore_pack_version(int(period_id), str(snapshot_id))
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, **result, "pack": get_period_pack(int(period_id))}

    def set_snapshot_retention(self, days: int) -> dict:
        try:
            value = set_snapshot_retention_days(days)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "snapshot_retention_days": value}

    def set_file_password(self, file_id: int, password: str) -> dict:
        if not str(password or "").strip():
            return {"ok": False, "error": "Enter the PDF password."}
        store_file_password(int(file_id), str(password))
        return {"ok": True}

    def get_source_crop(self, file_id: int, page: int, bbox: str = "") -> dict:
        return get_source_crop(int(file_id), int(page), bbox or None)

    def get_file_preview(
        self,
        file_id: int,
        page: int = 1,
        password: str = "",
        sheet: str = "",
        formatted: bool = True,
    ) -> dict:
        """One page of the source document, for the in-app preview pane."""
        try:
            return build_preview(
                int(file_id),
                int(page or 1),
                str(password or ""),
                str(sheet or ""),
                bool(formatted),
            )
        except (TypeError, ValueError):
            return {"ok": False, "error": "Could not open that file.", "reason": "unreadable"}
        except Exception:  # noqa: BLE001 - the pane needs a message, not a traceback
            return {"ok": False, "error": "Could not open that file.", "reason": "unreadable"}

    def open_source_file(self, file_id: int) -> dict:
        path = source_file_path(int(file_id))
        if path is None:
            return {"ok": False, "error": "The stored source file is missing."}
        try:
            _open_path(str(path))
        except OSError as exc:
            return {"ok": False, "error": f"Could not open that file. {exc}"}
        return {"ok": True}

    def tesseract_status(self) -> dict:
        try:
            from apps.engine.ocr import tesseract_status

            return {"ok": True, **tesseract_status()}
        except Exception:
            return {"ok": True, "found": False, "path": None, "note": "OCR module not loaded"}

    def wipe_and_reset(self) -> dict:
        """Delete every client, file and pack, then reset in place.

        The window stays open and the sign-in survives: only client data is
        wiped, so the engine lazily rebuilds an empty library and the UI
        returns to the first-run setup without asking for a login again.
        """
        global _wipe_epoch
        login_snapshot = auth.snapshot_auth_settings()
        _wipe_epoch += 1
        try:
            wipe_all()
        except OSError as exc:
            return {"ok": False, "error": f"Could not delete the library folder. {exc}"}
        auth.restore_auth_settings(login_snapshot)
        self._current_period_id = None
        state = self.get_state()
        return {"ok": True, **state}


def _firm_name() -> str:
    """The firm name recorded on a saved decision's audit trail."""
    try:
        firm = get_firm()
    except Exception:
        return "Firm"
    name = str((firm or {}).get("name") or "").strip()
    return name or "Firm"


def _open_path(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def ui_index() -> str:
    return (_bundle_root() / "ui" / "index.html").as_uri()


def app_icon_path() -> str | None:
    path = _bundle_root() / "ui" / "app-icon.ico"
    return str(path) if path.is_file() else None


def claim_taskbar_identity(app_id: str = "CAUnpacker.Desktop.1") -> None:
    """Give the process its own taskbar identity.

    Without this Windows groups the window under python.exe, so the taskbar
    button shows the Python icon even though the window frame carries ours.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def _load_icon(path: str, size: int):
    import ctypes
    from ctypes import wintypes

    image_icon = 1
    lr_loadfromfile = 0x0010
    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    return user32.LoadImageW(None, path, image_icon, size, size, lr_loadfromfile)


def _send_window_icon(hwnd, path: str) -> None:
    import ctypes
    from ctypes import wintypes

    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    sm_cxicon = 11
    sm_cxsmicon = 49
    user32 = ctypes.windll.user32
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    # Match the desktop's icon metrics; a 32px bitmap looks blurred at 150%.
    big_size = max(32, int(user32.GetSystemMetrics(sm_cxicon) or 0))
    small_size = max(16, int(user32.GetSystemMetrics(sm_cxsmicon) or 0))
    big = _load_icon(path, big_size)
    small = _load_icon(path, small_size)
    if big:
        user32.SendMessageW(hwnd, wm_seticon, icon_big, big)
    if small:
        user32.SendMessageW(hwnd, wm_seticon, icon_small, small)


def _find_window_by_title(title: str):
    """Find our own top-level window by title, falling back to any visible one."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [
        ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
        wintypes.LPARAM,
    ]
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        return hwnd

    matches: list[int] = []
    pid = os.getpid()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _visit(candidate, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(candidate, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(candidate):
            return True
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(candidate, buffer, 256)
        if buffer.value == title:
            matches.append(candidate)
            return False
        return True

    user32.EnumWindows(_visit, 0)
    return matches[0] if matches else None


def apply_window_icon(title: str = "CA Unpacker") -> None:
    """Put the app icon on the window (and any dev console) after it is shown."""
    if sys.platform != "win32":
        return
    path = app_icon_path()
    if not path:
        return
    try:
        import ctypes

        hwnd = _find_window_by_title(title)
        if hwnd:
            _send_window_icon(hwnd, path)
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            _send_window_icon(console, path)
    except Exception:
        pass


def _log_crash(message: str) -> None:
    """Best effort: a failing log must never hide the real failure."""
    try:
        log_path = get_library_path() / "app.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"\n===== {stamp} =====\n{message.rstrip()}\n")
        # A crash loop must not fill the disk. Truncating in place keeps the
        # fault handler's own handle on the same file valid.
        try:
            if log_path.stat().st_size > 1_000_000:
                shutil.copyfile(log_path, log_path.with_name("app.log.1"))
                log_path.write_text("", encoding="utf-8")
        except OSError:
            pass
    except OSError:
        pass


_FAULT_LOG = None


def _enable_fault_handler() -> None:
    """Record native crashes (PDF/OCR C extensions) to the library log."""
    global _FAULT_LOG
    if _FAULT_LOG is not None:
        return
    try:
        import faulthandler

        log_path = get_library_path() / "app.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _FAULT_LOG = open(log_path, "a", encoding="utf-8")
        faulthandler.enable(file=_FAULT_LOG)
    except (OSError, AttributeError):
        _FAULT_LOG = None


def _show_fatal(message: str) -> None:
    """Surface a startup failure as a dialog instead of a silent exit."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, message, "CA Unpacker", 0x00000010 | 0x00000000
        )
    except Exception as exc:
        # This is the last chance to tell the user why the app did not start;
        # if the dialog fails, the log must carry the message instead.
        _log.warning("Could not show a startup dialog (%s): %s", message, exc)


def _friendly_startup_message(error: BaseException) -> str:
    """Turn a startup exception into something a CA can act on."""
    text = str(error or "").strip()
    lowered = text.lower()
    if "newer than supported" in lowered:
        return (
            "This data folder was made by a newer version of CA Unpacker.\n\n"
            "Install the latest version and open it again. Nothing was deleted "
            "and every file is still in that folder."
        )
    if "already using this library" in lowered:
        return (
            "Another CA Unpacker window is already using this folder.\n\n"
            "Close it and try again. If no window is open, that folder is on "
            "another computer or a network drive."
        )
    if isinstance(error, PermissionError) or "permission denied" in lowered:
        return (
            "Windows would not let CA Unpacker write to its data folder.\n\n"
            "Move the folder out of OneDrive, Desktop or a synced drive, then "
            "open the app again."
        )
    if "no space left" in lowered:
        return "The disk is full, so CA Unpacker could not save its data. Free some space and try again."
    return text.splitlines()[-1] if text else "Unknown error"


def _install_crash_hooks() -> None:
    """Log uncaught errors from the main thread and from worker threads.

    pythonw has no console, so without this a crash in a worker left nothing
    behind but a closed window.
    """
    import traceback

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        _log_crash("".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = _hook
    try:

        def _thread_hook(args) -> None:
            if args.exc_type is SystemExit:
                return
            name = getattr(args.thread, "name", "worker")
            detail = "".join(
                traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
            )
            _log_crash(f"thread {name} failed:\n{detail}")

        threading.excepthook = _thread_hook
    except Exception as exc:
        _log.warning("Could not install the thread exception hook: %s", exc)


def _run_job_thread(job_id: int, fn) -> None:
    epoch = _wipe_epoch

    def work() -> None:
        ran = False
        try:
            if epoch == _wipe_epoch:
                ran = True
                fn()
        except Exception as exc:
            from apps.engine.dump import JobCancelled

            if isinstance(exc, JobCancelled):
                # The user asked to cancel: the job is already marked
                # "cancelled" and files processed so far are kept.
                return
            import traceback

            # Log first, but never let a logging failure stop the job from
            # being marked failed - a stuck "parsing" job blocks the period
            # until the library is deleted.
            try:
                _log_crash(traceback.format_exc())
            except Exception:
                pass
            try:
                leftover = get_job(job_id)
                if leftover is None or leftover.get("status") in {
                    "queued",
                    "routing",
                    "parsing",
                    "cancel_requested",
                }:
                    fail_job(job_id, "Could not process these files.")
            except Exception as fail_exc:
                # The job would stay "parsing" and block the period until the
                # library is reset, so record why the fallback failed.
                _log.warning(
                    "Could not mark job %s as failed after a crash: %s",
                    job_id,
                    fail_exc,
                )
        finally:
            with _job_threads_lock:
                _job_threads.discard(threading.current_thread())
            if ran and epoch != _wipe_epoch:
                # The library was wiped while this job was running; the job
                # may have recreated files or the database on disk. Wipe again
                # so the reset the user asked for still ends empty.
                try:
                    wipe_all()
                except OSError:
                    pass

    thread = threading.Thread(target=work, daemon=True)
    with _job_threads_lock:
        _job_threads.add(thread)
    thread.start()


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


def _startup_auth_sync() -> None:
    try:
        auth.refresh_session()
        auth.fetch_quota()
        auth.send_heartbeat()
    except Exception:
        pass


def _pending_deep_link_path() -> Path:
    return get_library_path() / _PENDING_AUTH_CALLBACK_FILE


def _acquire_single_instance_mutex() -> bool:
    """Return True when this process is the primary desktop instance."""
    global _mutex_handle
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, True, _SINGLE_INSTANCE_MUTEX_NAME)
    return kernel32.GetLastError() != 183


def _delegate_deep_link_to_running_instance(url: str) -> None:
    path = _pending_deep_link_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(url, encoding="utf-8")
    tmp.replace(path)


def _read_pending_deep_link() -> str | None:
    path = _pending_deep_link_path()
    if not path.is_file():
        return None
    for _ in range(6):
        try:
            if not path.is_file():
                return None
            url = path.read_text(encoding="utf-8").strip()
            if url and url.startswith("caunpacker://"):
                path.unlink(missing_ok=True)
                return url
            if url:
                # non matching content, discard
                path.unlink(missing_ok=True)
                return None
            # empty, retry shortly
            time.sleep(0.04)
        except OSError:
            time.sleep(0.04)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    return None


_UI_EVENTS: list[dict] = []
_UI_EVENTS_LOCK = threading.Lock()
_UI_EVENTS_LIMIT = 25


def _queue_ui_event(event: dict) -> None:
    """Hand work to the page from a background thread.

    pywebview's window belongs to the UI thread. Calling evaluate_js from a
    worker thread raised a COM fault (0x8001010d) and took the whole app down,
    so background code only appends here and the page drains this queue on its
    own timer (see DesktopApi.drain_ui_events and the pump in app.js).
    """
    if not event:
        return
    with _UI_EVENTS_LOCK:
        _UI_EVENTS.append(dict(event))
        del _UI_EVENTS[:-_UI_EVENTS_LIMIT]


def _drain_ui_events() -> list[dict]:
    with _UI_EVENTS_LOCK:
        events = list(_UI_EVENTS)
        _UI_EVENTS.clear()
    return events


def _notify_auth_ui_refresh(result: dict) -> None:
    """Queue the post-sign-in refresh; the page applies it on the UI thread."""
    if not result:
        return
    if result.get("ok"):
        _queue_ui_event({"type": "auth_refresh"})
    elif result.get("error"):
        _queue_ui_event({"type": "auth_error", "message": str(result["error"])})


def _process_deep_link(api: DesktopApi, url: str) -> dict:
    result = api.handle_auth_callback(url)
    _notify_auth_ui_refresh(result)
    return result


def _check_pending_now(api: DesktopApi) -> None:
    try:
        pending = _read_pending_deep_link()
        if pending:
            _process_deep_link(api, pending)
    except Exception as exc:
        # A dropped sign-in callback looks like nothing happened at all.
        _log.warning("Could not process a pending sign-in link: %s", exc)


def _start_deep_link_poller(api: DesktopApi) -> None:
    def poll() -> None:
        while True:
            time.sleep(0.5)
            pending = _read_pending_deep_link()
            if pending:
                _process_deep_link(api, pending)

    threading.Thread(target=poll, daemon=True).start()


def _on_window_shown(api: DesktopApi) -> None:
    apply_window_icon()
    _bind_explorer_drop(api)
    if _startup_deep_link:
        _process_deep_link(api, _startup_deep_link)
    # immediate pending check (handles race between poller start and arrival / shown timing)
    try:
        pending = _read_pending_deep_link()
        if pending:
            _process_deep_link(api, pending)
    except Exception as exc:
        _log.warning("Could not process a pending sign-in link: %s", exc)
    _start_deep_link_poller(api)
    # also check on load (helps if deep link processed after initial render)
    if _WINDOW is not None:
        try:
            _WINDOW.events.loaded += lambda: _check_pending_now(api)
        except Exception:
            pass
        try:
            # WebView2 can reset the frame icon when the document loads.
            _WINDOW.events.loaded += lambda: apply_window_icon()
        except Exception:
            pass


def main() -> None:
    import traceback

    claim_taskbar_identity()
    _enable_fault_handler()
    _install_crash_hooks()

    global _startup_deep_link
    deep_link = extract_deep_link_url()
    is_primary = _acquire_single_instance_mutex()
    if not is_primary:
        if deep_link:
            _delegate_deep_link_to_running_instance(deep_link)
        else:
            # A second double-click used to exit silently and look like a crash.
            _show_fatal(
                "CA Unpacker is already open.\n\n"
                "Switch to the window that is already running, or close it and "
                "try again."
            )
        return
    _startup_deep_link = deep_link

    try:
        init_library()
        get_engine()
        # Free any period left mid-parse by the last crash or restart.
        try:
            reconcile_interrupted_work()
        except Exception as exc:
            # Otherwise the period keeps saying it is already being processed.
            _log.warning("Could not reconcile interrupted work at startup: %s", exc)
        # Claim caunpacker:// so browser sign-in can hand the session back.
        # Best effort: the in-app form still works if this fails.
        registered, err = ensure_registered()
        if err:
            # Log but don't fail - in-app form still works
            import logging

            logging.getLogger(__name__).warning(
                "Failed to register caunpacker:// protocol: %s", err
            )
        elif registered:
            import logging

            logging.getLogger(__name__).info(
                "Registered caunpacker:// protocol for browser handoff"
            )
        # Auth sync talks to the network (up to three round trips). Do it in the
        # background so the window appears immediately instead of after ~45s.
        threading.Thread(target=_startup_auth_sync, daemon=True).start()
        global _WINDOW
        api = DesktopApi()
        # Keep the window usable on any screen: never taller than ~90% of the
        # work area and always placed inside it (150% DPI made it overflow).
        width, height = 1120, 760
        x = y = None
        try:
            primary = webview.screens[0]
            width = min(width, max(primary.width - 20, 700))
            height = min(height, max(primary.height - 16, 480))
            x = max(0, (primary.width - width) // 2)
            y = max(0, (primary.height - height) // 2)
        except Exception:
            pass
        _WINDOW = webview.create_window(
            "CA Unpacker",
            ui_index(),
            js_api=api,
            width=width,
            height=height,
            x=x,
            y=y,
            min_size=(880, 580),
            background_color="#2C3330",
        )
        _WINDOW.events.shown += lambda: _on_window_shown(api)
        # Best-effort, non-blocking: only checks once the user is signed in.
        _schedule_startup_update_check()
        webview.start(icon=app_icon_path())
    except Exception as exc:
        detail = traceback.format_exc()
        _log_crash(detail)
        _show_fatal(
            "CA Unpacker could not start.\n\n"
            f"{_friendly_startup_message(exc)}\n\n"
            f"Details were written to:\n{get_library_path() / 'app.log'}"
        )
        raise
