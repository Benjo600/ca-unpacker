from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from apps.engine.library import acquire_library_lock, get_db_path, init_library, release_library_lock


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Firm(Base):
    __tablename__ = "firms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    library_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    firm_id: Mapped[int] = mapped_column(ForeignKey("firms.id"))
    name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    profession_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    profession_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gst_registered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_json: Mapped[str] = mapped_column(
        String, default="{}", server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    label: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    intake_discovered_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    intake_accepted_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoredFile(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"))
    original_name: Mapped[str] = mapped_column(String(260))
    mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(500))
    detected_kind: Mapped[str] = mapped_column(String(20), default="unknown")
    override_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    classify_reason: Mapped[str] = mapped_column(String(300), default="")
    parse_outcome: Mapped[str] = mapped_column(
        String(20), default="unclassified", server_default=text("'unclassified'")
    )
    parse_reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parse_reason_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parse_row_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    parse_warnings_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    parser_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    currency_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency_candidates_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    currency_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency_override: Mapped[str | None] = mapped_column(String(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExtractedRow(Base):
    __tablename__ = "extracted_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"))
    kind: Mapped[str] = mapped_column(String(20))
    payload_json: Mapped[str] = mapped_column(String)
    source_page: Mapped[int] = mapped_column(Integer, default=1)
    source_bbox: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validation_flags: Mapped[str] = mapped_column(String, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataPack(Base):
    __tablename__ = "data_packs"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    bank_xlsx_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    balance_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconRuleSet(Base):
    __tablename__ = "recon_rule_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    workflow_id: Mapped[str] = mapped_column(String(60), default="*")
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_default: Mapped[int] = mapped_column(Integer, default=1)
    config_json: Mapped[str] = mapped_column(String, default="{}", server_default=text("'{}'"))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconRun(Base):
    __tablename__ = "recon_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_uuid: Mapped[str] = mapped_column(String(40), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(String(60), index=True)
    workflow_label: Mapped[str] = mapped_column(String(160), default="")
    client_name: Mapped[str] = mapped_column(String(200), default="")
    period_label: Mapped[str] = mapped_column(String(80), default="")
    financial_year: Mapped[str] = mapped_column(String(20), default="", index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    completion_status: Mapped[str] = mapped_column(
        String(30), default="in_progress", index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    source_dataset_ids_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    source_files_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    ruleset_id: Mapped[int | None] = mapped_column(
        ForeignKey("recon_rule_sets.id"), nullable=True
    )
    ruleset_version: Mapped[int] = mapped_column(Integer, default=1)
    rules_snapshot_json: Mapped[str] = mapped_column(
        String, default="{}", server_default=text("'{}'")
    )
    counts_json: Mapped[str] = mapped_column(
        String, default="{}", server_default=text("'{}'")
    )
    totals_json: Mapped[str] = mapped_column(
        String, default="{}", server_default=text("'{}'")
    )
    checks_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("recon_runs.id"), nullable=True
    )
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconMatch(Base):
    __tablename__ = "recon_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recon_runs.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0, index=True)
    classification: Mapped[str] = mapped_column(String(30), default="review", index=True)
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    match_type: Mapped[str] = mapped_column(String(30), default="none")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    requires_review: Mapped[int] = mapped_column(Integer, default=1)
    reason_code: Mapped[str] = mapped_column(String(80), default="")
    explanation: Mapped[str] = mapped_column(String(2000), default="")
    matched_fields_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    differences_json: Mapped[str] = mapped_column(
        String, default="{}", server_default=text("'{}'")
    )
    tolerances_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    exception_categories_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    allocations_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    candidates_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    left_records_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    right_records_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    left_row_ids_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    right_row_ids_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    left_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    right_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    difference_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_superseded: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconRecordLink(Base):
    __tablename__ = "recon_record_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recon_runs.id"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("recon_matches.id"), index=True)
    side: Mapped[str] = mapped_column(String(10), default="left")
    row_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    record_json: Mapped[str] = mapped_column(
        String, default="{}", server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconException(Base):
    __tablename__ = "recon_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recon_runs.id"), index=True)
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("recon_matches.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(60), default="unmatched_transaction", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(String(2000), default="")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    resolution_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_refs_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReconAuditEvent(Base):
    __tablename__ = "recon_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recon_runs.id"), index=True)
    match_id: Mapped[int | None] = mapped_column(
        ForeignKey("recon_matches.id"), nullable=True, index=True
    )
    exception_id: Mapped[int | None] = mapped_column(
        ForeignKey("recon_exceptions.id"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(200), default="local user")
    action: Mapped[str] = mapped_column(String(60), default="update", index=True)
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    record_refs_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    evidence_refs_json: Mapped[str] = mapped_column(
        String, default="[]", server_default=text("'[]'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engine = None
SessionLocal = None


def reset_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None
    release_library_lock()


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        init_library()
        acquire_library_lock()
        _engine = create_engine(
            f"sqlite:///{get_db_path()}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        from apps.engine.migrations import ensure_schema

        try:
            ensure_schema(_engine, Base.metadata)
        except BaseException:
            _engine.dispose()
            _engine = None
            release_library_lock()
            raise
        SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session():
    get_engine()
    assert SessionLocal is not None
    return SessionLocal()
