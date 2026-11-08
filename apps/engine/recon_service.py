"""Persistence, workflow orchestration and investigation services.

The matching algorithms live in :mod:`apps.engine.recon_engine`.  This module
owns database transactions, rule snapshots, run history, exceptions, manual
decisions and the audit trail.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import and_, func, or_, select

from apps.engine.db import (
    Client,
    ExtractedRow,
    Period,
    ReconAuditEvent,
    ReconException,
    ReconMatch,
    ReconRecordLink,
    ReconRuleSet,
    ReconRun,
    StoredFile,
    get_session,
)
from apps.engine.recon_datasets import (
    WORKFLOWS,
    WORKFLOW_BY_ID,
    dataset_payload,
    dataset_sources,
    datasets_for_period,
    financial_year,
    period_meta,
    workflow_definition,
)
from apps.engine.recon_engine import (
    CLASSIFICATION_LABELS,
    DEFAULT_RULES,
    ENGINE_VERSION,
    EXCEPTION_LABELS,
    STATUS_LABELS,
    compare_pair,
    match_dataset,
    normalise_rules,
    rule_summary,
)

RESOLVED_EXCEPTION_STATUSES = {
    "resolved",
    "approved",
    "timing_difference",
    "approved_adjustment",
    "closed",
}
OPEN_EXCEPTION_STATUSES = {"open", "investigating", "assigned", "reopened"}
EXCEPTION_STATUSES = (
    "open",
    "investigating",
    "assigned",
    "resolved",
    "approved",
    "timing_difference",
    "approved_adjustment",
    "reopened",
    "closed",
)
RUN_STATUSES = ("queued", "running", "completed", "failed", "cancelled")
MATCHED_STATUSES = {"matched", "accepted", "manual", "timing_difference", "approved_adjustment"}
PROPOSED_STATUSES = {"proposed"}
UNMATCHED_STATUSES = {"unmatched"}
DUPLICATE_STATUSES = {"duplicate"}
REVERSAL_STATUSES = {"reversal_candidate"}

_EXECUTION_LOCK = threading.RLock()
_RUN_THREADS: set[threading.Thread] = set()
_RUN_THREADS_LOCK = threading.Lock()
_CANCELLED_RUNS: set[int] = set()
_CANCELLED_LOCK = threading.Lock()


class ReconciliationCancelled(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_load(text: str | None, fallback):
    try:
        value = json.loads(text or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return value


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _actor(value: str | None) -> str:
    return str(value or "").strip() or "local user"


def _require_reason(value: str | None, action: str) -> str:
    reason = str(value or "").strip()
    if len(reason) < 3:
        raise ValueError(f"Record a reason before you {action}.")
    return reason


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decode(row: ReconMatch) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "ordinal": row.ordinal,
        "classification": row.classification,
        "classification_label": CLASSIFICATION_LABELS.get(
            row.classification, row.classification.replace("_", " ").title()
        ),
        "status": row.status,
        "status_label": STATUS_LABELS.get(row.status, row.status.replace("_", " ").title()),
        "match_type": row.match_type,
        "confidence": row.confidence,
        "requires_review": bool(row.requires_review),
        "reason_code": row.reason_code,
        "explanation": row.explanation,
        "matched_fields": _json_load(row.matched_fields_json, []),
        "differences": _json_load(row.differences_json, {}),
        "tolerances": _json_load(row.tolerances_json, []),
        "exception_categories": _json_load(row.exception_categories_json, []),
        "allocations": _json_load(row.allocations_json, []),
        "candidates": _json_load(row.candidates_json, []),
        "left": _json_load(row.left_records_json, []),
        "right": _json_load(row.right_records_json, []),
        "left_ids": _json_load(row.left_row_ids_json, []),
        "right_ids": _json_load(row.right_row_ids_json, []),
        "left_amount": row.left_amount,
        "right_amount": row.right_amount,
        "difference_amount": row.difference_amount,
        "currency": row.currency or "",
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_reason": row.decision_reason,
        "is_superseded": bool(row.is_superseded),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _decode_run(row: ReconRun) -> dict:
    return {
        "id": row.id,
        "run_uuid": row.run_uuid,
        "client_id": row.client_id,
        "client_name": row.client_name,
        "period_id": row.period_id,
        "period_label": row.period_label,
        "financial_year": row.financial_year,
        "workflow_id": row.workflow_id,
        "workflow_label": row.workflow_label,
        "status": row.status,
        "completion_status": row.completion_status,
        "progress": row.progress,
        "actor": row.actor or "",
        "counts": _json_load(row.counts_json, {}),
        "totals": _json_load(row.totals_json, {}),
        "checks": _json_load(row.checks_json, []),
        "source_files": _json_load(row.source_files_json, []),
        "source_dataset_ids": _json_load(row.source_dataset_ids_json, {}),
        "ruleset_id": row.ruleset_id,
        "ruleset_version": row.ruleset_version,
        "rules_snapshot": _json_load(row.rules_snapshot_json, {}),
        "error_message": row.error_message or "",
        "parent_run_id": row.parent_run_id,
        "input_hash": row.input_hash or "",
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _decode_exception(row: ReconException) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "match_id": row.match_id,
        "category": row.category,
        "category_label": EXCEPTION_LABELS.get(
            row.category, row.category.replace("_", " ").title()
        ),
        "status": row.status,
        "severity": row.severity,
        "title": row.title,
        "description": row.description,
        "amount": row.amount,
        "currency": row.currency or "",
        "assigned_to": row.assigned_to or "",
        "resolution_reason": row.resolution_reason or "",
        "evidence": _json_load(row.evidence_json, []),
        "previous_status": row.previous_status or "",
        "source_refs": _json_load(row.source_refs_json, []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


def _decode_audit(row: ReconAuditEvent) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "match_id": row.match_id,
        "exception_id": row.exception_id,
        "actor": row.actor,
        "action": row.action,
        "previous_status": row.previous_status or "",
        "new_status": row.new_status or "",
        "reason": row.reason or "",
        "record_refs": _json_load(row.record_refs_json, []),
        "evidence_refs": _json_load(row.evidence_refs_json, []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _audit(
    session,
    run_id: int,
    action: str,
    *,
    actor: str,
    match_id: int | None = None,
    exception_id: int | None = None,
    previous_status: str | None = None,
    new_status: str | None = None,
    reason: str | None = None,
    record_refs: Sequence[Any] | None = None,
    evidence_refs: Sequence[Any] | None = None,
) -> ReconAuditEvent:
    event = ReconAuditEvent(
        run_id=run_id,
        match_id=match_id,
        exception_id=exception_id,
        actor=_actor(actor),
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
        record_refs_json=_json_dump(list(record_refs or [])),
        evidence_refs_json=_json_dump(list(evidence_refs or [])),
        created_at=_now(),
    )
    session.add(event)
    return event


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def _latest_rule_set(session, workflow_id: str, client_id: int | None = None):
    query = session.query(ReconRuleSet)
    if client_id is not None:
        exact = (
            query.filter(
                ReconRuleSet.workflow_id == workflow_id,
                ReconRuleSet.client_id == client_id,
                ReconRuleSet.is_default == 1,
            )
            .order_by(ReconRuleSet.version.desc(), ReconRuleSet.id.desc())
            .first()
        )
        if exact is not None:
            return exact
    return (
        query.filter(
            ReconRuleSet.workflow_id == workflow_id,
            ReconRuleSet.client_id.is_(None),
            ReconRuleSet.is_default == 1,
        )
        .order_by(ReconRuleSet.version.desc(), ReconRuleSet.id.desc())
        .first()
    )


def get_ruleset(ruleset_id: int) -> dict:
    session = get_session()
    try:
        row = session.get(ReconRuleSet, int(ruleset_id))
        if row is None:
            raise ValueError("That reconciliation rule set was not found.")
        return _decode_ruleset(row)
    finally:
        session.close()


def _decode_ruleset(row: ReconRuleSet) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "workflow_id": row.workflow_id,
        "client_id": row.client_id,
        "version": row.version,
        "is_default": bool(row.is_default),
        "config": normalise_rules(_json_load(row.config_json, {})),
        "config_json": _json_load(row.config_json, {}),
        "notes": row.notes or "",
        "created_by": row.created_by or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_rule_sets(workflow_id: str | None = None) -> dict:
    session = get_session()
    try:
        query = session.query(ReconRuleSet)
        if workflow_id:
            query = query.filter(ReconRuleSet.workflow_id == str(workflow_id))
        rows = query.order_by(
            ReconRuleSet.workflow_id.asc(),
            ReconRuleSet.name.asc(),
            ReconRuleSet.version.desc(),
        ).all()
        return {
            "rulesets": [_decode_ruleset(row) for row in rows],
            "defaults": normalise_rules(DEFAULT_RULES),
            "default_summary": rule_summary(DEFAULT_RULES),
            "workflows": [
                {
                    "id": workflow["id"],
                    "label": workflow["label"],
                    "group": workflow.get("group", ""),
                }
                for workflow in WORKFLOWS
            ],
        }
    finally:
        session.close()


def save_rule_set(payload: Mapping[str, Any], actor: str | None = None) -> dict:
    workflow_id = str(payload.get("workflow_id") or "*").strip() or "*"
    if workflow_id != "*" and workflow_id not in WORKFLOW_BY_ID:
        raise ValueError("Choose a valid reconciliation workflow.")
    name = str(payload.get("name") or "Reconciliation rules").strip()
    if not name:
        raise ValueError("Give the rule set a name.")
    config = normalise_rules(payload.get("config") or payload)
    client_id = payload.get("client_id")
    try:
        client_id = int(client_id) if client_id not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("Client was not found.")
    session = get_session()
    try:
        existing = (
            session.query(ReconRuleSet)
            .filter(
                ReconRuleSet.name == name,
                ReconRuleSet.workflow_id == workflow_id,
                ReconRuleSet.client_id == client_id,
            )
            .order_by(ReconRuleSet.version.desc())
            .first()
        )
        version = (existing.version + 1) if existing else 1
        if payload.get("is_default", True):
            session.query(ReconRuleSet).filter(
                ReconRuleSet.workflow_id == workflow_id,
                ReconRuleSet.client_id == client_id,
            ).update({ReconRuleSet.is_default: 0})
        row = ReconRuleSet(
            name=name,
            workflow_id=workflow_id,
            client_id=client_id,
            version=version,
            is_default=1 if payload.get("is_default", True) else 0,
            config_json=_json_dump(config),
            notes=str(payload.get("notes") or "").strip() or None,
            created_by=_actor(actor),
            created_at=_now(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _decode_ruleset(row)
    finally:
        session.close()


def _resolve_rules(
    session,
    workflow_id: str,
    client_id: int,
    ruleset_id: int | None,
) -> tuple[ReconRuleSet | None, dict]:
    row = None
    if ruleset_id not in (None, ""):
        try:
            row = session.get(ReconRuleSet, int(ruleset_id))
        except (TypeError, ValueError):
            row = None
        if row is None:
            raise ValueError("That reconciliation rule set was not found.")
    if row is None:
        row = _latest_rule_set(session, workflow_id, client_id)
    if row is None:
        row = ReconRuleSet(
            name="Default reconciliation rules",
            workflow_id=workflow_id,
            client_id=None,
            version=1,
            is_default=1,
            config_json=_json_dump(normalise_rules(DEFAULT_RULES)),
            notes="Created automatically from the built-in safe defaults.",
            created_by="system",
            created_at=_now(),
        )
        session.add(row)
        session.flush()
    config = normalise_rules(_json_load(row.config_json, {}))
    return row, config


# ---------------------------------------------------------------------------
# Run creation and execution
# ---------------------------------------------------------------------------


def _period_context(period_id: int) -> tuple[Period, Client]:
    session = get_session()
    try:
        period = session.get(Period, int(period_id))
        if period is None:
            raise ValueError("Period was not found.")
        client = session.get(Client, period.client_id)
        if client is None:
            raise ValueError("Client was not found.")
        return period, client
    finally:
        session.close()


def _missing_message(workflow: Mapping, missing: Sequence[str]) -> str:
    if len(missing) == 2:
        return (
            f"{workflow['label']} needs both {workflow['left_label']} and "
            f"{workflow['right_label']} for this period. Nothing is calculated until both are present."
        )
    return (
        f"{workflow['label']} needs {missing[0]} for this period. "
        "Nothing is calculated until it is present."
    )


def prepare_run(
    period_id: int,
    workflow_id: str,
    *,
    ruleset_id: int | None = None,
    actor: str | None = None,
    parent_run_id: int | None = None,
) -> dict:
    workflow = workflow_definition(workflow_id)
    if workflow is None:
        raise ValueError("That reconciliation workflow is not available.")
    period, client = _period_context(period_id)
    datasets = datasets_for_period(period.id)
    left_rows = datasets.get(workflow["left_key"]) or []
    right_rows = datasets.get(workflow["right_key"]) or []
    missing = []
    if not left_rows:
        missing.append(workflow["left_label"])
    if not right_rows:
        missing.append(workflow["right_label"])
    if missing:
        return {
            "available": False,
            "workflow": workflow,
            "missing": missing,
            "message": _missing_message(workflow, missing),
            "datasets": {
                key: len(value or [])
                for key, value in datasets.items()
                if key != "all_books"
            },
        }
    meta = period_meta(period, client)
    session = get_session()
    try:
        ruleset, config = _resolve_rules(
            session, workflow["id"], client.id, ruleset_id
        )
        source_rows = [*left_rows, *right_rows]
        sources = dataset_sources(source_rows)
        source_ids = {
            "left": [source["file_id"] for source in dataset_sources(left_rows)],
            "right": [source["file_id"] for source in dataset_sources(right_rows)],
        }
        snapshot = {
            "engine_version": ENGINE_VERSION,
            "ruleset": {
                "id": ruleset.id if ruleset else None,
                "name": ruleset.name if ruleset else "Built-in defaults",
                "version": ruleset.version if ruleset else 1,
                "client_id": ruleset.client_id if ruleset else None,
                "workflow_id": ruleset.workflow_id if ruleset else workflow["id"],
            },
            "config": config,
            "summary": rule_summary(config),
        }
        run = ReconRun(
            run_uuid=uuid.uuid4().hex,
            client_id=client.id,
            period_id=period.id,
            workflow_id=workflow["id"],
            workflow_label=workflow["label"],
            client_name=client.name,
            period_label=period.label,
            financial_year=meta["financial_year"],
            status="queued",
            completion_status="in_progress",
            progress=0,
            source_dataset_ids_json=_json_dump(source_ids),
            source_files_json=_json_dump(sources),
            ruleset_id=ruleset.id if ruleset else None,
            ruleset_version=ruleset.version if ruleset else 1,
            rules_snapshot_json=_json_dump(snapshot),
            counts_json="{}",
            totals_json="{}",
            checks_json="[]",
            actor=_actor(actor),
            parent_run_id=parent_run_id,
            created_at=_now(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        _audit(
            session,
            run.id,
            "run_queued",
            actor=_actor(actor),
            new_status="queued",
            reason=f"{workflow['label']} started for {client.name} · {period.label}.",
            record_refs=[source["file_id"] for source in sources],
        )
        session.commit()
        payload = _decode_run(run)
        payload["available"] = True
        payload["datasets"] = dataset_payload(workflow, datasets)
        return payload
    finally:
        session.close()


def start_reconciliation(
    period_id: int,
    workflow_id: str,
    *,
    ruleset_id: int | None = None,
    actor: str | None = None,
    background: bool = True,
    parent_run_id: int | None = None,
) -> dict:
    prepared = prepare_run(
        period_id,
        workflow_id,
        ruleset_id=ruleset_id,
        actor=actor,
        parent_run_id=parent_run_id,
    )
    if not prepared.get("available"):
        return prepared
    run_id = int(prepared["id"])
    if background:
        thread = threading.Thread(
            target=_execute_run_thread,
            args=(run_id,),
            name=f"recon-run-{run_id}",
            daemon=True,
        )
        with _RUN_THREADS_LOCK:
            _RUN_THREADS.add(thread)
        thread.start()
        prepared["status"] = "queued"
        return prepared
    _execute_run(run_id)
    payload = get_run(run_id)
    payload["available"] = payload.get("status") != "failed"
    return payload


def cancel_run(run_id: int, actor: str | None = None) -> dict:
    session = get_session()
    try:
        run = session.get(ReconRun, int(run_id))
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        if run.status not in {"queued", "running"}:
            return {"ok": False, "error": "Only a queued or running reconciliation can be cancelled."}
        with _CANCELLED_LOCK:
            _CANCELLED_RUNS.add(run.id)
        run.status = "cancelled"
        run.completion_status = "cancelled"
        run.error_message = "Cancelled by the user."
        run.completed_at = _now()
        run.progress = 100
        _audit(
            session,
            run.id,
            "run_cancelled",
            actor=_actor(actor),
            previous_status="running",
            new_status="cancelled",
            reason="Cancelled by the user before results were stored.",
        )
        session.commit()
        return {"ok": True, "run_id": run.id, "status": "cancelled"}
    finally:
        session.close()


def _check_cancelled(run_id: int) -> None:
    with _CANCELLED_LOCK:
        cancelled = run_id in _CANCELLED_RUNS
    if not cancelled:
        session = get_session()
        try:
            run = session.get(ReconRun, run_id)
            cancelled = run is not None and run.status == "cancelled"
        finally:
            session.close()
    if cancelled:
        raise ReconciliationCancelled()


def _execute_run_thread(run_id: int) -> None:
    try:
        _execute_run(run_id)
    finally:
        with _RUN_THREADS_LOCK:
            _RUN_THREADS.discard(threading.current_thread())
        with _CANCELLED_LOCK:
            _CANCELLED_RUNS.discard(run_id)


def _set_progress(run_id: int, progress: int) -> None:
    session = get_session()
    try:
        run = session.get(ReconRun, run_id)
        if run is not None:
            run.progress = max(0, min(100, int(progress)))
            session.commit()
    finally:
        session.close()


def _execute_run(run_id: int) -> None:
    with _EXECUTION_LOCK:
        session = get_session()
        run = None
        try:
            run = session.get(ReconRun, run_id)
            if run is None:
                return
            with _CANCELLED_LOCK:
                cancelled_before_start = run_id in _CANCELLED_RUNS
            if run.status == "cancelled" or cancelled_before_start:
                return
            workflow = workflow_definition(run.workflow_id)
            if workflow is None:
                raise ValueError("The workflow for this run no longer exists.")
            run.status = "running"
            run.progress = 5
            run.started_at = _now()
            session.commit()
            _audit(
                session,
                run.id,
                "run_started",
                actor=run.actor or "local user",
                previous_status="queued",
                new_status="running",
            )
            session.commit()
        except BaseException as exc:
            session.rollback()
            session.close()
            _fail_run(run_id, str(exc) or "The reconciliation could not start.")
            return
        finally:
            # The actual worker uses its own transaction below.
            if session.is_active:
                session.close()

        try:
            period, client = _period_context(run.period_id)
            datasets = datasets_for_period(period.id)
            left_rows = datasets.get(workflow["left_key"]) or []
            right_rows = datasets.get(workflow["right_key"]) or []
            if not left_rows or not right_rows:
                raise ValueError(
                    _missing_message(
                        workflow,
                        [
                            workflow["left_label"] if not left_rows else "",
                            workflow["right_label"] if not right_rows else "",
                        ],
                    )
                )
            _check_cancelled(run.id)
            _set_progress(run.id, 25)
            snapshot = _json_load(run.rules_snapshot_json, {})
            config = normalise_rules(snapshot.get("config") or {})
            result = match_dataset(
                left_rows,
                right_rows,
                config,
                mode=workflow["mode"],
            )
            _check_cancelled(run.id)
            _set_progress(run.id, 65)
            _check_cancelled(run.id)

            session = get_session()
            try:
                run = session.get(ReconRun, run_id)
                if run is None:
                    return
                # A rerun always gets a new run row; this cleanup only matters
                # if an interrupted run is retried in place.
                session.query(ReconException).filter(
                    ReconException.run_id == run_id
                ).delete(synchronize_session=False)
                session.query(ReconRecordLink).filter(
                    ReconRecordLink.run_id == run_id
                ).delete(synchronize_session=False)
                session.query(ReconMatch).filter(
                    ReconMatch.run_id == run_id
                ).delete(synchronize_session=False)
                session.flush()
                _persist_engine_result(session, run, result, workflow)
                run.input_hash = _input_hash(left_rows, right_rows, config)
                run.counts_json = _json_dump(result.get("counts") or {})
                run.totals_json = _json_dump(result.get("totals") or {})
                run.checks_json = _json_dump(result.get("checks") or [])
                run.status = "completed"
                run.progress = 90
                run.completed_at = _now()
                session.flush()
                _refresh_run_summary(session, run)
                processed = int(
                    (result.get("totals") or {}).get("left_rows", 0)
                    or 0
                ) + int((result.get("totals") or {}).get("right_rows", 0) or 0)
                _audit(
                    session,
                    run.id,
                    "run_completed",
                    actor=run.actor or "local user",
                    previous_status="running",
                    new_status="completed",
                    reason=f"Processed {processed} records and stored the evidence snapshot.",
                )
                run.progress = 100
                session.commit()
                session.refresh(run)
                # Persist the direct object payload after refresh so callers
                # polling immediately see the final summary.
            finally:
                session.close()
        except ReconciliationCancelled:
            # The run row was already marked cancelled by cancel_run().  Do not
            # overwrite it with a failed status, and repair the status if the
            # worker had already moved it to running.
            with _CANCELLED_LOCK:
                _CANCELLED_RUNS.discard(run_id)
            cleanup = get_session()
            try:
                current = cleanup.get(ReconRun, run_id)
                if current is not None and current.status in {"queued", "running"}:
                    current.status = "cancelled"
                    current.completion_status = "cancelled"
                    current.error_message = "Cancelled by the user."
                    current.completed_at = _now()
                    current.progress = 100
                    cleanup.commit()
            finally:
                cleanup.close()
        except BaseException as exc:
            _fail_run(run_id, str(exc) or "The reconciliation failed.")


def _input_hash(left_rows: Sequence[Mapping], right_rows: Sequence[Mapping], config: Mapping) -> str:
    digest = hashlib.sha256()
    for side, rows in (("left", left_rows), ("right", right_rows)):
        digest.update(side.encode())
        for row in rows:
            payload = {
                key: value
                for key, value in row.items()
                if not str(key).startswith("_ca_")
            }
            digest.update(_json_dump(payload).encode("utf-8"))
    digest.update(_json_dump(config).encode("utf-8"))
    return digest.hexdigest()


def _fail_run(run_id: int, message: str) -> None:
    session = get_session()
    try:
        run = session.get(ReconRun, run_id)
        if run is None:
            return
        previous = run.status
        run.status = "failed"
        run.completion_status = "failed"
        run.error_message = message[:1000]
        run.completed_at = _now()
        run.progress = 100
        _audit(
            session,
            run.id,
            "run_failed",
            actor=run.actor or "local user",
            previous_status=previous,
            new_status="failed",
            reason=message[:1000],
        )
        session.commit()
    finally:
        session.close()


def _source_refs(records: Iterable[Mapping]) -> list[dict]:
    refs = []
    for record in records:
        refs.append(
            {
                "row_id": record.get("row_id"),
                "file_id": record.get("file_id"),
                "file_name": record.get("file_name") or record.get("source") or "",
                "page": record.get("source_page"),
                "bbox": record.get("source_bbox"),
                "reference": record.get("reference"),
                "party": record.get("party"),
                "amount": record.get("amount"),
            }
        )
    return refs


def _balance_side_records(value: Any, side: str) -> list[dict]:
    """Turn a balance aggregate into the match-record shape used by the UI."""

    if isinstance(value, list):
        return value
    if not isinstance(value, Mapping):
        return []
    rows = value.get("rows") or []
    first = rows[0] if isinstance(rows, list) and rows else {}
    closing = value.get("closing")
    if closing is None:
        closing = value.get("movement")
    if closing is None:
        closing = value.get("opening")
    account = value.get("account") or first.get("account") or ""
    return [
        {
            "row_id": first.get("row_id"),
            "file_id": first.get("file_id"),
            "file_name": first.get("file_name") or "",
            "kind": first.get("kind") or "",
            "reference": account,
            "normalized_reference": account,
            "party": first.get("party") or account,
            "gstin": "",
            "date": "",
            "amount": closing,
            "taxable": None,
            "tax": None,
            "currency": "",
            "direction": "",
            "description": f"{side.title()} balance for {account}" if account else f"{side.title()} balance",
            "document_type": "balance",
            "source": first.get("source") or "",
            "source_page": first.get("source_page"),
            "source_bbox": first.get("source_bbox"),
            "aggregate": _json_load(_json_dump(value), {}),
            "raw": value,
        }
    ]


def _balance_fields(row: Mapping) -> list[dict]:
    left = _balance_side_records(row.get("left"), "left")
    right = _balance_side_records(row.get("right"), "right")
    left_agg = left[0].get("aggregate") if left else None
    right_agg = right[0].get("aggregate") if right else None
    if not left_agg or not right_agg:
        return []
    fields = []
    for key, label in (
        ("opening", "Opening balance"),
        ("movement", "Period movement"),
        ("closing", "Closing balance"),
    ):
        left_value = left_agg.get(key)
        right_value = right_agg.get(key)
        matched = None
        if left_value is not None and right_value is not None:
            matched = abs(float(left_value) - float(right_value)) <= 1.0
        fields.append(
            {
                "field": label,
                "left": left_value,
                "right": right_value,
                "matched": matched,
                "note": "Compared from stored balance values",
            }
        )
    fields.append(
        {
            "field": "Account",
            "left": left_agg.get("account"),
            "right": right_agg.get("account"),
            "matched": left_agg.get("account") == right_agg.get("account"),
            "note": "Grouped by account code/name",
        }
    )
    return fields


def _persist_engine_result(session, run: ReconRun, result: Mapping, workflow: Mapping) -> None:
    rows = result.get("rows") or []
    ordinal = 0
    is_balance = workflow.get("mode") == "balance"
    for row in rows:
        raw_left = row.get("left") or []
        raw_right = row.get("right") or []
        if is_balance:
            left = _balance_side_records(raw_left, "left")
            right = _balance_side_records(raw_right, "right")
            status_value = str(row.get("status") or "")
            if status_value == "matched":
                classification = "exact"
                status = "matched"
                confidence = 100
                requires_review = 0
            elif status_value in {"left_only", "right_only"}:
                classification = "unmatched"
                status = "unmatched"
                confidence = 0
                requires_review = 1
            else:
                classification = "review"
                status = "proposed"
                confidence = 70
                requires_review = 1
        else:
            left = raw_left if isinstance(raw_left, list) else []
            right = raw_right if isinstance(raw_right, list) else []
            classification = str(row.get("classification") or "review")
            status = str(row.get("status") or "proposed")
            confidence = int(row.get("confidence") or 0)
            requires_review = 1 if row.get("requires_review") else 0
        left_amount = sum(float(record.get("amount") or 0) for record in left)
        right_amount = sum(float(record.get("amount") or 0) for record in right)
        differences = dict(row.get("differences") or {})
        currency = ""
        for record in [*left, *right]:
            if record.get("currency"):
                currency = str(record.get("currency"))
                break
        matched_fields = row.get("matched_fields") or (
            _balance_fields(row) if is_balance else []
        )
        match = ReconMatch(
            run_id=run.id,
            ordinal=ordinal,
            classification=classification,
            status=status,
            match_type=str(row.get("match_type") or ("balance" if is_balance else "none")),
            confidence=confidence,
            requires_review=requires_review,
            reason_code=str(row.get("reason_code") or ""),
            explanation=str(row.get("explanation") or ""),
            matched_fields_json=_json_dump(matched_fields),
            differences_json=_json_dump(differences),
            tolerances_json=_json_dump(row.get("tolerances") or []),
            exception_categories_json=_json_dump(row.get("exception_categories") or []),
            allocations_json=_json_dump(row.get("allocations") or []),
            candidates_json=_json_dump(row.get("candidates") or []),
            left_records_json=_json_dump(left),
            right_records_json=_json_dump(right),
            left_row_ids_json=_json_dump(row.get("left_ids") or []),
            right_row_ids_json=_json_dump(row.get("right_ids") or []),
            left_amount=left_amount,
            right_amount=right_amount,
            difference_amount=_as_float(differences.get("amount")),
            currency=currency or None,
            is_superseded=0,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(match)
        session.flush()
        for record in left:
            session.add(
                ReconRecordLink(
                    run_id=run.id,
                    match_id=match.id,
                    side="left",
                    row_id=record.get("row_id"),
                    record_json=_json_dump(record),
                    created_at=_now(),
                )
            )
        for record in right:
            session.add(
                ReconRecordLink(
                    run_id=run.id,
                    match_id=match.id,
                    side="right",
                    row_id=record.get("row_id"),
                    record_json=_json_dump(record),
                    created_at=_now(),
                )
            )
        categories = list(row.get("exception_categories") or [])
        if not categories and match.status == "proposed":
            categories = ["unmatched_transaction"]
        if match.status == "duplicate" and "duplicate_records" not in categories:
            categories = ["duplicate_records"]
        if match.status == "reversal_candidate" and "possible_reversal" not in categories:
            categories = ["possible_reversal"]
        if match.status == "unmatched" and not categories:
            categories = ["unmatched_transaction"]
        source_refs = _source_refs([*left, *right])
        for category in dict.fromkeys(categories):
            exception = _create_exception(
                session,
                run,
                match,
                category,
                amount=max(left_amount, right_amount),
                currency=currency or None,
                source_refs=source_refs,
                description=match.explanation,
            )
            session.add(exception)
        ordinal += 1
    session.commit()


def _exception_title(run: ReconRun, match: ReconMatch, category: str) -> str:
    label = EXCEPTION_LABELS.get(category, category.replace("_", " ").title())
    left = _json_load(match.left_records_json, [])
    right = _json_load(match.right_records_json, [])
    reference = ""
    party = ""
    for record in [*left, *right]:
        reference = reference or str(record.get("reference") or "")
        party = party or str(record.get("party") or "")
    bits = [label]
    if reference:
        bits.append(reference)
    elif party:
        bits.append(party)
    bits.append(f"run {run.run_uuid[:8]}")
    return " · ".join(bits)


def _exception_severity(category: str, amount: float | None) -> str:
    if category in {"duplicate_records", "possible_reversal", "currency_mismatch", "balance_variance"}:
        return "high"
    if amount is not None and abs(amount) >= 100000:
        return "high"
    if category in {"unmatched_transaction", "amount_mismatch", "multiple_possible_matches"}:
        return "medium"
    return "low"


def _create_exception(
    session,
    run: ReconRun,
    match: ReconMatch,
    category: str,
    *,
    amount: float | None,
    currency: str | None,
    source_refs: Sequence[Mapping],
    description: str = "",
    status: str = "open",
    resolution_reason: str | None = None,
) -> ReconException:
    exception = ReconException(
        run_id=run.id,
        match_id=match.id,
        category=category,
        status=status,
        severity=_exception_severity(category, amount),
        title=_exception_title(run, match, category),
        description=(description or "")[:2000],
        amount=amount,
        currency=currency,
        resolution_reason=resolution_reason,
        evidence_json="[]",
        source_refs_json=_json_dump(list(source_refs)),
        resolved_at=_now() if status in RESOLVED_EXCEPTION_STATUSES else None,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(exception)
    session.flush()
    return exception


def _refresh_run_summary(session, run: ReconRun) -> dict:
    matches = (
        session.query(ReconMatch)
        .filter(ReconMatch.run_id == run.id, ReconMatch.is_superseded == 0)
        .all()
    )
    counts = {
        "exact": 0,
        "strong": 0,
        "probable": 0,
        "partial": 0,
        "review": 0,
        "unmatched": 0,
        "duplicate": 0,
        "reversal_candidate": 0,
        "manual": 0,
        "matched": 0,
        "proposed": 0,
        "total": len(matches),
    }
    matched_records = 0
    unmatched_records = 0
    proposed_records = 0
    duplicate_records = 0
    matched_amount = 0.0
    for match in matches:
        counts[match.classification] = counts.get(match.classification, 0) + 1
        record_count = len(_json_load(match.left_records_json, [])) + len(
            _json_load(match.right_records_json, [])
        )
        if match.status in MATCHED_STATUSES:
            counts["matched"] += 1
            matched_records += record_count
            matched_amount += float(match.left_amount or 0)
        elif match.status in PROPOSED_STATUSES:
            counts["proposed"] += 1
            proposed_records += record_count
        elif match.status in DUPLICATE_STATUSES:
            duplicate_records += record_count
        elif match.status in REVERSAL_STATUSES:
            proposed_records += record_count
        elif match.status in UNMATCHED_STATUSES:
            unmatched_records += record_count
    total_records = sum(
        len(_json_load(match.left_records_json, [])) + len(_json_load(match.right_records_json, []))
        for match in matches
    )
    exceptions = (
        session.query(ReconException)
        .filter(ReconException.run_id == run.id)
        .all()
    )
    open_exceptions = [
        exception for exception in exceptions if exception.status not in RESOLVED_EXCEPTION_STATUSES
    ]
    unresolved_value = sum(abs(float(exception.amount or 0)) for exception in open_exceptions)
    amount_discrepancies = sum(
        1
        for exception in exceptions
        if exception.category in {"amount_mismatch", "partial_settlement"}
    )
    base_totals = _json_load(run.totals_json, {})
    totals = {
        **base_totals,
        "left_rows": sum(
            len(_json_load(match.left_records_json, [])) for match in matches
        ),
        "right_rows": sum(
            len(_json_load(match.right_records_json, [])) for match in matches
        ),
        "records_processed": total_records,
        "matched_records": matched_records,
        "unmatched_records": unmatched_records,
        "proposed_records": proposed_records,
        "duplicate_records": duplicate_records,
        "matched_amount": matched_amount,
        "unresolved_amount": unresolved_value,
        "open_exceptions": len(open_exceptions),
        "total_exceptions": len(exceptions),
        "amount_discrepancies": amount_discrepancies,
        "match_rate": round((matched_records / total_records * 100.0), 2) if total_records else 0.0,
    }
    run.counts_json = _json_dump(counts)
    run.totals_json = _json_dump(totals)
    if run.status in {"failed", "cancelled"}:
        completion = run.status
    elif open_exceptions:
        completion = "completed_with_exceptions"
    else:
        completion = "completed"
    run.completion_status = completion
    run.updated_at = _now()
    return {"counts": counts, "totals": totals, "completion_status": completion}


# ---------------------------------------------------------------------------
# Run and control-centre queries
# ---------------------------------------------------------------------------


def get_run(run_id: int) -> dict:
    session = get_session()
    try:
        run = session.get(ReconRun, int(run_id))
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        payload = _decode_run(run)
        exception_counts = dict(
            session.query(ReconException.status, func.count(ReconException.id))
            .filter(ReconException.run_id == run.id)
            .group_by(ReconException.status)
            .all()
        )
        category_counts = dict(
            session.query(ReconException.category, func.count(ReconException.id))
            .filter(ReconException.run_id == run.id)
            .group_by(ReconException.category)
            .all()
        )
        payload["exception_counts"] = exception_counts
        payload["exception_category_counts"] = category_counts
        payload["audit_count"] = int(
            session.query(func.count(ReconAuditEvent.id))
            .filter(ReconAuditEvent.run_id == run.id)
            .scalar()
            or 0
        )
        return payload
    finally:
        session.close()


def _run_filter_query(session, filters: Mapping[str, Any] | None):
    filters = filters or {}
    query = session.query(ReconRun)
    client_id = _as_int(filters.get("client_id"))
    if client_id:
        query = query.filter(ReconRun.client_id == client_id)
    period_id = _as_int(filters.get("period_id"))
    if period_id:
        query = query.filter(ReconRun.period_id == period_id)
    fy = str(filters.get("financial_year") or "").strip()
    if fy:
        query = query.filter(ReconRun.financial_year == fy)
    workflow_id = str(filters.get("workflow_id") or "").strip()
    if workflow_id:
        query = query.filter(ReconRun.workflow_id == workflow_id)
    status = str(filters.get("run_status") or filters.get("status") or "").strip()
    if status:
        query = query.filter(ReconRun.status == status)
    source_file_id = _as_int(filters.get("source_file_id"))
    if source_file_id:
        # Match the exact JSON member, not a prefix of a larger id (1 vs 10).
        query = query.filter(
            or_(
                ReconRun.source_files_json.like(f'%"file_id":{source_file_id},%'),
                ReconRun.source_files_json.like(f'%"file_id":{source_file_id}}}%'),
            )
        )
    exception_status = str(filters.get("exception_status") or "").strip()
    if exception_status:
        subquery = select(ReconException.run_id).where(
            ReconException.status == exception_status
        )
        query = query.filter(ReconRun.id.in_(subquery))
    search = str(filters.get("search") or "").strip()
    if search:
        needle = f"%{search}%"
        query = query.filter(
            or_(
                ReconRun.client_name.ilike(needle),
                ReconRun.period_label.ilike(needle),
                ReconRun.workflow_label.ilike(needle),
                ReconRun.run_uuid.ilike(needle),
            )
        )
    return query


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_runs(
    filters: Mapping[str, Any] | None = None,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    session = get_session()
    try:
        query = _run_filter_query(session, filters)
        total = int(query.count())
        rows = (
            query.order_by(ReconRun.created_at.desc(), ReconRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "runs": [_decode_run(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }
    finally:
        session.close()


def _exception_counts_for_runs(session, run_ids: Sequence[int]) -> dict[int, dict]:
    if not run_ids:
        return {}
    result: dict[int, dict] = {}
    counts = (
        session.query(
            ReconException.run_id,
            ReconException.status,
            func.count(ReconException.id),
        )
        .filter(ReconException.run_id.in_(list(run_ids)))
        .group_by(ReconException.run_id, ReconException.status)
        .all()
    )
    for run_id, status, count in counts:
        bucket = result.setdefault(int(run_id), {})
        bucket[status] = int(count)
    return result


def control_centre(filters: Mapping[str, Any] | None = None) -> dict:
    filters = filters or {}
    session = get_session()
    try:
        query = _run_filter_query(session, filters)
        all_runs = query.order_by(ReconRun.created_at.desc(), ReconRun.id.desc()).all()
        run_ids = [run.id for run in all_runs]
        exception_counts = _exception_counts_for_runs(session, run_ids)
        latest_by_scope: dict[tuple[int, str], ReconRun] = {}
        for run in all_runs:
            if run.status != "completed":
                continue
            key = (run.period_id, run.workflow_id)
            if key not in latest_by_scope:
                latest_by_scope[key] = run
        scope_runs = list(latest_by_scope.values())
        scope_run_ids = [run.id for run in scope_runs]
        open_exceptions_query = session.query(ReconException).filter(
            ReconException.run_id.in_(scope_run_ids or [-1]),
            ReconException.status.notin_(list(RESOLVED_EXCEPTION_STATUSES)),
        )
        open_exceptions = (
            open_exceptions_query.order_by(
                ReconException.amount.desc(), ReconException.id.desc()
            )
            .limit(25)
            .all()
        )
        open_count = int(open_exceptions_query.count())
        unresolved_value = float(
            session.query(func.coalesce(func.sum(func.abs(ReconException.amount)), 0.0))
            .filter(
                ReconException.run_id.in_(scope_run_ids or [-1]),
                ReconException.status.notin_(list(RESOLVED_EXCEPTION_STATUSES)),
            )
            .scalar()
            or 0
        )
        category_rows = (
            session.query(ReconException.category, func.count(ReconException.id))
            .filter(
                ReconException.run_id.in_(scope_run_ids or [-1]),
                ReconException.status.notin_(list(RESOLVED_EXCEPTION_STATUSES)),
            )
            .group_by(ReconException.category)
            .order_by(func.count(ReconException.id).desc())
            .all()
        )
        completion_counts = {
            status: int(
                session.query(func.count(ReconRun.id))
                .filter(ReconRun.id.in_(run_ids or [-1]), ReconRun.completion_status == status)
                .scalar()
                or 0
            )
            for status in (
                "in_progress",
                "completed",
                "completed_with_exceptions",
                "failed",
                "cancelled",
            )
        }
        recent_runs = [_decode_run(run) for run in all_runs[:12]]
        for payload in recent_runs:
            payload["exception_counts"] = exception_counts.get(payload["id"], {})
        total_runs = len(all_runs)
        records_processed = 0
        matched_records = 0
        unmatched_records = 0
        requiring = 0
        duplicates = 0
        amount_discrepancies = 0
        debit_total = 0.0
        credit_total = 0.0
        for run in scope_runs:
            totals = _json_load(run.totals_json, {})
            records_processed += int(
                (totals.get("left_rows") or 0) + (totals.get("right_rows") or 0)
            )
            matched_records += int(totals.get("matched_records") or 0)
            unmatched_records += int(totals.get("unmatched_records") or 0)
            run_exception_counts = exception_counts.get(run.id, {})
            requiring += sum(
                int(count)
                for status, count in run_exception_counts.items()
                if status not in RESOLVED_EXCEPTION_STATUSES
            )
            duplicates += int(totals.get("duplicate_records") or 0)
            amount_discrepancies += int(totals.get("amount_discrepancies") or 0)
            debit_total += float(totals.get("debit_total") or 0)
            credit_total += float(totals.get("credit_total") or 0)
        match_rate = (
            round(matched_records / records_processed * 100.0, 2)
            if records_processed
            else 0.0
        )
        exceptions_payload = []
        run_map = {run.id: run for run in all_runs}
        for exception in open_exceptions:
            payload = _decode_exception(exception)
            run = run_map.get(exception.run_id)
            if run is not None:
                payload["run_uuid"] = run.run_uuid
                payload["workflow_label"] = run.workflow_label
                payload["client_name"] = run.client_name
                payload["period_label"] = run.period_label
            exceptions_payload.append(payload)
        return {
            "generated_at": _now().isoformat(),
            "metrics": {
                "total_runs": total_runs,
                "records_processed": records_processed,
                "matched_records": matched_records,
                "unmatched_records": unmatched_records,
                "requires_investigation": requiring,
                "duplicate_records": duplicates,
                "amount_discrepancies": amount_discrepancies,
                "match_rate": match_rate,
                "debit_total": debit_total,
                "credit_total": credit_total,
                "unresolved_exception_value": unresolved_value,
                "open_exceptions": open_count,
                "completion_counts": completion_counts,
            },
            "recent_runs": recent_runs,
            "outstanding_exceptions": exceptions_payload,
            "exception_categories": [
                {
                    "category": category,
                    "label": EXCEPTION_LABELS.get(
                        category, category.replace("_", " ").title()
                    ),
                    "count": int(count),
                }
                for category, count in category_rows
            ],
            "filters": recon_filter_options(session),
        }
    finally:
        session.close()


def recon_filter_options(session=None) -> dict:
    owned = session is None
    session = session or get_session()
    try:
        clients = session.query(Client).order_by(Client.name.asc()).all()
        periods = (
            session.query(Period, Client)
            .join(Client, Period.client_id == Client.id)
            .order_by(Period.created_at.desc(), Period.id.desc())
            .all()
        )
        years = sorted(
            {
                financial_year(period.label)
                for period, _client in periods
            },
            reverse=True,
        )
        source_files = (
            session.query(StoredFile.id, StoredFile.original_name, StoredFile.period_id)
            .order_by(StoredFile.original_name.asc())
            .all()
        )
        categories = sorted(
            {
                row[0]
                for row in session.query(ReconException.category).distinct().all()
                if row[0]
            }
        )
        statuses = sorted(
            {
                row[0]
                for row in session.query(ReconException.status).distinct().all()
                if row[0]
            }
        )
        return {
            "clients": [
                {"id": client.id, "name": client.name, "gstin": client.gstin or ""}
                for client in clients
            ],
            "periods": [
                {
                    "id": period.id,
                    "label": period.label,
                    "client_id": client.id,
                    "client_name": client.name,
                    "financial_year": financial_year(period.label),
                }
                for period, client in periods
            ],
            "financial_years": years,
            "workflows": [
                {
                    "id": workflow["id"],
                    "label": workflow["label"],
                    "group": workflow.get("group", ""),
                }
                for workflow in WORKFLOWS
            ],
            "source_files": [
                {
                    "id": file_id,
                    "name": name,
                    "period_id": period_id,
                }
                for file_id, name, period_id in source_files
            ],
            "run_statuses": list(RUN_STATUSES),
            "exception_statuses": list(
                dict.fromkeys([*EXCEPTION_STATUSES, *statuses])
            ),
            "exception_categories": [
                {
                    "id": category,
                    "label": EXCEPTION_LABELS.get(
                        category, category.replace("_", " ").title()
                    ),
                }
                for category in categories
            ],
        }
    finally:
        if owned:
            session.close()


# ---------------------------------------------------------------------------
# Workbench and detail
# ---------------------------------------------------------------------------


def _match_row_payload(row: ReconMatch, exceptions: Sequence[ReconException] | None = None) -> dict:
    payload = _decode(row)
    payload["exceptions"] = [_decode_exception(item) for item in exceptions or []]
    return payload


def get_run_rows(run_id: int, filters: Mapping[str, Any] | None = None) -> dict:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    page_size = min(500, max(10, int(filters.get("page_size") or 100)))
    session = get_session()
    try:
        run = session.get(ReconRun, int(run_id))
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        query = session.query(ReconMatch).filter(
            ReconMatch.run_id == run.id, ReconMatch.is_superseded == 0
        )
        status = str(filters.get("status") or "all")
        if status == "matched":
            query = query.filter(ReconMatch.status.in_(list(MATCHED_STATUSES)))
        elif status == "review":
            query = query.filter(ReconMatch.status.in_(["proposed", "reversal_candidate"]))
        elif status == "unmatched":
            query = query.filter(ReconMatch.status.in_(["unmatched", "rejected"]))
        elif status == "duplicate":
            query = query.filter(ReconMatch.status == "duplicate")
        elif status == "reversal":
            query = query.filter(ReconMatch.status == "reversal_candidate")
        elif status == "proposed":
            query = query.filter(ReconMatch.status == "proposed")
        classification = str(filters.get("classification") or "").strip()
        if classification:
            query = query.filter(ReconMatch.classification == classification)
        category = str(filters.get("category") or "").strip()
        if category:
            query = query.filter(
                ReconMatch.exception_categories_json.like(f'%"{category}"%')
            )
        exception_status = str(filters.get("exception_status") or "").strip()
        if exception_status:
            subquery = select(ReconException.match_id).where(
                ReconException.run_id == run.id,
                ReconException.status == exception_status,
            )
            query = query.filter(ReconMatch.id.in_(subquery))
        search = str(filters.get("search") or "").strip()
        if search:
            needle = f"%{search}%"
            query = query.filter(
                or_(
                    ReconMatch.left_records_json.ilike(needle),
                    ReconMatch.right_records_json.ilike(needle),
                    ReconMatch.explanation.ilike(needle),
                    ReconMatch.reason_code.ilike(needle),
                )
            )
        total = int(query.count())
        rows = (
            query.order_by(ReconMatch.ordinal.asc(), ReconMatch.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        ids = [row.id for row in rows]
        exceptions_by_match: dict[int, list[ReconException]] = {}
        if ids:
            exceptions = (
                session.query(ReconException)
                .filter(ReconException.match_id.in_(ids))
                .order_by(ReconException.id.asc())
                .all()
            )
            for exception in exceptions:
                exceptions_by_match.setdefault(exception.match_id, []).append(exception)
        return {
            "run": _decode_run(run),
            "rows": [
                _match_row_payload(row, exceptions_by_match.get(row.id, []))
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "filter": {
                key: filters.get(key)
                for key in (
                    "status",
                    "classification",
                    "category",
                    "exception_status",
                    "search",
                )
                if filters.get(key)
            },
        }
    finally:
        session.close()


def get_match_detail(match_id: int) -> dict:
    session = get_session()
    try:
        match = session.get(ReconMatch, int(match_id))
        if match is None:
            raise ValueError("That reconciliation row was not found.")
        run = session.get(ReconRun, match.run_id)
        exceptions = (
            session.query(ReconException)
            .filter(ReconException.match_id == match.id)
            .order_by(ReconException.id.asc())
            .all()
        )
        exception_ids = [exception.id for exception in exceptions]
        audit_query = session.query(ReconAuditEvent).filter(
            or_(
                ReconAuditEvent.match_id == match.id,
                ReconAuditEvent.exception_id.in_(exception_ids or [-1]),
            )
        )
        audit_rows = audit_query.order_by(
            ReconAuditEvent.created_at.desc(), ReconAuditEvent.id.desc()
        ).all()
        record_ids = [
            *_json_load(match.left_row_ids_json, []),
            *_json_load(match.right_row_ids_json, []),
        ]
        previous_attempts = []
        if record_ids:
            links = (
                session.query(ReconRecordLink)
                .filter(
                    ReconRecordLink.run_id == match.run_id,
                    ReconRecordLink.row_id.in_(record_ids),
                )
                .all()
            )
            seen: set[int] = set()
            for link in links:
                if link.match_id == match.id or link.match_id in seen:
                    continue
                seen.add(link.match_id)
                other = session.get(ReconMatch, link.match_id)
                if other is None:
                    continue
                previous_attempts.append(
                    {
                        "id": other.id,
                        "status": other.status,
                        "classification": other.classification,
                        "confidence": other.confidence,
                        "reason_code": other.reason_code,
                        "explanation": other.explanation,
                        "decided_by": other.decided_by or "",
                        "decided_at": other.decided_at.isoformat() if other.decided_at else None,
                        "decision_reason": other.decision_reason or "",
                        "is_superseded": bool(other.is_superseded),
                    }
                )
        return {
            "match": _match_row_payload(match, exceptions),
            "run": _decode_run(run) if run else {},
            "exceptions": [_decode_exception(exception) for exception in exceptions],
            "audit": [_decode_audit(event) for event in audit_rows],
            "previous_attempts": previous_attempts,
            "rules": _json_load(run.rules_snapshot_json, {}) if run else {},
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Manual decisions
# ---------------------------------------------------------------------------


def _load_run_matches(session, run_id: int, include_superseded: bool = False):
    query = session.query(ReconMatch).filter(ReconMatch.run_id == run_id)
    if not include_superseded:
        query = query.filter(ReconMatch.is_superseded == 0)
    return query


def _resolve_linked_exceptions(
    session,
    run_id: int,
    match_ids: Sequence[int],
    *,
    actor: str,
    reason: str,
    status: str = "resolved",
    action: str = "match_decision",
) -> None:
    if not match_ids:
        return
    exceptions = (
        session.query(ReconException)
        .filter(ReconException.run_id == run_id, ReconException.match_id.in_(list(match_ids)))
        .all()
    )
    for exception in exceptions:
        previous = exception.status
        exception.previous_status = previous
        exception.status = status
        exception.resolution_reason = reason
        exception.updated_at = _now()
        exception.resolved_at = _now() if status in RESOLVED_EXCEPTION_STATUSES else None
        _audit(
            session,
            run_id,
            action,
            actor=actor,
            match_id=exception.match_id,
            exception_id=exception.id,
            previous_status=previous,
            new_status=status,
            reason=reason,
        )


def accept_match(match_id: int, reason: str, actor: str | None = None) -> dict:
    reason = _require_reason(reason, "accept a match")
    session = get_session()
    try:
        match = session.get(ReconMatch, int(match_id))
        if match is None:
            raise ValueError("That reconciliation row was not found.")
        if match.is_superseded:
            raise ValueError("This row was superseded by a later decision.")
        if not match.left_records_json or not match.right_records_json:
            raise ValueError("Both sides need a record before a match can be accepted.")
        if _json_load(match.left_records_json, []) == [] or _json_load(match.right_records_json, []) == []:
            raise ValueError("Both sides need a record before a match can be accepted.")
        if match.status in {"duplicate"}:
            raise ValueError("Duplicate rows must be resolved by choosing the genuine record, not by accepting the duplicate.")
        if match.classification == "reversal_candidate":
            raise ValueError(
                "A reversal candidate needs evidence and an exception decision; it cannot be accepted as a normal match."
            )
        previous = match.status
        match.status = "accepted"
        match.requires_review = 0
        match.decided_by = _actor(actor)
        match.decided_at = _now()
        match.decision_reason = reason
        match.updated_at = _now()
        _resolve_linked_exceptions(
            session,
            match.run_id,
            [match.id],
            actor=_actor(actor),
            reason=reason,
            action="match_accepted",
        )
        _audit(
            session,
            match.run_id,
            "match_accepted",
            actor=_actor(actor),
            match_id=match.id,
            previous_status=previous,
            new_status="accepted",
            reason=reason,
            record_refs=[
                *_json_load(match.left_row_ids_json, []),
                *_json_load(match.right_row_ids_json, []),
            ],
        )
        run = session.get(ReconRun, match.run_id)
        if run is not None:
            _refresh_run_summary(session, run)
        session.commit()
        session.refresh(match)
        return _decode(match)
    finally:
        session.close()


def _release_match(
    session,
    match: ReconMatch,
    *,
    actor: str,
    reason: str,
    action: str,
    new_status: str = "rejected",
) -> None:
    run = session.get(ReconRun, match.run_id)
    if run is None:
        raise ValueError("That reconciliation run was not found.")
    left = _json_load(match.left_records_json, [])
    right = _json_load(match.right_records_json, [])
    previous = match.status
    match.is_superseded = 1
    match.status = new_status
    match.requires_review = 1
    match.decided_by = _actor(actor)
    match.decided_at = _now()
    match.decision_reason = reason
    match.updated_at = _now()
    _resolve_linked_exceptions(
        session,
        match.run_id,
        [match.id],
        actor=_actor(actor),
        reason=reason,
        action=action,
        status="resolved",
    )
    released_ids = []
    for side, records in (("left", left), ("right", right)):
        for record in records:
            row_id = record.get("row_id")
            released_ids.append(row_id)
            released = ReconMatch(
                run_id=run.id,
                ordinal=int(match.ordinal or 0),
                classification="unmatched",
                status="unmatched",
                match_type="none",
                confidence=0,
                requires_review=1,
                reason_code="released_from_rejected_match",
                explanation=f"Released after {action.replace('_', ' ')}: {reason}",
                matched_fields_json="[]",
                differences_json=_json_dump(
                    {"amount": record.get("amount"), "date_days": None}
                ),
                tolerances_json="[]",
                exception_categories_json=_json_dump(["unmatched_transaction"]),
                left_records_json=_json_dump([record] if side == "left" else []),
                right_records_json=_json_dump([record] if side == "right" else []),
                left_row_ids_json=_json_dump([row_id] if side == "left" and row_id else []),
                right_row_ids_json=_json_dump([row_id] if side == "right" and row_id else []),
                left_amount=float(record.get("amount") or 0) if side == "left" else None,
                right_amount=float(record.get("amount") or 0) if side == "right" else None,
                currency=record.get("currency") or None,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(released)
            session.flush()
            if row_id:
                session.add(
                    ReconRecordLink(
                        run_id=run.id,
                        match_id=released.id,
                        side=side,
                        row_id=row_id,
                        record_json=_json_dump(record),
                        created_at=_now(),
                    )
                )
            _create_exception(
                session,
                run,
                released,
                "unmatched_transaction",
                amount=record.get("amount"),
                currency=record.get("currency"),
                source_refs=_source_refs([record]),
                description=f"Released after {action.replace('_', ' ')}: {reason}",
            )
    _audit(
        session,
        match.run_id,
        action,
        actor=_actor(actor),
        match_id=match.id,
        previous_status=previous,
        new_status=new_status,
        reason=reason,
        record_refs=[item for item in released_ids if item is not None],
    )
    _refresh_run_summary(session, run)


def reject_match(match_id: int, reason: str, actor: str | None = None) -> dict:
    reason = _require_reason(reason, "reject a match")
    session = get_session()
    try:
        match = session.get(ReconMatch, int(match_id))
        if match is None:
            raise ValueError("That reconciliation row was not found.")
        if match.is_superseded:
            raise ValueError("This row was already superseded.")
        if match.status in {"unmatched", "duplicate"}:
            raise ValueError("Use the exception workflow to resolve this row.")
        _release_match(session, match, actor=_actor(actor), reason=reason, action="match_rejected")
        session.commit()
        return {"ok": True, "match_id": match.id, "status": "rejected"}
    finally:
        session.close()


def unmatch(match_id: int, reason: str, actor: str | None = None) -> dict:
    reason = _require_reason(reason, "unmatch records")
    session = get_session()
    try:
        match = session.get(ReconMatch, int(match_id))
        if match is None:
            raise ValueError("That reconciliation row was not found.")
        if match.is_superseded:
            raise ValueError("This row was already superseded.")
        _release_match(session, match, actor=_actor(actor), reason=reason, action="match_unmatched")
        session.commit()
        return {"ok": True, "match_id": match.id, "status": "unmatched"}
    finally:
        session.close()


def manual_match(payload: Mapping[str, Any], actor: str | None = None) -> dict:
    run_id = _as_int(payload.get("run_id"))
    if not run_id:
        raise ValueError("Choose a reconciliation run.")
    reason = _require_reason(payload.get("reason"), "match records manually")
    left_ids = _int_list(payload.get("left_ids") or payload.get("left_row_ids"))
    right_ids = _int_list(payload.get("right_ids") or payload.get("right_row_ids"))
    if not left_ids or not right_ids:
        raise ValueError("Choose at least one record on each side.")
    if len(set(left_ids) & set(right_ids)) > 0:
        raise ValueError("A record cannot appear on both sides.")
    allocations = payload.get("allocations") or []
    session = get_session()
    try:
        run = session.get(ReconRun, run_id)
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        links = (
            session.query(ReconRecordLink)
            .join(ReconMatch, ReconRecordLink.match_id == ReconMatch.id)
            .filter(
                ReconRecordLink.run_id == run.id,
                ReconRecordLink.row_id.in_([*left_ids, *right_ids]),
                ReconMatch.is_superseded == 0,
            )
            .all()
        )
        by_row = {link.row_id: link for link in links}
        missing = [row_id for row_id in [*left_ids, *right_ids] if row_id not in by_row]
        if missing:
            raise ValueError(
                "Some selected records no longer exist in this run. Refresh the workbench."
            )
        old_match_ids: set[int] = set()
        for row_id in left_ids:
            link = by_row[row_id]
            if link.side != "left":
                raise ValueError("A selected record is on the wrong side of the comparison.")
            old = session.get(ReconMatch, link.match_id)
            if old is not None and old.status in MATCHED_STATUSES:
                raise ValueError(
                    "One of the selected records is already accepted or matched. Unmatch it first."
                )
            old_match_ids.add(link.match_id)
        for row_id in right_ids:
            link = by_row[row_id]
            if link.side != "right":
                raise ValueError("A selected record is on the wrong side of the comparison.")
            old = session.get(ReconMatch, link.match_id)
            if old is not None and old.status in MATCHED_STATUSES:
                raise ValueError(
                    "One of the selected records is already accepted or matched. Unmatch it first."
                )
            old_match_ids.add(link.match_id)
        selected_ids = set(left_ids) | set(right_ids)
        for old_id in old_match_ids:
            old = session.get(ReconMatch, old_id)
            if old is None:
                continue
            old_ids = {
                *_json_load(old.left_row_ids_json, []),
                *_json_load(old.right_row_ids_json, []),
            }
            if not old_ids.issubset(selected_ids):
                raise ValueError(
                    "This record belongs to a split/aggregation row. Select the complete row or unmatch it before building a new manual match."
                )
        left_records = [_json_load(by_row[row_id].record_json, {}) for row_id in left_ids]
        right_records = [_json_load(by_row[row_id].record_json, {}) for row_id in right_ids]
        left_total = sum(float(record.get("amount") or 0) for record in left_records)
        right_total = sum(float(record.get("amount") or 0) for record in right_records)
        if (len(left_ids) > 1 or len(right_ids) > 1) and not allocations:
            raise ValueError(
                "Provide an allocation for a split or aggregation match so no record is double-counted."
            )
        if allocations:
            _validate_allocations(
                allocations, left_ids, right_ids, left_total, right_total
            )
        config = normalise_rules(
            _json_load(run.rules_snapshot_json, {}).get("config") or {}
        )
        comparison = compare_pair(left_records, right_records, config)
        differences = comparison.get("differences") or {}
        if allocations:
            allocated_total = sum(float(item.get("amount") or 0) for item in allocations)
            differences["amount"] = round(abs(left_total - right_total), 2)
            differences["allocated_total"] = round(allocated_total, 2)
        previous_status = "proposed" if old_match_ids else "unmatched"
        for old_id in old_match_ids:
            old = session.get(ReconMatch, old_id)
            if old is None:
                continue
            old.is_superseded = 1
            old.status = "superseded"
            old.updated_at = _now()
        _resolve_linked_exceptions(
            session,
            run.id,
            list(old_match_ids),
            actor=_actor(actor),
            reason=f"Superseded by manual match: {reason}",
            action="manual_match_superseded",
            status="resolved",
        )
        match = ReconMatch(
            run_id=run.id,
            ordinal=0,
            classification="manual",
            status="manual",
            match_type="manual_allocation" if allocations else "manual",
            confidence=100,
            requires_review=0,
            reason_code="manual_decision",
            explanation=(
                f"Manually matched by {_actor(actor)}. Reason: {reason}. "
                "Source values were not modified."
            ),
            matched_fields_json=_json_dump(comparison.get("matched_fields") or []),
            differences_json=_json_dump(differences),
            tolerances_json=_json_dump(comparison.get("tolerances") or []),
            exception_categories_json="[]",
            allocations_json=_json_dump(allocations),
            candidates_json="[]",
            left_records_json=_json_dump(left_records),
            right_records_json=_json_dump(right_records),
            left_row_ids_json=_json_dump(left_ids),
            right_row_ids_json=_json_dump(right_ids),
            left_amount=left_total,
            right_amount=right_total,
            difference_amount=round(abs(left_total - right_total), 2),
            currency=(
                left_records[0].get("currency") or right_records[0].get("currency") or None
            ),
            decided_by=_actor(actor),
            decided_at=_now(),
            decision_reason=reason,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(match)
        session.flush()
        for side, records in (("left", left_records), ("right", right_records)):
            for record in records:
                row_id = record.get("row_id")
                session.add(
                    ReconRecordLink(
                        run_id=run.id,
                        match_id=match.id,
                        side=side,
                        row_id=row_id,
                        record_json=_json_dump(record),
                        created_at=_now(),
                    )
                )
        if abs(left_total - right_total) > float(config["amount_tolerance"]):
            _create_exception(
                session,
                run,
                match,
                "amount_mismatch",
                amount=abs(left_total - right_total),
                currency=match.currency,
                source_refs=_source_refs([*left_records, *right_records]),
                description=(
                    f"Manual match accepted with a difference of ₹{abs(left_total - right_total):,.2f}. "
                    f"Reason: {reason}"
                ),
                status="resolved",
                resolution_reason=reason,
            )
        if allocations:
            _create_exception(
                session,
                run,
                match,
                "allocation_required",
                amount=max(left_total, right_total),
                currency=match.currency,
                source_refs=_source_refs([*left_records, *right_records]),
                description=f"Manual allocation accepted. Reason: {reason}",
                status="resolved",
                resolution_reason=reason,
            )
        _audit(
            session,
            run.id,
            "manual_match",
            actor=_actor(actor),
            match_id=match.id,
            previous_status=previous_status,
            new_status="manual",
            reason=reason,
            record_refs=[*left_ids, *right_ids],
            evidence_refs=payload.get("evidence_refs") or [],
        )
        _refresh_run_summary(session, run)
        session.commit()
        session.refresh(match)
        return _decode(match)
    finally:
        session.close()


def _int_list(values: Any) -> list[int]:
    if not isinstance(values, (list, tuple, set)):
        return []
    cleaned = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number and number not in cleaned:
            cleaned.append(number)
    return cleaned


def _validate_allocations(
    allocations: Sequence[Mapping],
    left_ids: Sequence[int],
    right_ids: Sequence[int],
    left_total: float,
    right_total: float,
) -> None:
    if not isinstance(allocations, Sequence) or isinstance(allocations, (str, bytes)):
        raise ValueError("The allocation must be a list.")
    seen_left: set[int] = set()
    seen_right: set[int] = set()
    seen_pairs: set[tuple[int, int]] = set()
    allocated = 0.0
    for index, item in enumerate(allocations):
        if not isinstance(item, Mapping):
            raise ValueError(f"Allocation {index + 1} is not valid.")
        left_id = _as_int(item.get("left_id"))
        right_id = _as_int(item.get("right_id"))
        amount = _as_float(item.get("amount"))
        if left_id not in left_ids or right_id not in right_ids:
            raise ValueError("Every allocation must reference selected records on both sides.")
        if amount is None or amount <= 0:
            raise ValueError("Every allocation needs a positive amount.")
        pair = (int(left_id), int(right_id))
        if pair in seen_pairs:
            raise ValueError("The same allocation pair appears more than once.")
        seen_pairs.add(pair)
        seen_left.add(left_id)
        seen_right.add(right_id)
        allocated += amount
    if seen_left != set(left_ids) or seen_right != set(right_ids):
        raise ValueError("Every selected record must appear in the allocation.")
    limit = min(left_total, right_total)
    tolerance = 1.0
    if allocated > limit + tolerance:
        raise ValueError(
            f"The allocated total ₹{allocated:,.2f} exceeds the smaller side ₹{limit:,.2f}."
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def get_exceptions(filters: Mapping[str, Any] | None = None) -> dict:
    filters = filters or {}
    page = max(1, int(filters.get("page") or 1))
    page_size = min(500, max(10, int(filters.get("page_size") or 100)))
    session = get_session()
    try:
        query = session.query(ReconException, ReconRun).join(
            ReconRun, ReconException.run_id == ReconRun.id
        )
        run_id = _as_int(filters.get("run_id"))
        if run_id:
            query = query.filter(ReconException.run_id == run_id)
        status = str(filters.get("status") or "").strip()
        if status == "outstanding":
            query = query.filter(
                ReconException.status.notin_(list(RESOLVED_EXCEPTION_STATUSES))
            )
        elif status:
            query = query.filter(ReconException.status == status)
        category = str(filters.get("category") or "").strip()
        if category:
            query = query.filter(ReconException.category == category)
        assigned_to = str(filters.get("assigned_to") or "").strip()
        if assigned_to:
            query = query.filter(ReconException.assigned_to == assigned_to)
        client_id = _as_int(filters.get("client_id"))
        if client_id:
            query = query.filter(ReconRun.client_id == client_id)
        period_id = _as_int(filters.get("period_id"))
        if period_id:
            query = query.filter(ReconRun.period_id == period_id)
        financial_year_value = str(filters.get("financial_year") or "").strip()
        if financial_year_value:
            query = query.filter(ReconRun.financial_year == financial_year_value)
        workflow_id = str(filters.get("workflow_id") or "").strip()
        if workflow_id:
            query = query.filter(ReconRun.workflow_id == workflow_id)
        search = str(filters.get("search") or "").strip()
        if search:
            needle = f"%{search}%"
            query = query.filter(
                or_(
                    ReconException.title.ilike(needle),
                    ReconException.description.ilike(needle),
                    ReconRun.client_name.ilike(needle),
                    ReconRun.run_uuid.ilike(needle),
                )
            )
        total = int(query.count())
        rows = (
            query.order_by(
                ReconException.status.asc(),
                ReconException.amount.desc(),
                ReconException.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "exceptions": [
                {
                    **_decode_exception(exception),
                    "run_uuid": run.run_uuid,
                    "client_id": run.client_id,
                    "client_name": run.client_name,
                    "period_id": run.period_id,
                    "period_label": run.period_label,
                    "financial_year": run.financial_year,
                    "workflow_id": run.workflow_id,
                    "workflow_label": run.workflow_label,
                }
                for exception, run in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "filters": recon_filter_options(session),
        }
    finally:
        session.close()


def get_exception_detail(exception_id: int) -> dict:
    session = get_session()
    try:
        exception = session.get(ReconException, int(exception_id))
        if exception is None:
            raise ValueError("That exception was not found.")
        run = session.get(ReconRun, exception.run_id)
        match = session.get(ReconMatch, exception.match_id) if exception.match_id else None
        events = (
            session.query(ReconAuditEvent)
            .filter(
                or_(
                    ReconAuditEvent.exception_id == exception.id,
                    ReconAuditEvent.match_id
                    == (exception.match_id if exception.match_id else -1),
                )
            )
            .order_by(ReconAuditEvent.created_at.desc(), ReconAuditEvent.id.desc())
            .all()
        )
        return {
            "exception": _decode_exception(exception),
            "run": _decode_run(run) if run else {},
            "match": _match_row_payload(match) if match else None,
            "audit": [_decode_audit(event) for event in events],
        }
    finally:
        session.close()


def update_exception(payload: Mapping[str, Any], actor: str | None = None) -> dict:
    exception_id = _as_int(payload.get("id") or payload.get("exception_id"))
    if not exception_id:
        raise ValueError("Choose an exception.")
    reason = str(payload.get("reason") or "").strip()
    new_status = str(payload.get("status") or "").strip()
    assigned_to = payload.get("assigned_to")
    evidence = payload.get("evidence")
    if new_status and new_status not in EXCEPTION_STATUSES:
        raise ValueError("That exception status is not available.")
    if new_status and not reason:
        raise ValueError("Record a reason before changing an exception status.")
    session = get_session()
    try:
        exception = session.get(ReconException, exception_id)
        if exception is None:
            raise ValueError("That exception was not found.")
        previous = exception.status
        changed = False
        if new_status and new_status != previous:
            exception.previous_status = previous
            exception.status = new_status
            exception.resolved_at = _now() if new_status in RESOLVED_EXCEPTION_STATUSES else None
            exception.resolution_reason = reason or exception.resolution_reason
            changed = True
        if assigned_to is not None:
            exception.assigned_to = str(assigned_to or "").strip() or None
            changed = True
        if evidence is not None:
            existing = _json_load(exception.evidence_json, [])
            if isinstance(evidence, Mapping):
                existing.append(dict(evidence))
            elif isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes)):
                existing.extend(evidence)
            exception.evidence_json = _json_dump(existing)
            changed = True
        if reason:
            exception.resolution_reason = reason
        exception.updated_at = _now()
        _audit(
            session,
            exception.run_id,
            "exception_updated",
            actor=_actor(actor),
            match_id=exception.match_id,
            exception_id=exception.id,
            previous_status=previous,
            new_status=exception.status,
            reason=reason or (
                f"Assigned to {exception.assigned_to}" if assigned_to is not None else "Evidence updated"
            ),
            evidence_refs=evidence if isinstance(evidence, list) else ([evidence] if evidence else []),
        )
        if exception.match_id and new_status in {"timing_difference", "approved_adjustment"}:
            match = session.get(ReconMatch, exception.match_id)
            if match is not None:
                match.status = new_status
                match.requires_review = 0
                match.decided_by = _actor(actor)
                match.decided_at = _now()
                match.decision_reason = reason
                match.updated_at = _now()
        if exception.match_id and new_status in {"reopened", "investigating", "open"}:
            match = session.get(ReconMatch, exception.match_id)
            if match is not None and match.status in {
                "accepted",
                "manual",
                "timing_difference",
                "approved_adjustment",
            }:
                match.status = "proposed"
                match.requires_review = 1
                match.updated_at = _now()
        run = session.get(ReconRun, exception.run_id)
        if run is not None:
            _refresh_run_summary(session, run)
        session.commit()
        session.refresh(exception)
        return _decode_exception(exception)
    finally:
        session.close()


def add_exception_note(payload: Mapping[str, Any], actor: str | None = None) -> dict:
    exception_id = _as_int(payload.get("exception_id") or payload.get("id"))
    note = str(payload.get("note") or payload.get("reason") or "").strip()
    if not exception_id:
        raise ValueError("Choose an exception.")
    if len(note) < 2:
        raise ValueError("Write a note before saving it.")
    session = get_session()
    try:
        exception = session.get(ReconException, exception_id)
        if exception is None:
            raise ValueError("That exception was not found.")
        _audit(
            session,
            exception.run_id,
            "note_added",
            actor=_actor(actor),
            match_id=exception.match_id,
            exception_id=exception.id,
            previous_status=exception.status,
            new_status=exception.status,
            reason=note,
            evidence_refs=payload.get("evidence_refs") or [],
        )
        exception.updated_at = _now()
        session.commit()
        return {"ok": True, "exception_id": exception.id}
    finally:
        session.close()


def add_match_note(payload: Mapping[str, Any], actor: str | None = None) -> dict:
    match_id = _as_int(payload.get("match_id") or payload.get("id"))
    note = str(payload.get("note") or payload.get("reason") or "").strip()
    if not match_id:
        raise ValueError("Choose a reconciliation row.")
    if len(note) < 2:
        raise ValueError("Write a note before saving it.")
    session = get_session()
    try:
        match = session.get(ReconMatch, match_id)
        if match is None:
            raise ValueError("That reconciliation row was not found.")
        _audit(
            session,
            match.run_id,
            "note_added",
            actor=_actor(actor),
            match_id=match.id,
            previous_status=match.status,
            new_status=match.status,
            reason=note,
            evidence_refs=payload.get("evidence_refs") or [],
        )
        match.updated_at = _now()
        session.commit()
        return {"ok": True, "match_id": match.id}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------


def rerun(run_id: int, actor: str | None = None, *, background: bool = True) -> dict:
    session = get_session()
    try:
        run = session.get(ReconRun, int(run_id))
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        return start_reconciliation(
            run.period_id,
            run.workflow_id,
            ruleset_id=run.ruleset_id,
            actor=actor,
            background=background,
            parent_run_id=run.id,
        )
    finally:
        session.close()


def compare_runs(run_a: int, run_b: int) -> dict:
    session = get_session()
    try:
        first = session.get(ReconRun, int(run_a))
        second = session.get(ReconRun, int(run_b))
        if first is None or second is None:
            raise ValueError("Both reconciliation runs are needed for a comparison.")
        if first.period_id != second.period_id or first.workflow_id != second.workflow_id:
            raise ValueError("Compare runs from the same period and workflow.")
        first_map = _record_status_map(session, first.id)
        second_map = _record_status_map(session, second.id)
        changed = []
        for key in sorted(set(first_map) | set(second_map)):
            left = first_map.get(key)
            right = second_map.get(key)
            if left == right:
                continue
            if left is None:
                change = "added"
            elif right is None:
                change = "removed"
            else:
                change = "changed"
            changed.append(
                {
                    "key": key,
                    "change": change,
                    "before": left,
                    "after": right,
                }
            )
        return {
            "run_a": _decode_run(first),
            "run_b": _decode_run(second),
            "counts_delta": _delta(
                _json_load(first.counts_json, {}), _json_load(second.counts_json, {})
            ),
            "totals_delta": _delta(
                _json_load(first.totals_json, {}), _json_load(second.totals_json, {})
            ),
            "changes": changed[:1000],
            "change_count": len(changed),
            "added": sum(1 for item in changed if item["change"] == "added"),
            "removed": sum(1 for item in changed if item["change"] == "removed"),
            "changed": sum(1 for item in changed if item["change"] == "changed"),
        }
    finally:
        session.close()


def _record_status_map(session, run_id: int) -> dict[str, dict]:
    links = (
        session.query(ReconRecordLink, ReconMatch)
        .join(ReconMatch, ReconRecordLink.match_id == ReconMatch.id)
        .filter(
            ReconRecordLink.run_id == run_id,
            ReconMatch.is_superseded == 0,
        )
        .all()
    )
    result = {}
    for link, match in links:
        if link.row_id:
            key = f"{link.side}:row:{link.row_id}"
        else:
            payload = _json_load(link.record_json, {})
            reference = payload.get("reference") or payload.get("account") or "aggregate"
            key = f"{link.side}:ref:{reference}"
        result[key] = {
            "status": match.status,
            "classification": match.classification,
            "confidence": match.confidence,
        }
    return result


def _delta(before: Mapping, after: Mapping) -> dict:
    keys = sorted(set(before) | set(after))
    changes = {}
    for key in keys:
        left = before.get(key)
        right = after.get(key)
        if left == right:
            continue
        if isinstance(left, (int, float)) or isinstance(right, (int, float)):
            try:
                changes[key] = round(float(right or 0) - float(left or 0), 2)
                continue
            except (TypeError, ValueError):
                pass
        changes[key] = {"before": left, "after": right}
    return changes


def run_audit(run_id: int) -> dict:
    session = get_session()
    try:
        run = session.get(ReconRun, int(run_id))
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        events = (
            session.query(ReconAuditEvent)
            .filter(ReconAuditEvent.run_id == run.id)
            .order_by(ReconAuditEvent.created_at.desc(), ReconAuditEvent.id.desc())
            .all()
        )
        return {"run": _decode_run(run), "events": [_decode_audit(event) for event in events]}
    finally:
        session.close()


def review_workload() -> dict:
    session = get_session()
    try:
        rows = (
            session.query(ReconException.assigned_to, func.count(ReconException.id))
            .filter(ReconException.status.notin_(list(RESOLVED_EXCEPTION_STATUSES)))
            .group_by(ReconException.assigned_to)
            .order_by(func.count(ReconException.id).desc())
            .all()
        )
        return {
            "reviewers": [
                {"name": name or "Unassigned", "count": int(count)}
                for name, count in rows
            ]
        }
    finally:
        session.close()
