from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import webview

from apps.desktop import updater
from apps.engine import updates
from apps.engine.clients import create_client, delete_client, get_client, list_clients
from apps.engine.db import get_engine
from apps.engine.dump import (
    fail_job,
    get_job,
    ingest_paths,
    list_period_files,
    override_kind,
    preflight_paths,
    reparse_period,
    start_job,
)
from apps.engine.firm import get_firm, save_firm
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.desktop.protocol import ensure_registered, is_registered
from apps.engine import auth
from apps.engine.license import activate_key, assert_can_ingest, get_license_status
from apps.engine.library import get_library_path, init_library
from apps.engine.settings import (
    get_output_root,
    is_guide_dismissed,
    path_sync_warnings,
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
from apps.version import APP_VERSION

_WINDOW: webview.Window | None = None
_PENDING_AUTH_CALLBACK_FILE = "pending_auth_callback.url"
_SINGLE_INSTANCE_MUTEX_NAME = "Global\\CAUnpackerSingleInstance"
_startup_deep_link: str | None = None
_mutex_handle: int | None = None

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
        except Exception:
            pass

    try:
        threading.Thread(
            target=work, name="update-startup-check", daemon=True
        ).start()
    except Exception:
        pass


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

    def get_state(self) -> dict:
        init_library()
        output = get_output_root()
        library = get_library_path()
        return {
            "app_version": APP_VERSION,
            "firm": get_firm(),
            "clients": list_clients(),
            "library_path": str(library),
            "output_path": str(output) if output else "",
            "guide_dismissed": is_guide_dismissed(),
            "license": get_license_status(),
            "auth": auth.get_auth_state(),
            "path_warnings": path_sync_warnings(
                str(library), str(output) if output else ""
            ),
        }

    def save_firm(self, name: str) -> dict:
        try:
            firm = save_firm(name)
            return {
                "ok": True,
                "firm": firm,
                "clients": list_clients(),
                "license": get_license_status(),
            }
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

    def delete_client_desk(self, client_id: int) -> dict:
        try:
            delete_client(int(client_id))
            return {"ok": True, "clients": list_clients()}
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


def _startup_auth_sync() -> None:
    try:
        auth.refresh_session()
        auth.fetch_quota()
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


def _notify_auth_ui_refresh(result: dict) -> None:
    if not result:
        return

    def _do_js() -> None:
        if _WINDOW is None:
            return
        try:
            if result.get("ok"):
                # robust: full state refresh + redecide screen (setup for fresh post-signup)
                # also ensures quota/auth UI fully updated even if window was loading
                js = (
                    "(async () => { try { "
                    "if (typeof ensurePostAuth === 'function') { await ensurePostAuth(); } "
                    "else if (typeof refreshAuthState === 'function') { await refreshAuthState(); "
                    "const api = (window.pywebview && window.pywebview.api) || null; "
                    "if (api && api.get_state) { "
                    "const s = await api.get_state(); "
                    "if (s && s.firm && s.output_path && typeof showDesk === 'function') showDesk(s); "
                    "else if (typeof showSetup === 'function') showSetup(s || {}); "
                    "} } "
                    "} catch (e) {} })();"
                )
                _WINDOW.evaluate_js(js)
            elif result.get("error"):
                message = json.dumps(str(result["error"]))
                _WINDOW.evaluate_js(
                    f"showError(document.getElementById('auth-error'), {message})"
                )
        except Exception:
            pass

    if _WINDOW is None:
        # window not assigned yet (rare timing), retry shortly
        def _delayed() -> None:
            time.sleep(0.7)
            _do_js()
        threading.Thread(target=_delayed, daemon=True).start()
    else:
        _do_js()


def _process_deep_link(api: DesktopApi, url: str) -> dict:
    result = api.handle_auth_callback(url)
    _notify_auth_ui_refresh(result)
    return result


def _check_pending_now(api: DesktopApi) -> None:
    try:
        pending = _read_pending_deep_link()
        if pending:
            _process_deep_link(api, pending)
    except Exception:
        pass


def _start_deep_link_poller(api: DesktopApi) -> None:
    def poll() -> None:
        while True:
            time.sleep(0.5)
            pending = _read_pending_deep_link()
            if pending:
                _process_deep_link(api, pending)

    threading.Thread(target=poll, daemon=True).start()


def _on_window_shown(api: DesktopApi) -> None:
    _bind_explorer_drop(api)
    if _startup_deep_link:
        _process_deep_link(api, _startup_deep_link)
    # immediate pending check (handles race between poller start and arrival / shown timing)
    try:
        pending = _read_pending_deep_link()
        if pending:
            _process_deep_link(api, pending)
    except Exception:
        pass
    _start_deep_link_poller(api)
    # also check on load (helps if deep link processed after initial render)
    if _WINDOW is not None:
        try:
            _WINDOW.events.loaded += lambda: _check_pending_now(api)
        except Exception:
            pass


def main() -> None:
    import traceback

    global _startup_deep_link
    deep_link = extract_deep_link_url()
    is_primary = _acquire_single_instance_mutex()
    if deep_link and not is_primary:
        _delegate_deep_link_to_running_instance(deep_link)
        return
    _startup_deep_link = deep_link

    try:
        init_library()
        get_engine()
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
        _startup_auth_sync()
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
        _WINDOW.events.shown += lambda: _on_window_shown(api)
        # Best-effort, non-blocking: only checks once the user is signed in.
        _schedule_startup_update_check()
        webview.start(icon=app_icon_path())
    except Exception:
        _log_crash(traceback.format_exc())
        raise
