from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.engine.classifier import classify_path
from apps.engine.currency import currency_label, is_known
from apps.engine.db import Job, Period, StoredFile, get_session, utcnow
from apps.engine.license import assert_can_ingest, record_ingested
from apps.engine.kinds import KIND_LABELS, KINDS
from apps.engine.library import files_root
from apps.engine.outcomes import derive_job_status, failed_file_outcome, persist_file_outcome
from apps.engine.pdf_passwords import redact_known_passwords
from apps.engine.periods import get_period
from apps.engine.pipeline import parse_period_banks
from apps.engine.preflight import load_report

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FOLDER_FILES = 400
TRUNCATION_WARNING = "This folder had more than 400 files. Only the first 400 were imported."
INTERRUPTED_MESSAGE = (
    "This period was interrupted before it finished. Add its files again, or "
    "use Retry to process what is already here."
)
STALE_JOB_MINUTES = 30
_SKIP_NAMES = {"readme.md", "readme.txt", "thumbs.db", "desktop.ini"}
_ACTIVE_JOB_STATUSES = ("queued", "routing", "parsing", "cancel_requested")
_FILE_OUTCOMES = ("processed", "needs_review", "failed", "unclassified")
_CANCEL_MESSAGE = "Processing was cancelled. Files already read were kept."


class JobCancelled(Exception):
    """Raised inside a job when the user asked to cancel it."""


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
    try:
        currency_candidates = json.loads(
            getattr(row, "currency_candidates_json", "[]") or "[]"
        )
    except (TypeError, ValueError):
        currency_candidates = []
    currency_code = getattr(row, "currency_code", None)
    currency_status = getattr(row, "currency_status", None)
    currency_source = getattr(row, "currency_source", None)
    currency_confidence = getattr(row, "currency_confidence", None)
    currency_override = getattr(row, "currency_override", None)
    effective_code = currency_override or currency_code
    effective_status = "confirmed" if currency_override else currency_status
    effective_source = "manual_override" if currency_override else currency_source
    effective_confidence = 1.0 if currency_override else currency_confidence
    currency_info = {
        "currency_code": effective_code,
        "currency_status": effective_status,
        "currency_source": effective_source,
        "currency_confidence": effective_confidence,
        "currency_candidates": currency_candidates
        if isinstance(currency_candidates, list)
        else [],
        "currency_override": currency_override,
        "currency_detected_code": currency_code,
        "currency_detected_status": currency_status,
        "currency_ambiguous": effective_status == "ambiguous",
    }
    currency_info["currency_label"] = currency_label(currency_info)
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
        "content_sha256": getattr(row, "content_sha256", None),
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
        **currency_info,
        "needs_review": parse_outcome == "needs_review"
        or parse_failed
        or (parse_outcome == "unclassified" and kind == "unknown")
        or (kind == "unknown" and row.override_kind is None),
        "needs_password": getattr(row, "parse_reason_code", None) == "password_required"
        or "password" in reason_l,
        "parse_failed": parse_failed,
        "duplicate_content": "duplicate content of" in reason_l,
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
        try:
            skipped_duplicates = json.loads(
                getattr(job, "intake_duplicate_names_json", "[]") or "[]"
            )
        except (TypeError, ValueError):
            skipped_duplicates = []
        if not isinstance(skipped_duplicates, list):
            skipped_duplicates = []
        report = load_report(job.period_id)
        return {
            "api_version": 1,
            "summary_scope": "period",
            "id": job.id,
            "period_id": job.period_id,
            "status": job.status,
            "error_message": job.error_message,
            "intake_discovered_count": job.intake_discovered_count,
            "intake_accepted_count": job.intake_accepted_count,
            "skipped_duplicates": skipped_duplicates,
            "outcome_counts": _outcome_counts(files),
            "files": file_dicts,
            "warnings": _warnings_from_files(file_dicts, extra),
            "preflight": report.to_dict() if report else None,
            "blocked": bool(report and report.blocked),
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
        if job is None or job.status in {"done", "done_with_warnings", "failed", "cancelled"}:
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


def cancel_job(job_id: int) -> dict:
    """Ask a running job to stop at the next file boundary.

    Cancellation is cooperative: the ingest/parse loops check the flag between
    files, so a page already being parsed finishes and its results are kept.
    """
    session = get_session()
    try:
        job = session.get(Job, job_id)
        if job is None:
            raise ValueError("Job was not found.")
        if job.status not in _ACTIVE_JOB_STATUSES:
            return {"id": job.id, "status": job.status, "cancelled": False}
        job.status = "cancel_requested"
        session.commit()
        return {"id": job.id, "status": job.status, "cancelled": True}
    finally:
        session.close()


def job_cancel_requested(job_id: int | None) -> bool:
    if not job_id:
        return False
    session = get_session()
    try:
        job = session.get(Job, int(job_id))
        return bool(job is not None and job.status == "cancel_requested")
    except Exception:
        return False
    finally:
        session.close()


def finish_cancelled_job(job_id: int) -> None:
    """Mark a cancelled job terminal, keeping files already processed."""
    session = get_session()
    try:
        job = session.get(Job, int(job_id))
        if job is None or job.status != "cancel_requested":
            return
        job.status = "cancelled"
        job.error_message = _CANCEL_MESSAGE
        job.finished_at = utcnow()
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _mark_interrupted(job: Job) -> None:
    job.status = "failed"
    job.error_message = INTERRUPTED_MESSAGE
    job.finished_at = utcnow()


def reconcile_interrupted_work(grace_minutes: int = 0) -> int:
    """Fail jobs left running by a crash or a restart.

    Only one process may write the library, so at startup every active job is
    orphaned - its thread died with the previous process. Left alone, such a job
    blocks the period forever with "already being processed".
    """
    session = get_session()
    if session is None:
        return 0
    failed = 0
    try:
        cutoff = _as_naive_utc(utcnow()) - timedelta(minutes=max(0, grace_minutes))
        active = (
            session.query(Job).filter(Job.status.in_(_ACTIVE_JOB_STATUSES)).all()
        )
        for job in active:
            created = _as_naive_utc(job.created_at)
            if created is not None and created > cutoff:
                continue
            _mark_interrupted(job)
            failed += 1
        if failed:
            session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return 0
    finally:
        session.close()
    return failed


def _fail_stale_jobs(session, period_id: int) -> None:
    """Free a period whose active job is older than the stale threshold."""
    cutoff = _as_naive_utc(utcnow()) - timedelta(minutes=STALE_JOB_MINUTES)
    active = (
        session.query(Job)
        .filter(Job.period_id == period_id, Job.status.in_(_ACTIVE_JOB_STATUSES))
        .all()
    )
    changed = False
    for job in active:
        created = _as_naive_utc(job.created_at)
        if created is not None and created > cutoff:
            continue
        _mark_interrupted(job)
        changed = True
    if changed:
        session.commit()


def start_job(period_id: int) -> dict:
    period = get_period(period_id)
    if period is None:
        raise ValueError("Period was not found.")
    session = get_session()
    try:
        _fail_stale_jobs(session, period_id)
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


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _existing_hashes(session, period_id: int) -> dict[str, str]:
    """Map content hash -> original name for files already in this period."""
    rows = (
        session.query(StoredFile.content_sha256, StoredFile.original_name)
        .filter(
            StoredFile.period_id == period_id,
            StoredFile.content_sha256.isnot(None),
            StoredFile.content_sha256 != "",
        )
        .all()
    )
    return {row[0]: row[1] for row in rows if row[0]}


def _split_already_present(
    sources: list[Path], present: dict[str, str]
) -> tuple[list[Path], list[dict]]:
    """Drop files whose bytes are already in the period.

    Re-dropping a client folder used to store every document a second time, so
    the pack counted the same bank lines and purchases twice.  Identical bytes
    in the same period are the same document, so they are skipped - and named
    in the import summary, never dropped silently.
    """
    unique: list[Path] = []
    skipped: list[dict] = []
    seen = dict(present)
    for source in sources:
        try:
            digest = _sha256_of(source)
        except OSError:
            # Unreadable sources keep their existing per-file failure path.
            unique.append(source)
            continue
        if digest in seen:
            skipped.append({"name": source.name, "of": seen[digest]})
            continue
        seen[digest] = source.name
        unique.append(source)
    return unique, skipped


def copy_verified(source: Path, dest: Path) -> tuple[str | None, str | None]:
    """Copy a file into the library, then verify and hash what was written.

    Returns ``(sha256_hex, error_message)``.  The hash and size check read the
    *destination* bytes, so the recorded hash always describes the copy the
    library will actually parse — not the source that may be mid-change.
    ``error_message`` is set on any failure and the partial file is removed.
    """
    try:
        shutil.copy2(source, dest)
    except OSError as exc:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return None, f"could not copy file into the library ({exc.__class__.__name__})"
    digest = hashlib.sha256()
    try:
        with open(dest, "rb") as reader:
            while True:
                chunk = reader.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        expected = source.stat().st_size
        copied = dest.stat().st_size
    except OSError:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return None, "could not verify the copied file"
    if expected is not None and copied != expected:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return None, (
            f"copy verification failed ({copied} of {expected} bytes); the source "
            "file may be changing on disk"
        )
    return digest.hexdigest(), None


def _find_duplicate_content(session, period_id: int, file_id: int, sha256: str | None):
    """Another file in this period with identical bytes, if any."""
    if not sha256:
        return None
    return (
        session.query(StoredFile)
        .filter(
            StoredFile.period_id == period_id,
            StoredFile.id != file_id,
            StoredFile.content_sha256 == sha256,
        )
        .first()
    )


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
        to_copy, already_present = _split_already_present(
            preflight.paths, _existing_hashes(session, period.id)
        )
        accepted_count = max(0, preflight.accepted_count - len(already_present))
        assert_can_ingest(accepted_count)
        # Re-read the row: a cancel request committed after this job started
        # must not be overwritten by the routine queued→routing transition.
        session.expire(job)
        session.refresh(job)
        if job.status == "cancel_requested":
            raise JobCancelled()
        job.status = "routing"
        job.intake_discovered_count = preflight.discovered_count
        job.intake_accepted_count = accepted_count
        job.intake_duplicate_names_json = json.dumps(already_present[:50])
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
            session.expire(job)
            session.refresh(job)
            if job.status == "cancel_requested":
                raise JobCancelled()
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
            sha256, copy_error = copy_verified(source, dest)
            if copy_error or sha256 is None:
                row.storage_key = ""
                row.classify_reason = copy_error or "could not copy file into the library"
                persist_file_outcome(
                    row,
                    failed_file_outcome(
                        "copy_failed", "The file could not be copied into the library."
                    ),
                )
                session.commit()
                continue
            row.content_sha256 = sha256

            duplicate = _find_duplicate_content(session, period.id, row.id, sha256)
            if duplicate is not None:
                # Never silently drop the file: ingest, parse and flag it so a
                # human can decide whether both copies belong in the register.
                row.classify_reason = (
                    f"duplicate content of {duplicate.original_name} (identical bytes)"
                )

            result = classify_path(dest)
            row.detected_kind = result.kind
            row.confidence = result.confidence
            if duplicate is not None:
                row.classify_reason = f"{row.classify_reason} · {result.reason}"[:300]
            else:
                row.classify_reason = result.reason
            session.commit()

        session.expire(job)
        session.refresh(job)
        if job.status == "cancel_requested":
            raise JobCancelled()
        job.status = "parsing"
        session.commit()
        period_id = period.id
        try:
            pack_result = parse_period_banks(period_id, job_id)
        except JobCancelled:
            finish_cancelled_job(job_id)
            raise
        job = session.get(Job, job_id)
        if job is not None:
            job.status = _period_job_status(session, period_id)
            job.error_message = _job_error_message(pack_result, job.status)
            job.finished_at = utcnow()
            session.commit()
        record_ingested(accepted_count)
        return get_job(job_id) or {"id": job_id, "status": "done", "files": []}
    except JobCancelled:
        try:
            session.rollback()
        except Exception:
            pass
        finish_cancelled_job(job_id)
        raise
    except JobCancelled:
        try:
            session.rollback()
        except Exception:
            pass
        finish_cancelled_job(job_id)
        raise
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


def set_file_currency(file_id: int, code: str | None) -> dict:
    """Set or clear a manual currency override for one source file.

    A statement with confirmed, explicit currency evidence cannot be relabelled
    to a different currency.  Ambiguous, unknown, or weakly inferred statements
    can be corrected by the user.  Amounts are never converted.
    """
    chosen = (code or "").strip().upper() or None
    if chosen is not None and not is_known(chosen):
        raise ValueError("That is not a known ISO currency code.")
    session = get_session()
    try:
        row = session.get(StoredFile, file_id)
        if row is None:
            raise ValueError("File was not found.")
        detected_code = (getattr(row, "currency_code", None) or "").upper() or None
        detected_status = getattr(row, "currency_status", None)
        if (
            chosen is not None
            and detected_status == "confirmed"
            and detected_code is not None
            and chosen != detected_code
        ):
            raise ValueError(
                f"This statement clearly shows {detected_code}. "
                f"A manual override to {chosen} would contradict the source file."
            )
        row.currency_override = chosen
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
        session.expire(job)
        session.refresh(job)
        if job.status == "cancel_requested":
            raise JobCancelled()
        job.status = "parsing"
        session.commit()
        try:
            pack_result = parse_period_banks(period_id, job_id)
        except JobCancelled:
            finish_cancelled_job(job_id)
            raise
        job = session.get(Job, job_id)
        if job is not None:
            job.status = _period_job_status(session, period_id)
            job.error_message = _job_error_message(pack_result, job.status)
            job.finished_at = utcnow()
            session.commit()
        return get_job(job_id) or {
            "id": job_id,
            "period_id": period_id,
            "status": "done_with_warnings",
            "files": [],
        }
    except JobCancelled:
        try:
            session.rollback()
        except Exception:
            pass
        finish_cancelled_job(job_id)
        raise
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


def _job_error_message(pack_result: dict | None, status: str) -> str | None:
    """A blocking pre-flight finding becomes the job's own message.

    The job status itself still comes from the per-file outcomes, so the
    existing job path (and the UI that reads it) does not change shape.
    """
    blocking = ((pack_result or {}).get("preflight") or {}).get("blocking") or []
    messages = [
        str(item.get("message") or "").strip()
        for item in blocking
        if isinstance(item, dict)
    ]
    messages = [message for message in messages if message]
    if messages:
        return redact_known_passwords(" ".join(messages))[:500]
    return "No files could be processed." if status == "failed" else None


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
