from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Mapping, Sequence

from apps.engine.db import utcnow


class FileOutcome(str, Enum):
    PROCESSED = "processed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    UNCLASSIFIED = "unclassified"


TERMINAL_FILE_OUTCOMES = frozenset(outcome.value for outcome in FileOutcome)

_PARSERS: dict[str, tuple[str, str]] = {
    "bank": ("bank_pdf", "1"),
    "invoice": ("invoice", "1"),
    "gstr_1": ("gstr", "1"),
    "gstr_2b": ("gstr", "1"),
    "gstr_3b": ("gstr", "1"),
    "tally": ("tally", "1"),
    "zoho": ("zoho", "1"),
}


@dataclass(frozen=True)
class FileOutcomeResult:
    outcome: FileOutcome
    reason_code: str
    reason_message: str
    row_count: int = 0
    warnings: tuple[str, ...] = ()
    parser_id: str | None = None
    parser_version: str | None = None


def evaluate_file_outcome(
    *,
    kind: str,
    rows: Sequence[Mapping],
    parser_metadata: Mapping | None,
    classification_reason: str = "",
) -> FileOutcomeResult:
    metadata = parser_metadata or {}
    if kind not in _PARSERS:
        if _password_required(classification_reason, metadata):
            return FileOutcomeResult(
                outcome=FileOutcome.NEEDS_REVIEW,
                reason_code="password_required",
                reason_message="This file needs a password before it can be processed.",
            )
        return FileOutcomeResult(
            outcome=FileOutcome.UNCLASSIFIED,
            reason_code="unknown_type",
            reason_message="The file type was not recognized.",
        )

    parser_id, parser_version = _PARSERS[kind]
    row_count = len(rows)
    warnings = _warnings(rows, metadata)
    if row_count:
        return FileOutcomeResult(
            outcome=FileOutcome.PROCESSED,
            reason_code="rows_extracted",
            reason_message=f"Extracted {row_count} row{'s' if row_count != 1 else ''}.",
            row_count=row_count,
            warnings=warnings,
            parser_id=parser_id,
            parser_version=parser_version,
        )
    if _password_required(classification_reason, metadata):
        return FileOutcomeResult(
            outcome=FileOutcome.NEEDS_REVIEW,
            reason_code="password_required",
            reason_message="This file needs a password before it can be processed.",
            warnings=warnings,
            parser_id=parser_id,
            parser_version=parser_version,
        )
    if metadata.get("valid_empty") is True:
        return FileOutcomeResult(
            outcome=FileOutcome.PROCESSED,
            reason_code="valid_empty",
            reason_message="The file is valid and contains no rows.",
            warnings=warnings,
            parser_id=parser_id,
            parser_version=parser_version,
        )
    return FileOutcomeResult(
        outcome=FileOutcome.NEEDS_REVIEW,
        reason_code="no_rows",
        reason_message="The file was recognized, but no rows could be extracted.",
        warnings=warnings,
        parser_id=parser_id,
        parser_version=parser_version,
    )


def failed_file_outcome(
    reason_code: str,
    reason_message: str,
    *,
    kind: str | None = None,
) -> FileOutcomeResult:
    parser_id, parser_version = _PARSERS.get(kind or "", (None, None))
    return FileOutcomeResult(
        outcome=FileOutcome.FAILED,
        reason_code=reason_code,
        reason_message=reason_message,
        parser_id=parser_id,
        parser_version=parser_version,
    )


def persist_file_outcome(
    stored_file,
    result: FileOutcomeResult,
    *,
    processed_at: datetime | None = None,
) -> None:
    stored_file.parse_outcome = result.outcome.value
    stored_file.parse_reason_code = result.reason_code
    stored_file.parse_reason_message = result.reason_message[:500]
    stored_file.parse_row_count = result.row_count
    stored_file.parse_warnings_json = json.dumps(list(result.warnings))
    stored_file.parser_id = result.parser_id
    stored_file.parser_version = result.parser_version
    stored_file.processed_at = processed_at or utcnow()


def derive_job_status(outcomes: Iterable[FileOutcome | str]) -> str:
    values = [FileOutcome(outcome) for outcome in outcomes]
    if values and all(outcome is FileOutcome.PROCESSED for outcome in values):
        return "done"
    if FileOutcome.PROCESSED in values:
        return "done_with_warnings"
    if FileOutcome.FAILED in values:
        return "failed"
    return "done_with_warnings"


def _password_required(classification_reason: str, metadata: Mapping) -> bool:
    if str(metadata.get("pdf_type") or "").strip().lower() == "encrypted":
        return True
    texts = [classification_reason, metadata.get("error"), metadata.get("reason")]
    return any(
        "password" in str(text).lower() or "encrypted" in str(text).lower()
        for text in texts
        if text
    )


def _warnings(rows: Sequence[Mapping], metadata: Mapping) -> tuple[str, ...]:
    collected: list[str] = []
    raw_metadata = metadata.get("warnings") or []
    if isinstance(raw_metadata, str):
        raw_metadata = [raw_metadata]
    for warning in raw_metadata:
        _add_warning(collected, warning)
    for row in rows:
        raw = row.get("flags") or row.get("validation_flags") or []
        if isinstance(raw, str):
            raw = [raw]
        for warning in raw:
            _add_warning(collected, warning)
    return tuple(collected)


def _add_warning(collected: list[str], value) -> None:
    text = str(value).strip()
    if text and text not in collected:
        collected.append(text)
