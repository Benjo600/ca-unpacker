from __future__ import annotations

import json
import mimetypes
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from apps.engine.classifier import classify_path
from apps.engine.db import Job, Period, StoredFile, get_session, utcnow
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.engine.library import files_root
from apps.engine.outcomes import derive_job_status, failed_file_outcome, persist_file_outcome
from apps.engine.pdf_passwords import redact_known_passwords
from apps.engine.periods import get_period
from apps.engine.pipeline import parse_period_banks

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FOLDER_FILES = 400
TRUNCATION_WARNING = "This folder had more than 400 files. Only the first 400 were imported."
_SKIP_NAMES = {"readme.md", "readme.txt", "thumbs.db", "desktop.ini"}
_ACTIVE_JOB_STATUSES = ("queued", "routing", "parsing")
_FILE_OUTCOMES = ("processed", "needs_review", "failed", "unclassified")


@dataclass(frozen=True)
class IntakePreflight:
    paths: list[Path]
    discovered_count: int
    accepted_count: int


def _file_dict(row: StoredFile) -> dict:
    kind = row.override_kind or row.detected_kind
    reason = row.classify_reason or ""
    reason_l = reason.lower()
    parse_outcome = getattr(row, "parse_outcome", "unclassified")
    try:
        parse_warnings = json.loads(getattr(row, "parse_warnings_json", "[]") or "[]")
    except (TypeError, ValueError):
        parse_warnings = []
    processed_at = getattr(row, "processed_at", None)
    parse_failed = (
        parse_outcome == "failed"
        or getattr(row, "parse_reason_code", None) in {"parser_error", "no_rows"}
        or reason_l.startswith("could not parse")
        or "no rows extracted" in reason_l
        or "no line items" in reason_l
        or "unreadable" in reason_l
    )
    return {
        "id": row.id,
        "job_id": row.job_id,
        "period_id": row.period_id,
        "original_name": row.original_name,
        "size": row.size,
        "storage_key": row.storage_key,
        "detected_kind": row.detected_kind,
        "override_kind": row.override_kind,
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "confidence": row.confidence,
        "classify_reason": reason,
        "parse_outcome": parse_outcome,
        "parse_reason_code": getattr(row, "parse_reason_code", None),
        "parse_reason_message": getattr(row, "parse_reason_message", None),
        "parse_row_count": getattr(row, "parse_row_count", 0),
        "parse_warnings": parse_warnings if isinstance(parse_warnings, list) else [],
        "parser_id": getattr(row, "parser_id", None),
        "parser_version": getattr(row, "parser_version", None),
        "processed_at": processed_at.isoformat() if processed_at else None,
        "needs_review": parse_outcome == "needs_review"
        or parse_failed
        or (parse_outcome == "unclassified" and kind == "unknown")
        or (kind == "unknown" and row.override_kind is None),
        "needs_password": getattr(row, "parse_reason_code", None) == "password_required"
        or "password" in reason_l,
        "parse_failed": parse_failed,
    }


def _outcome_counts(rows: list[StoredFile]) -> dict[str, int]:
    """Return the complete, stable set of terminal file-outcome totals."""
    counts = {outcome: 0 for outcome in _FILE_OUTCOMES}
    for row in rows:
        outcome = getattr(row, "parse_outcome", "unclassified")
        counts[outcome if outcome in counts else "unclassified"] += 1
    return counts


def _warnings_from_files(file_dicts: list[dict], extra: list[str] | None = None) -> list[str]:
    warnings = [
        f"{item['original_name']}: {item['classify_reason']}"
        for item in file_dicts
        if item.get("parse_failed")
    ]
    if extra:
        for message in extra:
            if message and message not in warnings:
                warnings.append(message)
    return warnings


def list_period_files(period_id: int) -> list[dict]:
    session = get_session()
    try:
        rows = (
            session.query(StoredFile)
            .filter(StoredFile.period_id == period_id)
            .order_by(StoredFile.created_at.asc())
            .all()
        )
        return [_file_dict(row) for row in rows]
    finally:
        session.close()


def get_job(job_id: int) -> dict | None:
    session = get_session()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return None
        files = (
            session.query(StoredFile)
            .filter(StoredFile.period_id == job.period_id)
            .order_by(StoredFile.id.asc())
            .all()
        )
        file_dicts = [_file_dict(row) for row in files]
        extra = []
        if (job.error_message or "") == TRUNCATION_WARNING:
            extra.append(TRUNCATION_WARNING)
        return {
            "api_version": 1,
            "summary_scope": "period",
            "id": job.id,
            "period_id": job.period_id,
            "status": job.status,
            "error_message": job.error_message,
            "intake_discovered_count": job.intake_discovered_count,
            "intake_accepted_count": job.intake_accepted_count,
            "outcome_counts": _outcome_counts(files),
            "files": file_dicts,
            "warnings": _warnings_from_files(file_dicts, extra),
        }
    finally:
        session.close()


def collect_inbox(raw_paths: list[str]) -> tuple[list[Path], bool]:
    collected: list[Path] = []
    seen: set[str] = set()
    truncated = False

    def take(file_path: Path) -> bool:
        nonlocal truncated
        if file_path.name.startswith("."):
            return False
        if file_path.name.lower() in _SKIP_NAMES:
            return False
        if "__macosx" in {part.lower() for part in file_path.parts}:
            return False
        key = str(file_path.resolve()).lower()
        if key in seen:
            return False
        seen.add(key)
        if len(collected) >= MAX_FOLDER_FILES:
            truncated = True
            return True
        collected.append(file_path)
        return False

    for raw in raw_paths:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                if take(child):
                    return collected, True
            continue
        if take(path):
            return collected, True
    return collected, truncated


def preflight_paths(raw_paths: list[str]) -> IntakePreflight:
    collected: list[Path] = []
    seen: set[str] = set()
    discovered_count = 0

    def reject_legacy_xls(path: Path) -> None:
        if path.suffix.lower() == ".xls":
            raise ValueError(
                "Legacy .xls files are not supported. Export the file as .xlsx or .csv and try again."
            )

    def add_path(path: Path) -> None:
        nonlocal discovered_count
        if path.name.startswith("."):
            return
        if path.name.lower() in _SKIP_NAMES:
            return
        if "__macosx" in {part.lower() for part in path.parts}:
            return
        discovered_count += 1
        key = str(path.resolve()).lower()
        if key in seen:
            return
        seen.add(key)
        reject_legacy_xls(path)
        collected.append(path)
        if len(collected) > MAX_FOLDER_FILES:
            raise ValueError(f"Choose at most {MAX_FOLDER_FILES} files at a time.")

    for raw in raw_paths:
        path = Path(raw)
        if not path.exists():
            raise ValueError(f"Selected path no longer exists: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*"), key=lambda item: str(item).lower()):
                if not child.is_file():
                    continue
                add_path(child)
            continue
        if not path.is_file():
            raise ValueError(f"Selected path is not a regular file or folder: {path}")
        reject_legacy_xls(path)
        add_path(path)
    return IntakePreflight(
        paths=collected,
        discovered_count=discovered_count,
        accepted_count=len(collected),
    )


def collect_paths(raw_paths: list[str]) -> list[Path]:
    return collect_inbox(raw_paths)[0]


def _user_job_error(exc: BaseException) -> str:
    if isinstance(exc, ValueError):
        text = str(exc).strip() or "Something went wrong with this dump."
    elif isinstance(exc, OSError):
        text = "Could not read or write a file for this dump."
    else:
        raw = str(exc).strip()
        if (not raw) or "traceback (most recent call last)" in raw.lower() or raw.count("\n") > 2:
            text = "Could not process these files."
        else:
            text = raw.splitlines()[0]
    return redact_known_passwords(text)[:500]


def fail_job(job_id: int, message: str) -> None:
    session = get_session()
    try:
        job = session.get(Job, job_id)
        if job is None or job.status in {"done", "done_with_warnings", "failed"}:
            return
        job.status = "failed"
        job.error_message = redact_known_passwords(message or "Could not process these files.")[:500]
        job.finished_at = utcnow()
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


def start_job(period_id: int) -> dict:
    period = get_period(period_id)
    if period is None:
        raise ValueError("Period was not found.")
    session = get_session()
    try:
        active = (
            session.query(Job)
            .filter(Job.period_id == period_id, Job.status.in_(_ACTIVE_JOB_STATUSES))
            .first()
        )
        if active is not None:
            raise ValueError("This period is already being processed. Wait for it to finish.")
        job = Job(
            client_id=period["client_id"],
            period_id=period_id,
            status="queued",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return {"id": job.id, "period_id": job.period_id, "status": job.status}
    finally:
        session.close()


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", name, flags=re.A).strip("._")
    return (cleaned or "file")[:120]


def ingest_paths(job_id: int, paths: list[str]) -> dict:
    session = get_session()
    try:
        job = session.get(Job, job_id)
        if job is None:
            raise ValueError("Job was not found.")
        period = session.get(Period, job.period_id)
        if period is None:
            raise ValueError("Period was not found.")

        preflight = preflight_paths(paths)
        to_copy = preflight.paths
        job.status = "routing"
        job.intake_discovered_count = preflight.discovered_count
        job.intake_accepted_count = preflight.accepted_count
        manifest: list[tuple[Path, StoredFile]] = []
        for source in to_copy:
            mime, _ = mimetypes.guess_type(source.name)
            row = StoredFile(
                job_id=job.id,
                period_id=period.id,
                original_name=source.name,
                mime=mime,
                size=0,
                storage_key="",
                detected_kind="unknown",
                confidence=0.0,
                classify_reason="",
            )
            session.add(row)
            manifest.append((source, row))
        session.commit()
        dest_root = files_root() / str(period.client_id) / str(period.id)
        dest_root.mkdir(parents=True, exist_ok=True)

        for source, row in manifest:
            try:
                size = source.stat().st_size
            except OSError:
                row.classify_reason = "source file could not be read"
                persist_file_outcome(
                    row,
                    failed_file_outcome(
                        "source_missing", "The source file could not be read."
                    ),
                )
                session.commit()
                continue

            row.size = size
            if size > MAX_FILE_BYTES:
                row.classify_reason = "file is larger than 100 MB"
                persist_file_outcome(
                    row,
                    failed_file_outcome(
                        "copy_failed", "The file could not be copied into the library."
                    ),
                )
                session.commit()
                continue

            key_name = f"{uuid.uuid4().hex[:8]}_{_safe_name(source.name)}"
            row.storage_key = f"{period.client_id}/{period.id}/{key_name}"
            dest = dest_root / key_name
            session.commit()
            try:
                shutil.copy2(source, dest)
                copied = dest.is_file()
            except OSError:
                copied = False
            if not copied:
                row.storage_key = ""
                row.classify_reason = "could not copy file into the library"
                persist_file_outcome(
                    row,
                    failed_file_outcome(
                        "copy_failed", "The file could not be copied into the library."
                    ),
                )
                session.commit()
                continue

            result = classify_path(dest)
            row.detected_kind = result.kind
            row.confidence = result.confidence
            row.classify_reason = result.reason
            session.commit()

        job.status = "parsing"
        session.commit()
        period_id = period.id
        parse_period_banks(period_id, job_id)
        job = session.get(Job, job_id)
        if job is not None:
            job.status = _period_job_status(session, period_id)
            job.error_message = (
                "No files could be processed."
                if job.status == "failed"
                else None
            )
            job.finished_at = utcnow()
            session.commit()
        return get_job(job_id) or {"id": job_id, "status": "done", "files": []}
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        _mark_unfinished_files_failed(session, job_id)
        fail_job(job_id, _user_job_error(exc))
        raise
    finally:
        session.close()


def override_kind(file_id: int, kind: str) -> dict:
    if kind not in KINDS:
        raise ValueError("That is not a known file type.")
    session = get_session()
    try:
        row = session.get(StoredFile, file_id)
        if row is None:
            raise ValueError("File was not found.")
        row.override_kind = None if kind == row.detected_kind else kind
        if kind != "unknown":
            row.classify_reason = f"manually set to {KIND_LABELS[kind]}"
        session.commit()
        session.refresh(row)
        return _file_dict(row)
    finally:
        session.close()


def reparse_period(period_id: int, job_id: int | None = None) -> dict:
    if job_id is None:
        started = start_job(period_id)
        job_id = started["id"]
    elif get_period(period_id) is None:
        raise ValueError("Period was not found.")

    session = get_session()
    try:
        job = session.get(Job, job_id)
        if job is None:
            raise ValueError("Job was not found.")
        job.status = "parsing"
        session.commit()
        parse_period_banks(period_id, job_id)
        job = session.get(Job, job_id)
        if job is not None:
            job.status = _period_job_status(session, period_id)
            job.error_message = (
                "No files could be processed."
                if job.status == "failed"
                else None
            )
            job.finished_at = utcnow()
            session.commit()
        return get_job(job_id) or {
            "id": job_id,
            "period_id": period_id,
            "status": "done_with_warnings",
            "files": [],
        }
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        _mark_unfinished_files_failed(session, job_id)
        fail_job(job_id, _user_job_error(exc))
        raise
    finally:
        session.close()


def _period_job_status(session, period_id: int) -> str:
    session.expire_all()
    outcomes = [
        row.parse_outcome
        for row in session.query(StoredFile).filter(StoredFile.period_id == period_id)
    ]
    return derive_job_status(outcomes)


def _mark_unfinished_files_failed(session, job_id: int) -> None:
    try:
        session.expire_all()
        job = session.get(Job, job_id)
        if job is None:
            return
        rows = (
            session.query(StoredFile)
            .filter(
                StoredFile.job_id == job.id,
                StoredFile.processed_at.is_(None),
            )
            .all()
        )
        for row in rows:
            persist_file_outcome(
                row,
                failed_file_outcome(
                    "infrastructure_error",
                    "Processing could not finish because an internal service failed.",
                ),
            )
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
