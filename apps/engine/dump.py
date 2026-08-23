from __future__ import annotations

import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from apps.engine.classifier import classify_path
from apps.engine.db import Job, Period, StoredFile, get_session, utcnow
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.engine.library import files_root
from apps.engine.pdf_passwords import redact_known_passwords
from apps.engine.periods import get_period
from apps.engine.pipeline import parse_period_banks

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FOLDER_FILES = 400
TRUNCATION_WARNING = "This folder had more than 400 files. Only the first 400 were imported."
_ACTIVE_JOB_STATUSES = ("queued", "routing", "parsing")


def _file_dict(row: StoredFile) -> dict:
    kind = row.override_kind or row.detected_kind
    reason = row.classify_reason or ""
    reason_l = reason.lower()
    parse_failed = reason_l.startswith("could not parse") or "no rows extracted" in reason_l
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
        "needs_review": kind == "unknown" and row.override_kind is None,
        "needs_password": "password" in reason.lower(),
        "parse_failed": parse_failed,
    }


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
            .filter(StoredFile.job_id == job_id)
            .order_by(StoredFile.id.asc())
            .all()
        )
        file_dicts = [_file_dict(row) for row in files]
        extra = []
        if (job.error_message or "") == TRUNCATION_WARNING:
            extra.append(TRUNCATION_WARNING)
        return {
            "id": job.id,
            "period_id": job.period_id,
            "status": job.status,
            "error_message": job.error_message,
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
                if child.name.startswith("."):
                    continue
                if "__macosx" in {part.lower() for part in child.parts}:
                    continue
                if take(child):
                    return collected, True
            continue
        if take(path):
            return collected, True
    return collected, truncated


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
        if job is None or job.status in {"done", "failed"}:
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

        job.status = "routing"
        session.commit()

        to_copy, truncated = collect_inbox(paths)
        if truncated:
            job.error_message = TRUNCATION_WARNING
            session.commit()
        dest_root = files_root() / str(period.client_id) / str(period.id)
        dest_root.mkdir(parents=True, exist_ok=True)

        for source in to_copy:
            size = source.stat().st_size
            key_name = f"{uuid.uuid4().hex[:8]}_{_safe_name(source.name)}"
            storage_key = f"{period.client_id}/{period.id}/{key_name}"
            dest = dest_root / key_name

            reason = ""
            kind = "unknown"
            confidence = 0.0
            copied = False
            if size > MAX_FILE_BYTES:
                reason = "file is larger than 100 MB"
            else:
                try:
                    shutil.copy2(source, dest)
                    copied = dest.is_file()
                except OSError:
                    reason = "could not copy file into the library"
                if copied:
                    result = classify_path(dest)
                    kind = result.kind
                    confidence = result.confidence
                    reason = result.reason

            mime, _ = mimetypes.guess_type(source.name)
            row = StoredFile(
                job_id=job.id,
                period_id=period.id,
                original_name=source.name,
                mime=mime,
                size=size,
                storage_key=storage_key if copied else "",
                detected_kind=kind,
                confidence=confidence,
                classify_reason=reason,
            )
            session.add(row)
            session.commit()

        job.status = "parsing"
        session.commit()
        period_id = period.id
        had_bank = any(
            (stored.override_kind or stored.detected_kind) == "bank"
            for stored in session.query(StoredFile).filter(StoredFile.job_id == job_id)
        )
        parse_period_banks(period_id, job_id)
        if had_bank:
            from apps.engine.pipeline import get_period_pack

            pack = get_period_pack(period_id)
            outputs = (pack or {}).get("outputs") or []
            if not any(item.get("key") == "bank" for item in outputs):
                fail_job(job_id, "Bank statement was found but no Excel pack was written.")
                payload = get_job(job_id) or {
                    "id": job_id,
                    "status": "failed",
                    "files": [],
                    "warnings": [],
                }
                if truncated:
                    warnings = list(payload.get("warnings") or [])
                    if TRUNCATION_WARNING not in warnings:
                        warnings.append(TRUNCATION_WARNING)
                    payload["warnings"] = warnings
                return payload
        job = session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.finished_at = utcnow()
            if truncated:
                job.error_message = TRUNCATION_WARNING
            session.commit()
        return get_job(job_id) or {
            "id": job_id,
            "status": "done",
            "files": [],
            "warnings": [TRUNCATION_WARNING] if truncated else [],
        }
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
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
            job.status = "done"
            job.finished_at = utcnow()
            session.commit()
        return get_job(job_id) or {
            "id": job_id,
            "period_id": period_id,
            "status": "done",
            "files": [],
            "warnings": [],
        }
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        fail_job(job_id, _user_job_error(exc))
        raise
    finally:
        session.close()
