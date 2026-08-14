from __future__ import annotations

import mimetypes
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apps.engine.classifier import classify_path
from apps.engine.db import Job, Period, StoredFile, get_session, utcnow
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.engine.library import files_root
from apps.engine.periods import get_period
from apps.engine.pipeline import parse_period_banks

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FOLDER_FILES = 400


def _file_dict(row: StoredFile) -> dict:
    kind = row.override_kind or row.detected_kind
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
        "classify_reason": row.classify_reason,
        "needs_review": kind == "unknown" and row.override_kind is None,
    }


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
        return {
            "id": job.id,
            "period_id": job.period_id,
            "status": job.status,
            "error_message": job.error_message,
            "files": [_file_dict(row) for row in files],
        }
    finally:
        session.close()


def collect_paths(raw_paths: list[str]) -> list[Path]:
    collected: list[Path] = []
    seen: set[str] = set()
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
                key = str(child.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(child)
                if len(collected) >= MAX_FOLDER_FILES:
                    return collected
            continue
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        collected.append(path)
    return collected


def start_job(period_id: int) -> dict:
    period = get_period(period_id)
    if period is None:
        raise ValueError("Period was not found.")
    session = get_session()
    try:
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

        to_copy = collect_paths(paths)
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
            if size > MAX_FILE_BYTES:
                reason = "file is larger than 100 MB"
            else:
                try:
                    shutil.copy2(source, dest)
                except OSError:
                    reason = "could not copy file into the library"
                    dest = None
                if dest is not None and dest.exists():
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
                storage_key=storage_key if dest is not None else "",
                detected_kind=kind,
                confidence=confidence,
                classify_reason=reason,
            )
            session.add(row)
            session.commit()

        job.status = "parsing"
        session.commit()
        period_id = period.id
        parse_period_banks(period_id, job_id)
        job = session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.finished_at = utcnow()
            session.commit()
        return get_job(job_id) or {"id": job_id, "status": "done", "files": []}
    except Exception as exc:
        try:
            job = session.get(Job, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
        except Exception:
            pass
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
        period_id = row.period_id
        session.commit()
        session.refresh(row)
        result = _file_dict(row)
        session.close()
        session = None
        parse_period_banks(period_id)
        return result
    finally:
        if session is not None:
            session.close()
