"""Desktop self-update support: manifest parsing, caching and downloads.

The app is offline-first. The only network calls here are the signed-in
``latest-release`` lookup and the installer download, and both are opt-in from
the desktop shell. Nothing in this module sends document data anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from apps.engine import auth
from apps.engine.library import get_library_path

try:  # apps/version.py is owned by the release packaging task.
    from apps.version import APP_VERSION
except Exception:  # pragma: no cover - import safety only
    APP_VERSION = "0.0.0"


APP_PLATFORM = "windows"

CACHE_TTL = timedelta(hours=6)
CACHE_FILENAME = "update_cache.json"
UPDATE_DIR_NAME = "updates"
INSTALLER_TEMPLATE = "CAUnpacker-Setup-{version}.exe"

APPROVED_HOSTS = (
    "github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
)

STATUSES = frozenset(
    {"idle", "checking", "available", "downloading", "ready", "installing", "error"}
)

_TRANSIENT_MESSAGE = "Could not check for updates. Check your internet connection."
_CANCELLED_MESSAGE = "Update download cancelled."
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_REDIRECTS = 5
_CHUNK_SIZE = 64 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Injectable seam so tests never reach Supabase.
_latest_release_call: Callable[[str, dict[str, Any]], dict] = (
    auth.call_authenticated_function
)


class UpdateCancelled(Exception):
    """Raised when the caller cancels an in-flight installer download."""


@dataclass(frozen=True)
class ReleaseManifest:
    """A validated release announcement from the ``latest-release`` function."""

    version: str
    title: str
    release_notes: str
    installer_url: str
    installer_sha256: str
    installer_size: int
    mandatory: bool
    published_at: str
    minimum_supported_version: str | None = None


@dataclass
class UpdateState:
    """Current update status for the desktop shell."""

    status: str = "idle"
    version: str = ""
    title: str = ""
    notes: str = ""
    mandatory: bool = False
    progress: float = 0.0
    error: str = ""
    downloaded_path: str | None = None
    installer_sha256: str = ""
    installer_size: int = 0

    @property
    def available(self) -> bool:
        return self.status in {"available", "downloading", "ready", "installing"}


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def _require_version(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Release version is missing or invalid.")
    text = value.strip()
    if not _VERSION_RE.match(text):
        raise ValueError(
            f"Version '{text}' is not a valid major.minor.patch version."
        )
    return text


def compare_versions(left: str, right: str) -> int:
    """Compare two strict ``major.minor.patch`` versions.

    Returns -1, 0 or 1. Prerelease and build suffixes are rejected rather than
    silently ordered, because the desktop app only ships plain releases.
    """

    left_text = _require_version(left)
    right_text = _require_version(right)
    left_parts = tuple(int(part) for part in left_text.split("."))
    right_parts = tuple(int(part) for part in right_text.split("."))
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def _approved_host(host: str) -> bool:
    lowered = (host or "").lower().rstrip(".")
    return any(
        lowered == approved or lowered.endswith("." + approved)
        for approved in APPROVED_HOSTS
    )


def _require_approved_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Update download link is invalid.") from exc
    if parts.scheme.lower() != "https":
        raise ValueError("Update download link must use https.")
    if parts.username or parts.password:
        raise ValueError("Update download link must not include credentials.")
    if port not in (None, 443):
        raise ValueError("Update download link must use port 443.")
    if not _approved_host(parts.hostname or ""):
        raise ValueError("Update download link points to an unapproved host.")
    return url


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Release field '{field_name}' is missing or empty.")
    return value.strip()


def _parse_release_dict(data: dict) -> ReleaseManifest:
    if not isinstance(data, dict):
        raise ValueError("Release details are not an object.")

    version = _require_version(data.get("version"))
    title = _require_text(data.get("title"), "title")

    notes = data.get("release_notes")
    if not isinstance(notes, str):
        raise ValueError("Release field 'release_notes' is missing or not text.")

    installer_url = _require_text(data.get("installer_url"), "installer_url")
    _require_approved_url(installer_url)

    checksum = data.get("installer_sha256")
    if not isinstance(checksum, str) or not _SHA256_RE.match(checksum.strip()):
        raise ValueError("Release installer checksum is invalid.")
    checksum = checksum.strip()

    size = data.get("installer_size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("Release installer size is invalid.")

    mandatory = data.get("mandatory", False)
    if not isinstance(mandatory, bool):
        raise ValueError("Release mandatory flag is invalid.")

    published_raw = data.get("published_at")
    published_at = published_raw if isinstance(published_raw, str) else ""

    minimum_raw = data.get("minimum_supported_version")
    minimum_supported_version: str | None = None
    if minimum_raw is not None:
        minimum_supported_version = _require_version(minimum_raw)

    return ReleaseManifest(
        version=version,
        title=title,
        release_notes=notes,
        installer_url=installer_url,
        installer_sha256=checksum,
        installer_size=size,
        mandatory=mandatory,
        published_at=published_at,
        minimum_supported_version=minimum_supported_version,
    )


def parse_latest_release(payload: Any) -> ReleaseManifest | None:
    """Return a validated manifest, or ``None`` when no update is offered."""

    if not isinstance(payload, dict):
        raise ValueError("Update response is not an object.")
    if payload.get("update_available") is not True:
        return None
    release = payload.get("release")
    if not isinstance(release, dict):
        raise ValueError("Update response is missing release details.")
    release = dict(release)
    # The endpoint may publish the floor beside the release rather than in it.
    if (
        "minimum_supported_version" not in release
        and payload.get("minimum_supported_version") is not None
    ):
        release["minimum_supported_version"] = payload["minimum_supported_version"]
    return _parse_release_dict(release)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_path() -> Path:
    return get_library_path() / CACHE_FILENAME


def _parse_when(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip())
    except ValueError:
        return None


def load_update_cache() -> dict:
    """Read the cached release metadata. Corrupt caches are treated as empty."""

    try:
        raw = _cache_path().read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    if _parse_when(data.get("checked_at")) is None:
        return {}
    manifest = data.get("manifest")
    if manifest is not None:
        if not isinstance(manifest, dict):
            return {}
        try:
            _parse_release_dict(manifest)
        except ValueError:
            return {}
    return data


def save_update_cache(cache: dict) -> dict:
    """Atomically persist release metadata and the last check time."""

    payload = dict(cache or {})
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return payload


def _manifest_entry(manifest: ReleaseManifest) -> dict:
    """Serialize a manifest with the effective mandatory flag applied."""

    entry: dict[str, Any] = {
        "version": manifest.version,
        "title": manifest.title,
        "release_notes": manifest.release_notes,
        "installer_url": manifest.installer_url,
        "installer_sha256": manifest.installer_sha256,
        "installer_size": manifest.installer_size,
        "mandatory": _effective_mandatory(manifest),
        "published_at": manifest.published_at,
    }
    if manifest.minimum_supported_version:
        entry["minimum_supported_version"] = manifest.minimum_supported_version
    return entry


def _manifest_from_cache(cache: dict) -> ReleaseManifest | None:
    entry = cache.get("manifest") if isinstance(cache, dict) else None
    if not isinstance(entry, dict):
        return None
    try:
        return _parse_release_dict(entry)
    except ValueError:
        return None


def _cache_is_fresh(cache: dict) -> bool:
    if not cache:
        return False
    if cache.get("current_version") != APP_VERSION:
        return False
    when = _parse_when(cache.get("checked_at"))
    if when is None:
        return False
    return datetime.now() - when < CACHE_TTL


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------


def _current_arch() -> str:
    machine = (platform.machine() or "").lower()
    if machine in {"amd64", "x86_64", "x64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86", "i386", "i686"}:
        return "x86"
    return machine or "x64"


def _is_newer(version: str) -> bool:
    try:
        return compare_versions(version, APP_VERSION) > 0
    except ValueError:
        return False


def _effective_mandatory(manifest: ReleaseManifest) -> bool:
    if manifest.mandatory:
        return True
    minimum = manifest.minimum_supported_version
    if not minimum:
        return False
    try:
        return compare_versions(APP_VERSION, minimum) < 0
    except ValueError:
        return False


def _state_from_manifest(manifest: ReleaseManifest) -> UpdateState:
    if not _is_newer(manifest.version):
        return UpdateState(
            status="idle",
            version=manifest.version,
            title=manifest.title,
            notes=manifest.release_notes,
        )
    return UpdateState(
        status="available",
        version=manifest.version,
        title=manifest.title,
        notes=manifest.release_notes,
        mandatory=_effective_mandatory(manifest),
        installer_sha256=manifest.installer_sha256,
        installer_size=manifest.installer_size,
    )


def _state_from_cache(cache: dict) -> UpdateState:
    manifest = _manifest_from_cache(cache)
    if manifest is None:
        return UpdateState()
    return _state_from_manifest(manifest)


def _fallback_state(cache: dict, error: str) -> UpdateState:
    state = _state_from_cache(cache)
    if state.status == "available":
        return state
    state.status = "idle"
    state.error = error
    return state


def check_for_update(force: bool = False) -> UpdateState:
    """Ask the release endpoint whether a newer build exists.

    A fresh cache (6 hours) is used unless ``force`` is set. Authentication
    errors propagate so the shell can prompt the user to sign in; transient
    network failures fall back to the last known newer release and never invent
    an update.
    """

    cache = load_update_cache()
    if not force and _cache_is_fresh(cache):
        return _state_from_cache(cache)

    body = {
        "current_version": APP_VERSION,
        "platform": APP_PLATFORM,
        "arch": _current_arch(),
    }
    try:
        payload = _latest_release_call("latest-release", body)
    except ValueError:
        raise
    except httpx.HTTPError:
        return _fallback_state(cache, _TRANSIENT_MESSAGE)

    try:
        manifest = parse_latest_release(payload)
    except ValueError:
        return _fallback_state(cache, _TRANSIENT_MESSAGE)

    checked_at = datetime.now().isoformat(timespec="seconds")
    save_update_cache(
        {
            "checked_at": checked_at,
            "current_version": APP_VERSION,
            "manifest": _manifest_entry(manifest) if manifest else None,
        }
    )
    if manifest is None:
        return UpdateState()
    return _state_from_manifest(manifest)


def mandatory_update_required() -> bool:
    """True only when a newer mandatory release is already known locally."""

    manifest = _manifest_from_cache(load_update_cache())
    if manifest is None:
        return False
    return _is_newer(manifest.version) and _effective_mandatory(manifest)


def assert_update_allows_ingest() -> None:
    if mandatory_update_required():
        raise ValueError(
            "A required CA Unpacker update must be installed before processing more files."
        )


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def update_root() -> Path:
    """Absolute installer folder, verified to sit inside the app data folder."""

    base = get_library_path()
    base.mkdir(parents=True, exist_ok=True)
    root = base / UPDATE_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve()
    base_resolved = base.resolve()
    if resolved == base_resolved or not resolved.is_relative_to(base_resolved):
        raise ValueError("Update folder is outside the app data folder.")
    return resolved


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _cancelled(cancel_event: Any) -> bool:
    if cancel_event is None:
        return False
    try:
        return bool(cancel_event.is_set())
    except Exception:
        return False


def _report(callback: Callable[[float], None] | None, fraction: float) -> None:
    if callback is None:
        return
    callback(max(0.0, min(1.0, float(fraction))))


def _file_matches(path: Path, size: int, checksum: str) -> bool:
    try:
        if path.stat().st_size != size:
            return False
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
                hasher.update(chunk)
    except OSError:
        return False
    return hasher.hexdigest() == checksum


def _write_stream(
    response: httpx.Response,
    partial: Path,
    size: int,
    checksum: str,
    progress_callback: Callable[[float], None] | None,
    cancel_event: Any,
) -> None:
    hasher = hashlib.sha256()
    written = 0
    _report(progress_callback, 0.0)
    with partial.open("wb") as handle:
        for chunk in response.iter_bytes(_CHUNK_SIZE):
            if not chunk:
                continue
            if _cancelled(cancel_event):
                raise UpdateCancelled(_CANCELLED_MESSAGE)
            written += len(chunk)
            if written > size:
                raise ValueError("Update download is larger than the release says.")
            hasher.update(chunk)
            handle.write(chunk)
            _report(progress_callback, written / size)
        if _cancelled(cancel_event):
            raise UpdateCancelled(_CANCELLED_MESSAGE)
        handle.flush()
        os.fsync(handle.fileno())
    if written != size:
        raise ValueError("Update download size does not match the release.")
    if hasher.hexdigest() != checksum:
        raise ValueError("Update download failed its checksum.")


def _stream_to_partial(
    client: httpx.Client,
    url: str,
    partial: Path,
    size: int,
    checksum: str,
    progress_callback: Callable[[float], None] | None,
    cancel_event: Any,
) -> None:
    current = url
    for _hop in range(_MAX_REDIRECTS + 1):
        current = _require_approved_url(current)
        with client.stream("GET", current, follow_redirects=False) as response:
            if response.status_code in _REDIRECT_STATUSES:
                location = (response.headers.get("location") or "").strip()
                if not location:
                    raise ValueError("Update download redirect is missing a location.")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            _write_stream(
                response,
                partial,
                size,
                checksum,
                progress_callback,
                cancel_event,
            )
            return
    raise ValueError("Update download redirected too many times.")


def download_update(
    manifest: ReleaseManifest,
    progress_callback: Callable[[float], None] | None = None,
    cancel_event: Any = None,
    *,
    client: httpx.Client | None = None,
) -> Path:
    """Download the installer next to its version folder and verify it.

    Redirects are followed manually so every hop is checked against the
    approved host list. A verified final file is reused without a request.
    """

    version = _require_version(manifest.version)
    url = _require_approved_url(manifest.installer_url)

    size = manifest.installer_size
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("Release installer size is invalid.")

    checksum = manifest.installer_sha256
    if not isinstance(checksum, str) or not _SHA256_RE.match(checksum.strip()):
        raise ValueError("Release installer checksum is invalid.")
    checksum = checksum.strip()

    root = update_root()
    destination = root / version
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / INSTALLER_TEMPLATE.format(version=version)
    partial = final.with_name(final.name + ".partial")

    if final.exists():
        if _file_matches(final, size, checksum):
            _report(progress_callback, 1.0)
            return final
        _unlink_quiet(final)

    if _cancelled(cancel_event):
        _unlink_quiet(partial)
        raise UpdateCancelled(_CANCELLED_MESSAGE)

    owns_client = client is None
    active = client or httpx.Client(
        timeout=httpx.Timeout(30.0, read=120.0),
        follow_redirects=False,
    )
    try:
        _stream_to_partial(
            active,
            url,
            partial,
            size,
            checksum,
            progress_callback,
            cancel_event,
        )
    except BaseException:
        _unlink_quiet(partial)
        raise
    finally:
        if owns_client:
            active.close()

    os.replace(partial, final)
    _report(progress_callback, 1.0)
    return final
