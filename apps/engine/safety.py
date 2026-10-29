"""Undo insurance for output packs: snapshots, trash, and safe restore.

Everything this module writes lives under ``<library>/safety`` so a snapshot is
never inside a client or period folder and can never be picked up by a later
pack run.  Nothing here deletes a pack folder outright: old versions are
snapshots, and anything that has to be set aside is moved to the trash area.

The important guarantee is ``restore_snapshot``: the live folder is snapshotted
before it is touched, and if the swap fails half way the folder is put back
byte-for-byte as it was, so a partial restore never reaches the user.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.engine.library import get_library_path, packs_root

SAFETY_DIR_NAME = "safety"
SNAPSHOTS_DIR_NAME = "snapshots"
TRASH_DIR_NAME = "trash"
CONTENT_DIR_NAME = "content"
MANIFEST_NAME = "manifest.json"
DAILY_REASON = "daily-packs-root"
DEFAULT_RETENTION_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def safety_root() -> Path:
    return get_library_path() / SAFETY_DIR_NAME


def snapshots_root() -> Path:
    path = safety_root() / SNAPSHOTS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def trash_root() -> Path:
    path = safety_root() / TRASH_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _new_id(when: datetime) -> str:
    return f"{when.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _valid_id(entry_id: str) -> str:
    text = str(entry_id or "").strip()
    if not text or any(ch in text for ch in '\\/:*?"<>|') or text in {".", ".."}:
        raise ValueError("That version was not found.")
    return text


def _write_manifest(folder: Path, manifest: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / MANIFEST_NAME
    scratch = folder / f"{MANIFEST_NAME}.tmp"
    scratch.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    scratch.replace(target)


def _read_manifest(folder: Path) -> dict | None:
    path = folder / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _folder_report(path: Path) -> tuple[list[str], int]:
    """Return (relative file names, total bytes) so a manifest says what it holds."""
    names: list[str] = []
    total = 0
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        names.append(item.relative_to(path).as_posix())
        try:
            total += item.stat().st_size
        except OSError:
            pass
    return names, total


def _is_empty(path: Path) -> bool:
    try:
        return not any(path.iterdir())
    except OSError:
        return True


def _guard_source(path: Path) -> Path:
    """Only ever copy or move a real folder that is outside the safety area."""
    source = Path(path)
    if not source.exists():
        raise ValueError("That folder does not exist.")
    if not source.is_dir():
        raise ValueError("Only a folder can be snapshotted.")
    resolved = source.resolve()
    safety = safety_root().resolve()
    if (
        resolved == safety
        or resolved.is_relative_to(safety)
        or safety.is_relative_to(resolved)
    ):
        raise ValueError(
            "That folder holds the app's own previous versions, so it cannot be copied there."
        )
    return source


def _parse_created(manifest: dict) -> datetime | None:
    raw = str(manifest.get("created_at") or "")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def snapshot(
    path: str | Path,
    *,
    reason: str = "manual",
    now: datetime | None = None,
    purge_first: bool = True,
) -> dict | None:
    """Copy a pack folder into the snapshot area with a small JSON manifest.

    Returns ``None`` when there is nothing to protect (missing or empty folder),
    so callers can snapshot unconditionally before writing.
    """
    source = Path(path)
    if not source.exists() or not source.is_dir() or _is_empty(source):
        return None
    source = _guard_source(source)
    when = now or utcnow()
    folder = snapshots_root() / _new_id(when)
    folder.mkdir(parents=True, exist_ok=False)
    content = folder / CONTENT_DIR_NAME
    try:
        shutil.copytree(source, content)
        names, total = _folder_report(content)
        manifest = {
            "kind": "snapshot",
            "id": folder.name,
            "created_at": when.isoformat(),
            "reason": str(reason or "manual"),
            "source": str(source),
            "file_count": len(names),
            "byte_count": total,
            "files": names,
        }
        _write_manifest(folder, manifest)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if purge_first:
        try:
            purge(now=when)
        except (OSError, ValueError):
            pass  # housekeeping must never fail a snapshot
    return manifest


def _entries(root: Path) -> list[dict]:
    entries: list[dict] = []
    if not root.exists():
        return entries
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        manifest = _read_manifest(folder)
        if manifest is None:
            continue
        manifest.setdefault("id", folder.name)
        entries.append(manifest)
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


def list_snapshots(target: str | Path | None = None) -> list[dict]:
    """Newest-first snapshot manifests, optionally only those of one folder."""
    entries = _entries(snapshots_root())
    if target is None:
        return entries
    wanted = str(Path(target).resolve()).lower()
    return [
        item
        for item in entries
        if str(item.get("source") or "").lower() == wanted
    ]


def list_trash() -> list[dict]:
    return _entries(trash_root())


def purge(
    retention_days: int | None = None, *, now: datetime | None = None
) -> list[str]:
    """Remove snapshots older than the retention window.

    Safe to call repeatedly and opportunistically.  The trash area is never
    purged here: setting a folder aside is a user's undo, not a cache.
    """
    if retention_days is None:
        from apps.engine.settings import get_snapshot_retention_days

        retention_days = get_snapshot_retention_days()
    days = int(retention_days)
    if days < 1:
        raise ValueError("Keep previous versions for at least one day.")
    cutoff = (now or utcnow()) - timedelta(days=days)
    removed: list[str] = []
    root = safety_root() / SNAPSHOTS_DIR_NAME
    if not root.exists():
        return removed
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        manifest = _read_manifest(folder) or {}
        created = _parse_created(manifest)
        if created is None:
            try:
                created = datetime.fromtimestamp(folder.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
        if created >= cutoff:
            continue
        try:
            shutil.rmtree(folder)
        except OSError:
            continue
        removed.append(folder.name)
    return removed


def daily_snapshot_done(*, now: datetime | None = None) -> bool:
    """True when the full packs-root snapshot for this day already exists."""
    today = (now or utcnow()).astimezone(timezone.utc).date()
    for item in list_snapshots():
        if str(item.get("reason") or "") != DAILY_REASON:
            continue
        created = _parse_created(item)
        if created is not None and created.astimezone(timezone.utc).date() == today:
            return True
    return False


def ensure_daily_snapshot(*, now: datetime | None = None) -> dict | None:
    """Snapshot the whole packs root at most once a day; ``None`` when already done."""
    if daily_snapshot_done(now=now):
        return None
    return snapshot(packs_root(), reason=DAILY_REASON, now=now)


def trash(
    path: str | Path,
    *,
    reason: str = "manual",
    now: datetime | None = None,
) -> dict:
    """Move a folder into the trash area, keeping a manifest of where it came from."""
    source = _guard_source(Path(path))
    if _is_empty(source):
        raise ValueError("That folder is empty, so there is nothing to set aside.")
    when = now or utcnow()
    names, total = _folder_report(source)
    folder = trash_root() / _new_id(when)
    folder.mkdir(parents=True, exist_ok=False)
    content = folder / CONTENT_DIR_NAME
    try:
        shutil.move(str(source), str(content))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    manifest = {
        "kind": "trash",
        "id": folder.name,
        "created_at": when.isoformat(),
        "reason": str(reason or "manual"),
        "source": str(source),
        "file_count": len(names),
        "byte_count": total,
        "files": names,
    }
    try:
        _write_manifest(folder, manifest)
    except BaseException:
        try:
            shutil.move(str(content), str(source))
        except OSError:
            pass
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return manifest


def restore_from_trash(entry_id: str, *, now: datetime | None = None) -> dict:
    """Put a folder from the trash back where it came from."""
    ident = _valid_id(entry_id)
    folder = trash_root() / ident
    manifest = _read_manifest(folder)
    if manifest is None:
        raise ValueError("That folder is not in the trash.")
    content = folder / CONTENT_DIR_NAME
    if not content.is_dir():
        raise ValueError("That folder has already been put back.")
    target = Path(str(manifest.get("source") or ""))
    if not str(target):
        raise ValueError("The original location of that folder was not recorded.")
    if target.exists():
        if not target.is_dir() or not _is_empty(target):
            raise ValueError(
                f"{target.name} is back in place already, so this copy was left in the trash."
            )
        target.rmdir()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(content), str(target))
    restored_at = (now or utcnow()).isoformat()
    manifest["restored_at"] = restored_at
    try:
        _write_manifest(folder, manifest)
    except OSError:
        pass
    return {
        "id": ident,
        "path": str(target),
        "restored_at": restored_at,
        "file_count": manifest.get("file_count"),
    }


def _swap_in(content: Path, target: Path) -> None:
    """Replace ``target`` with a copy of ``content`` without ever half-writing it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".ca_unpacker_restore_{uuid.uuid4().hex}"
    hold = target.parent / f".ca_unpacker_previous_{uuid.uuid4().hex}"
    try:
        shutil.copytree(content, staging)
        if target.exists():
            target.rename(hold)
        try:
            staging.rename(target)
        except BaseException:
            if hold.exists():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                hold.rename(target)
            raise
        if hold.exists():
            shutil.rmtree(hold, ignore_errors=True)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _set_aside(target: Path) -> bool:
    """Move a half-written folder into the trash (never delete it outright)."""
    if not target.exists():
        return True
    try:
        trash(target, reason="failed-restore")
        return True
    except (OSError, ValueError):
        return False


def _put_back(previous: dict | None, target: Path) -> bool:
    """Return ``target`` to its pre-restore state; True when that worked."""
    if previous is None:
        return _set_aside(target)
    try:
        content = snapshots_root() / str(previous["id"]) / CONTENT_DIR_NAME
        if not content.is_dir():
            return False
        _swap_in(content, target)
    except OSError:
        return False
    return True


def restore_snapshot(
    snapshot_id: str,
    target: str | Path,
    *,
    now: datetime | None = None,
    protect_current: bool = True,
) -> dict:
    """Roll a pack folder back to a snapshot, transactionally.

    A snapshot of the live folder is taken first.  If the restore fails part way
    the live folder is returned to that pre-restore state and an error is
    raised, so the user always keeps whichever pack they had.

    ``protect_current=False`` is for callers that are undoing their own failed
    run: the live folder is then a half-written pack with nothing worth keeping.
    """
    ident = _valid_id(snapshot_id)
    folder = snapshots_root() / ident
    manifest = _read_manifest(folder)
    if manifest is None:
        raise ValueError("That version was not found.")
    content = folder / CONTENT_DIR_NAME
    if not content.is_dir():
        raise ValueError("That version is incomplete and cannot be restored.")
    destination = Path(target)
    previous = (
        snapshot(destination, reason=f"before-restore:{ident}", now=now)
        if protect_current
        else None
    )
    try:
        _swap_in(content, destination)
    except BaseException as exc:
        if previous is not None and _put_back(previous, destination):
            raise ValueError(
                "That version could not be restored. The folder was put back the way it was."
            ) from exc
        _set_aside(destination)
        raise ValueError(
            "That version could not be restored. Your earlier copy is still saved under "
            "previous versions."
        ) from exc
    return {
        "id": ident,
        "path": str(destination),
        "restored_at": (now or utcnow()).isoformat(),
        "pre_restore_snapshot_id": previous["id"] if previous else None,
    }
