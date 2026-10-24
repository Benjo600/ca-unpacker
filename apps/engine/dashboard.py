from __future__ import annotations

from datetime import datetime, timezone

from apps.engine.db import Client, Job, Period, StoredFile, get_session
from apps.engine.kinds import KIND_LABELS
from apps.engine.recon_workflows import (
    latest_reconciliation_summary,
    reconciliation_workspace,
)

_ATTENTION_OUTCOMES = {"needs_review", "failed", "unclassified"}
_RECENT_LIMIT = 8


def _outcome_counts(files: list[StoredFile]) -> dict[str, int]:
    counts = {
        "processed": 0,
        "needs_review": 0,
        "failed": 0,
        "unclassified": 0,
    }
    for row in files:
        outcome = row.parse_outcome or "unclassified"
        if outcome not in counts:
            outcome = "unclassified"
        counts[outcome] += 1
    return counts


def _effective_kind(row: StoredFile) -> str:
    return row.override_kind or row.detected_kind or "unknown"


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def get_dashboard() -> dict:
    session = get_session()
    try:
        clients = session.query(Client).order_by(Client.name.asc()).all()
        periods = session.query(Period).order_by(Period.id.asc()).all()
        files = session.query(StoredFile).order_by(StoredFile.id.asc()).all()
        recent_jobs = (
            session.query(Job, Period, Client)
            .join(Period, Job.period_id == Period.id)
            .join(Client, Job.client_id == Client.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(_RECENT_LIMIT)
            .all()
        )
        job_files: dict[int, dict[str, int]] = {}
        for row in files:
            bucket = job_files.setdefault(
                row.job_id,
                {
                    "processed": 0,
                    "needs_review": 0,
                    "failed": 0,
                    "unclassified": 0,
                },
            )
            outcome = row.parse_outcome or "unclassified"
            if outcome not in bucket:
                outcome = "unclassified"
            bucket[outcome] += 1

        period_map = {
            period.id: {
                "label": period.label,
                "client_id": period.client_id,
            }
            for period in periods
        }
        client_map = {client.id: client.name for client in clients}
        outcome_counts = _outcome_counts(files)
        kind_counts: dict[str, dict] = {}
        for row in files:
            kind = _effective_kind(row)
            bucket = kind_counts.setdefault(
                kind,
                {
                    "kind": kind,
                    "label": KIND_LABELS.get(kind, kind),
                    "count": 0,
                    "processed": 0,
                    "needs_review": 0,
                    "failed": 0,
                    "unclassified": 0,
                },
            )
            outcome = row.parse_outcome or "unclassified"
            if outcome not in {"processed", "needs_review", "failed", "unclassified"}:
                outcome = "unclassified"
            bucket["count"] += 1
            bucket[outcome] += 1

        attention = []
        for row in sorted(
            (item for item in files if (item.parse_outcome or "") in _ATTENTION_OUTCOMES),
            key=lambda item: item.processed_at or item.created_at,
            reverse=True,
        )[:_RECENT_LIMIT]:
            period = period_map.get(row.period_id) or {}
            attention.append(
                {
                    "file_id": row.id,
                    "period_id": row.period_id,
                    "period_label": period.get("label") or "",
                    "client_name": client_map.get(period.get("client_id")) or "",
                    "file_name": row.original_name,
                    "kind": _effective_kind(row),
                    "kind_label": KIND_LABELS.get(_effective_kind(row), _effective_kind(row)),
                    "outcome": row.parse_outcome or "unclassified",
                    "reason": row.parse_reason_message
                    or row.classify_reason
                    or "Needs review.",
                }
            )

        activity = []
        for job, period, client in recent_jobs:
            counts = job_files.get(
                job.id,
                {
                    "processed": 0,
                    "needs_review": 0,
                    "failed": 0,
                    "unclassified": 0,
                },
            )
            activity.append(
                {
                    "job_id": job.id,
                    "period_id": period.id,
                    "period_label": period.label,
                    "client_name": client.name,
                    "status": job.status,
                    "files": sum(counts.values()),
                    "processed": counts["processed"],
                    "needs_review": counts["needs_review"],
                    "failed": counts["failed"],
                    "unclassified": counts["unclassified"],
                    "created_at": _iso(job.created_at),
                    "finished_at": _iso(job.finished_at),
                    "error_message": job.error_message or "",
                }
            )

        total_rows = sum(
            int(getattr(row, "parse_row_count", 0) or 0) for row in files
        )
    finally:
        session.close()

    workspace = reconciliation_workspace()
    latest_reconciliation = latest_reconciliation_summary(workspace)
    ready_periods = sum(
        1 for period in workspace.get("periods") or [] if period.get("has_comparison")
    )

    document_types = sorted(
        kind_counts.values(),
        key=lambda item: (-item["count"], item["label"]),
    )
    attention_total = (
        outcome_counts["needs_review"]
        + outcome_counts["failed"]
        + outcome_counts["unclassified"]
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "clients": len(clients),
            "periods": len(periods),
            "documents": len(files),
            "rows_extracted": total_rows,
            "processed": outcome_counts["processed"],
            "needs_review": outcome_counts["needs_review"],
            "failed": outcome_counts["failed"],
            "unclassified": outcome_counts["unclassified"],
            "attention": attention_total,
            "recon_ready_periods": ready_periods,
        },
        "status_counts": outcome_counts,
        "document_types": document_types,
        "recent_activity": activity,
        "attention": attention,
        "latest_reconciliation": latest_reconciliation,
        "periods": [
            {
                "id": period["id"],
                "label": period["label"],
                "client_id": period["client_id"],
                "client_name": period["client_name"],
                "has_comparison": period.get("has_comparison", False),
            }
            for period in workspace.get("periods") or []
        ],
    }
