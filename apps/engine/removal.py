from __future__ import annotations

from pathlib import Path

from apps.engine.db import Client, ExtractedRow, Job, Period, StoredFile, get_session
from apps.engine.dump import reparse_period
from apps.engine.library import init_library, resolve_storage_key
from apps.engine.periods import get_period
from apps.engine.pipeline import get_period_pack
from apps.engine.settings import period_output_dir

# A period that is mid-run must not be mutated underneath the parser.
_ACTIVE_JOB_STATUSES = ("queued", "routing", "parsing")


class FileRemovalError(ValueError):
    """Raised when one file cannot be removed without risking other data."""


def _snapshot(row: StoredFile) -> dict:
    """Capture every column so the row can be rebuilt if the rebuild fails."""
    return {column.name: getattr(row, column.name) for column in StoredFile.__table__.columns}


def _active_job(period_id: int) -> bool:
    session = get_session()
    try:
        return (
            session.query(Job)
            .filter(Job.period_id == period_id, Job.status.in_(_ACTIVE_JOB_STATUSES))
            .first()
            is not None
        )
    finally:
        session.close()


def _blob_path(snapshot: dict) -> Path | None:
    key = str(snapshot.get("storage_key") or "")
    if not key:
        return None
    return resolve_storage_key(key)


def _move_blob_aside(blob: Path | None) -> Path | None:
    """Park the stored copy next to itself so it can be put back on failure."""
    if blob is None or not blob.exists():
        return None
    backup = blob.with_name(blob.name + ".removing")
    try:
        backup.unlink(missing_ok=True)
        blob.replace(backup)
    except OSError as exc:
        raise FileRemovalError(
            "Could not remove this file because its stored copy is in use. "
            "Close it in Excel or another app and try again."
        ) from exc
    return backup


def _discard_backup(backup: Path | None) -> None:
    if backup is None:
        return
    try:
        backup.unlink(missing_ok=True)
    except OSError:
        pass


def _restore_backup(blob: Path | None, backup: Path | None) -> None:
    if backup is None or blob is None:
        return
    try:
        if not blob.exists():
            backup.replace(blob)
    except OSError:
        pass


def _delete_rows(file_id: int, period_id: int) -> None:
    session = get_session()
    try:
        session.query(ExtractedRow).filter(ExtractedRow.file_id == file_id).delete()
        row = session.get(StoredFile, file_id)
        if row is not None:
            session.delete(row)
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()


def _restore_row(snapshot: dict) -> None:
    session = get_session()
    try:
        if session.get(StoredFile, snapshot["id"]) is None:
            session.add(StoredFile(**snapshot))
            session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


def _purge_crop_cache(file_id: int) -> None:
    """Crops are cached by file id; drop only this file's crops."""
    folder = init_library() / "cache" / "crops"
    if not folder.exists():
        return
    for path in folder.glob(f"{file_id}_p*.png"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _prune_stale_outputs(period_id: int, outputs: list[dict]) -> list[str]:
    """Drop Excels this period no longer produces, so removed rows cannot linger."""
    session = get_session()
    try:
        period = session.get(Period, period_id)
        client = session.get(Client, period.client_id) if period else None
    finally:
        session.close()
    if period is None:
        return []
    dest_dir = period_output_dir(
        client.name if client else "Client",
        period.label if period else f"period-{period_id}",
    )
    keep = {
        Path(str(item.get("path") or "")).resolve()
        for item in outputs
        if str(item.get("path") or "")
    }
    removed: list[str] = []
    for path in dest_dir.glob("*.xlsx"):
        if path.resolve() in keep:
            continue
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            pass
    return removed


def remove_period_file(file_id: int) -> dict:
    """Remove exactly one file from its period and rebuild that period's pack.

    Only the selected file's row, extracted rows, stored copy, crops and the
    period's regenerated Excels are touched. Every other file and its data stay
    as they were. The pack is rebuilt from the remaining files, so no removed
    rows survive in the database or in the generated workbook.
    """
    session = get_session()
    try:
        row = session.get(StoredFile, int(file_id))
        if row is None:
            raise FileRemovalError("File was not found. It may already be removed.")
        snapshot = _snapshot(row)
    finally:
        session.close()

    period_id = int(snapshot["period_id"])
    if get_period(period_id) is None:
        raise FileRemovalError("Period was not found.")
    if _active_job(period_id):
        raise FileRemovalError(
            "This period is still being processed. Wait for it to finish, then remove the file."
        )

    blob = _blob_path(snapshot)
    backup = _move_blob_aside(blob)

    try:
        _delete_rows(int(snapshot["id"]), period_id)
        job = reparse_period(period_id)
    except Exception as exc:
        # Put the file back before reporting the failure.
        _restore_backup(blob, backup)
        _restore_row(snapshot)
        try:
            reparse_period(period_id)
        except Exception:
            pass
        raise FileRemovalError(
            "Could not remove this file. Nothing was changed."
        ) from exc

    _discard_backup(backup)
    _purge_crop_cache(int(snapshot["id"]))

    pack = get_period_pack(period_id)
    pruned = _prune_stale_outputs(period_id, (pack or {}).get("outputs") or [])

    return {
        "file_id": int(snapshot["id"]),
        "period_id": period_id,
        "original_name": snapshot.get("original_name"),
        "job": job,
        "pruned_outputs": pruned,
    }
