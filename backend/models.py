from sqlalchemy import Column, String, DateTime, Integer, Enum, Float, ForeignKey, Text, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from uuid import uuid4
from database import Base

class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# ── Multi-Tenant Model ────────────────────────────────────────────────────────

class Tenant(Base):
    """
    Top-level org/firm record. Every user and every batch belongs to a tenant.
    A CA firm onboarding as a client gets one Tenant row.
    """
    __tablename__ = "tenants"

    id         = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name       = Column(String, nullable=False)
    slug       = Column(String, unique=True, nullable=False, index=True)  # e.g. "sharma-associates"
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # GSTR-2B gap-trigger destination + policy (see Gstr2bGapTrigger / services/gstr2b_trigger_engine.py).
    # One contact email per tenant for now — matches the per-tenant granularity
    # already used by GoogleDriveSyncConfig, revisit per-GSTIN only if a client
    # with multiple registrations actually needs split contacts.
    client_contact_email          = Column(String, nullable=True)
    auto_vendor_followup_enabled  = Column(Boolean, default=False, nullable=False)
    # Bucket A ("not_in_books" client requests) default to accountant-gated
    # (True) per the confirmed human-gated-outbound rule. A firm can flip this
    # off to auto-approve Bucket A requests the same way Bucket B already
    # auto-sends — see services/gstr2b_trigger_engine.sync_gap_triggers.
    bucket_a_require_review       = Column(Boolean, default=True, nullable=False)

    users = relationship("User", back_populates="tenant")
    batches = relationship("BatchJob", back_populates="tenant")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id         = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_files= Column(Integer, default=0)
    status     = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    user_id    = Column(String, ForeignKey("users.id"), nullable=True)
    tenant_id  = Column(String, ForeignKey("tenants.id"), nullable=True, index=True)

    tasks  = relationship("InvoiceTask", back_populates="batch", cascade="all, delete-orphan")
    tenant = relationship("Tenant", back_populates="batches")

class InvoiceTask(Base):
    __tablename__ = "invoice_tasks"
    
    id = Column(String, primary_key=True, index=True)
    batch_id = Column(String, ForeignKey("batch_jobs.id"))
    file_name = Column(String)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    error_message = Column(String, nullable=True)
    invoice_type = Column(String) # "Sales", "Purchase", or "both"
    created_at = Column(DateTime, default=datetime.utcnow)
    # Phase 4A: Reconciliation audit fields
    recon_status = Column(String, nullable=True)         # ERP_READY | NEEDS_REVIEW | BLOCKED
    recon_report_json = Column(Text, nullable=True)      # Full ReconciliationReport as JSON
    
    batch = relationship("BatchJob", back_populates="tasks")
    sales_items = relationship("SalesLineItem", back_populates="task", cascade="all, delete-orphan")
    purchase_items = relationship("PurchaseLineItem", back_populates="task", cascade="all, delete-orphan")

class SalesLineItem(Base):
    __tablename__ = "sales_line_items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(String, ForeignKey("invoice_tasks.id"))
    
    voucher_date = Column(String, nullable=True)
    voucher_type = Column(String, nullable=True)
    invoice_no = Column(String, nullable=True)
    party_ledger_name = Column(String, nullable=True)
    party_gstin = Column(String, nullable=True)
    place_of_supply = Column(String, nullable=True)
    particulars = Column(String, nullable=True)
    hsn = Column(String, nullable=True)
    qty = Column(Float, nullable=True)
    rate = Column(Float, nullable=True)
    taxable_value = Column(Float, nullable=True)
    discount = Column(Float, nullable=True)
    advances = Column(Float, nullable=True)
    cgst_amount = Column(Float, nullable=True)
    sgst_amount = Column(Float, nullable=True)
    igst_amount = Column(Float, nullable=True)
    total_invoice_value = Column(Float, nullable=True)
    gstr1_category = Column(String, nullable=True)
    narration = Column(String, nullable=True)
    
    task = relationship("InvoiceTask", back_populates="sales_items")

class PurchaseLineItem(Base):
    __tablename__ = "purchase_line_items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(String, ForeignKey("invoice_tasks.id"))
    
    voucher_date = Column(String, nullable=True)
    voucher_type = Column(String, nullable=True)
    invoice_no = Column(String, nullable=True)
    party_ledger_name = Column(String, nullable=True)
    party_gstin = Column(String, nullable=True)
    place_of_supply = Column(String, nullable=True)
    particulars = Column(String, nullable=True)
    hsn = Column(String, nullable=True)
    qty = Column(Float, nullable=True)
    rate = Column(Float, nullable=True)
    taxable_value = Column(Float, nullable=True)
    cgst_amount = Column(Float, nullable=True)
    sgst_amount = Column(Float, nullable=True)
    igst_amount = Column(Float, nullable=True)
    total_invoice_value = Column(Float, nullable=True)
    itc_eligibility = Column(String, nullable=True)
    narration = Column(String, nullable=True)
    
    task = relationship("InvoiceTask", back_populates="purchase_items")


# ── Observability Layer ────────────────────────────────────────────────────────

class ObservabilityLog(Base):
    """
    Append-only audit log for every pipeline event in the observability layer.
    Never updated — corrections are new rows referencing original_file_id.
    Retained for 7 years per CGST Act Section 36.
    """
    __tablename__ = "observability_logs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id        = Column(String, index=True, nullable=True)   # for per-tenant cost aggregation
    # Correlation IDs — mandatory on every row
    batch_id         = Column(String, index=True, nullable=False)
    file_id          = Column(String, index=True, nullable=True)   # null for batch-level events
    # Event classification
    event_type       = Column(String, index=True, nullable=False)  # e.g. batch_received, system_flag, extraction_quality_score
    stage            = Column(String, nullable=True)               # e.g. file_intake, llm_extraction
    severity         = Column(String, nullable=True)               # CRITICAL | HIGH | MEDIUM | LOW | null
    flag_id          = Column(String, nullable=True, index=True)   # e.g. NUMBER_HALLUCINATION_SUSPECTED
    # Payload
    payload_json     = Column(Text, nullable=False)                # Full structured JSON blob
    # Context
    prompt_version   = Column(String, nullable=True)
    model_identifier = Column(String, nullable=True)
    api_provider     = Column(String, nullable=True)
    # Timestamps
    timestamp_utc    = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    # Replay / fix linkage
    original_file_id = Column(String, nullable=True)  # set on replay rows
    fix_id           = Column(String, nullable=True)
    is_replay        = Column(Boolean, default=False)


class TallyConnectionConfig(Base):
    """
    Per-tenant TallyPrime connection settings (host/port/company), so the
    "Push to Tally" modal doesn't need host/port/company retyped on every
    use. Same upsert pattern as GoogleDriveSyncConfig — one row per tenant.

    Auto-saved by the push endpoint after a successful connectivity test
    (see main.py's push_batch_to_tally) rather than requiring a separate
    "save config" step — the first successful push remembers itself.
    """
    __tablename__ = "tally_connection_configs"

    tenant_id  = Column(String, ForeignKey("tenants.id"), primary_key=True)
    host       = Column(String, nullable=False)
    port       = Column(Integer, default=9000, nullable=False)
    company    = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TallyPushLog(Base):
    """
    Append-only record of every Tally voucher push attempt — the idempotency
    ledger for services/tally_connector.py. One row per (item_type, item_id)
    per attempt; never updated, only inserted (same pattern as ObservabilityLog).

    Before pushing a line item, the endpoint checks for an existing row with
    status="success" for that (item_type, item_id) and skips it if found —
    prevents duplicate vouchers in Tally on a retried/re-run batch push.
    """
    __tablename__ = "tally_push_logs"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id          = Column(String, index=True, nullable=True)
    batch_id           = Column(String, index=True, nullable=False)
    task_id            = Column(String, index=True, nullable=False)
    item_type          = Column(String, nullable=False)   # "sales" | "purchase"
    item_id            = Column(Integer, index=True, nullable=False)  # SalesLineItem.id / PurchaseLineItem.id
    voucher_type       = Column(String, nullable=False)   # "Sales" | "Purchase"
    invoice_no         = Column(String, nullable=True)
    status             = Column(String, nullable=False)   # "success" | "failed"
    tally_company      = Column(String, nullable=True)
    error              = Column(String, nullable=True)
    pushed_at          = Column(DateTime, default=datetime.utcnow, nullable=False)
    pushed_by_user_id  = Column(String, nullable=True)


# ── Role-Based User Model ────────────────────────────────────────────────────────

class User(Base):
    """
    User database model representing account credentials and access roles.
    Supported roles: "owner", "hr", "auditor", "other"
    """
    __tablename__ = "users"

    id              = Column(String, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, default="auditor", nullable=False)  # owner | hr | auditor | other
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    tenant_id       = Column(String, ForeignKey("tenants.id"), nullable=True, index=True)

    tenant = relationship("Tenant", back_populates="users")


# ── Session Persistence Layer ─────────────────────────────────────────────────

class UserSession(Base):
    """
    One row per user. Upserted on every meaningful UI action.
    Enables "resume where you left off" across devices and interfaces.
    """
    __tablename__ = "user_sessions"

    id                   = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id              = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    active_batch_id      = Column(String, ForeignKey("batch_jobs.id"), nullable=True)
    active_task_id       = Column(String, nullable=True)
    active_page          = Column(String, nullable=True)       # e.g. "invoice-extractor"
    selected_invoice_type= Column(String, nullable=True)       # sales | purchase | both
    selected_model       = Column(String, nullable=True)       # auto | groq | gemini | ...
    scroll_position      = Column(Integer, default=0)
    context_blob         = Column(Text, nullable=True)         # JSON: extra UI state
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserPreferences(Base):
    """
    Per-user settings that follow them across devices.
    """
    __tablename__ = "user_preferences"

    user_id              = Column(String, ForeignKey("users.id"), primary_key=True)
    theme                = Column(String, default="dark")
    default_invoice_type = Column(String, default="both")
    default_model        = Column(String, default="auto")
    default_export_schema= Column(String, default="standard")
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserAnnotation(Base):
    """
    Field-level notes and corrections made by auditors during review.
    Append-only — each edit is a new row (before/after values preserved).
    """
    __tablename__ = "user_annotations"

    id             = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id        = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    task_id        = Column(String, ForeignKey("invoice_tasks.id"), nullable=False, index=True)
    field_name     = Column(String, nullable=False)
    note           = Column(Text, nullable=True)
    original_value = Column(Text, nullable=True)
    corrected_value= Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)


# ── Google Drive Sync ──────────────────────────────────────────────────────

class GoogleDriveFileTracker(Base):
    """
    Single source of truth for processed Google Drive files.
    Tracks file metadata to detect new/changed files.
    """
    __tablename__ = "google_drive_file_tracker"

    id                   = Column(String, primary_key=True)  # Google Drive file ID
    tenant_id            = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    google_drive_id      = Column(String, nullable=False, unique=True, index=True)  # Immutable Drive ID
    md5_checksum         = Column(String, nullable=False)    # File content hash
    modified_time        = Column(DateTime, nullable=False)  # Drive's modifiedTime
    filename             = Column(String, nullable=False)
    mime_type            = Column(String, nullable=True)
    processing_status    = Column(String, default="pending")  # pending | processing | completed | failed
    error_message        = Column(Text, nullable=True)
    task_id              = Column(String, ForeignKey("invoice_tasks.id"), nullable=True)  # Link to extracted task
    excel_row_id         = Column(Integer, nullable=True)     # Which row in Excel output
    processed_at         = Column(DateTime, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GoogleDriveSyncJob(Base):
    """
    Log entry for each monthly sync run.
    Tracks sync history for auditing.
    """
    __tablename__ = "google_drive_sync_jobs"

    id               = Column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id        = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    sync_timestamp   = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_files_found = Column(Integer, default=0)
    new_files        = Column(Integer, default=0)
    updated_files    = Column(Integer, default=0)
    processed_files  = Column(Integer, default=0)
    failed_files     = Column(Integer, default=0)
    status           = Column(String, default="in_progress")  # in_progress | completed | failed
    error_message    = Column(Text, nullable=True)
    excel_output_path = Column(String, nullable=True)
    completed_at     = Column(DateTime, nullable=True)


class GoogleDriveSyncConfig(Base):
    """
    Per-tenant Google Drive sync configuration.
    One row per tenant — upserted via POST /api/google-drive-sync/config.
    Stores the folder the user wants to pull invoices from so they never
    have to paste the URL again after the first setup.

    Two modes, either or both can be set on the same row:
      - Legacy single-folder mode (folder_id/invoice_type/schedule): one
        fixed Drive folder, manually or cron-triggered via
        tasks.google_drive_sync_task. No month-folder resolution.
      - Self-resolving month-folder mode (the sales_/purchase_/gstr2b_
        *_root_folder_id fields): mirrors drive_path_resolver.TenantDrivePath
        - a root folder containing "<N>. <Month> <Year>" subfolders, resolved
          at run time by tasks.sales_ingestion_task / purchase_ingestion_task /
          gstr2b_ingestion_task. Added 2026-07-09 so any tenant can configure
          this from the Drive Sync UI instead of requiring someone to hand-
          edit a data/drive_paths/<slug>.json file on the server (which only
          ever worked for OneStack, the one tenant that got a manually
          created file) - see services/drive_path_resolver.py's
          load_tenant_path_config_from_db for how these fields turn into a
          TenantDrivePath.
    """
    __tablename__ = "google_drive_sync_configs"

    tenant_id    = Column(String, ForeignKey("tenants.id"), primary_key=True)
    folder_id    = Column(String, nullable=True)
    invoice_type = Column(String, default="both")  # sales | purchase | both
    schedule     = Column(String, default="0 0 1 * *")  # cron expression

    fiscal_year_start_month = Column(Integer, nullable=True)  # defaults to 4 (April) if unset
    month_folder_pattern    = Column(String, nullable=True)   # defaults to "{n}. {month_name} {year}" if unset
    sales_root_folder_id    = Column(String, nullable=True)
    purchase_root_folder_id = Column(String, nullable=True)
    gstr2b_root_folder_id   = Column(String, nullable=True)
    sales_schedule          = Column(String, nullable=True)   # cron, defaults to "0 2 * * *" (daily) if unset
    purchase_schedule       = Column(String, nullable=True)   # cron, defaults to "0 2 * * *" (daily) if unset
    gstr2b_schedule         = Column(String, nullable=True)   # cron, defaults to "0 3 * * *" (daily) if unset

    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Sales Period Review Gate ──────────────────────────────────────────────

class SalesPeriodReview(Base):
    """
    One row per (tenant, period) - the checkpoint between reconciliation
    (sales_reconciliation.py) + filing generation (gstr1_filing.py) and
    anything actually reaching the client or a GST portal. Nothing built
    in Phases 4-6 persisted its output because no real consumer existed
    yet; this table is that consumer, sized to what it actually needs to
    show a reviewer (recon status counts, flagged/skipped doc lists, one
    filing summary per GST registration) rather than the full raw
    ReconEntry/line-item payload, which stays queryable from
    SalesLineItem/InvoiceTask directly if a reviewer needs to drill in.
    """
    __tablename__ = "sales_period_reviews"

    id                = Column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id         = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    period            = Column(String, nullable=False)  # e.g. "2026-06"
    status            = Column(String, default="PENDING_REVIEW", nullable=False)
    # PENDING_REVIEW | APPROVED | REJECTED

    recon_summary_json = Column(Text, nullable=True)   # status counts + flagged/skipped doc lists
    filings_summary_json = Column(Text, nullable=True) # per-GSTIN: doc count, taxable, tax, sections

    reviewed_by       = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at       = Column(DateTime, nullable=True)
    review_notes      = Column(Text, nullable=True)

    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)


# ── Purchase / GSTR-2B Reconciliation Review Gate ─────────────────────────

class PurchaseGstr2bReview(Base):
    """
    One row per (tenant, period, gstin) - the checkpoint between GSTR-2B
    reconciliation (gstr2b_reconciler.py) and anything actually feeding a
    GSTR-3B ITC claim. Mirrors SalesPeriodReview's shape/lifecycle (see
    that model's docstring) - same PENDING_REVIEW -> APPROVED/REJECTED
    state machine, same reasoning for storing a compact summary rather
    than the full raw reconciliation payload (which stays queryable from
    PurchaseLineItem directly if a reviewer needs to drill in).

    Scoped per GSTIN (not just per tenant+period like Sales) because
    OneStack alone has two registrations (MH/HR) and a GSTR-2B JSON is
    always issued per-GSTIN by the portal - two registrations filing for
    the same period means two separate reviews, not one.
    """
    __tablename__ = "purchase_gstr2b_reviews"

    id            = Column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id     = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    period        = Column(String, nullable=False)  # e.g. "2026-06"
    gstin         = Column(String, nullable=False)
    status        = Column(String, default="PENDING_REVIEW", nullable=False)
    # PENDING_REVIEW | APPROVED | REJECTED

    recon_summary_json = Column(Text, nullable=True)  # counts, amounts, itc_at_risk, rule_36_4

    reviewed_by   = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at   = Column(DateTime, nullable=True)
    review_notes  = Column(Text, nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)


class Gstr2bGapTrigger(Base):
    """
    One row per (tenant, registration_gstin, counterparty_gstin, invoice_no,
    bucket) — tracks outbound-messaging state for a single GSTR-2B
    reconciliation gap across however many times reconciliation gets re-run
    for that period. Encodes the confirmed rules from
    memory/project_gstr2b_client_trigger.md:

      bucket="not_in_books" (Bucket A, Drive=No rows only — Drive=Yes never
        reaches here, that's an internal Tally-booking fix, no client
        contact): pending_review -> accountant approves -> approved ->
        services.gstr2b_trigger_engine.run_due_triggers sends the client
        request -> sent. Re-sent monthly (last_triggered_at gate) while the
        gap stays open.

      bucket="missing_in_2b" (Bucket B): queued (no accountant gate — auto
        per Tenant.auto_vendor_followup_enabled) -> run_due_triggers sends
        the vendor-followup notice -> sent. Also re-sent monthly while open.

    A gap that disappears from a later reconciliation run (invoice got
    booked, or the 2B filing showed up) is marked resolved by
    sync_gap_triggers rather than deleted, so the audit trail (who approved
    what, when it was sent, when it resolved) survives.
    """
    __tablename__ = "gstr2b_gap_triggers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "registration_gstin", "counterparty_gstin",
            "invoice_no", "bucket", name="uq_gap_trigger_identity",
        ),
    )

    id                  = Column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id           = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    period              = Column(String, nullable=False)   # period of most recent sighting, e.g. "2026-06"
    registration_gstin  = Column(String, nullable=False)   # the audited company's own GSTIN
    counterparty_gstin  = Column(String, nullable=False)   # supplier (A) or vendor (B) GSTIN
    invoice_no          = Column(String, nullable=False)
    bucket              = Column(String, nullable=False)   # not_in_books | missing_in_2b
    amount              = Column(Float, nullable=True)

    status              = Column(String, default="pending_review", nullable=False)
    # not_in_books:  pending_review -> approved -> sent -> resolved | rejected
    # missing_in_2b: queued -> sent -> resolved

    reviewed_by         = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at         = Column(DateTime, nullable=True)

    last_triggered_at   = Column(DateTime, nullable=True)
    trigger_count       = Column(Integer, default=0, nullable=False)
    resolved_at         = Column(DateTime, nullable=True)

    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class GoogleDriveWebhookChannel(Base):
    """
    Track active Google Drive watch channels for real-time sync.
    Channels expire and must be renewed every ~1 hour.
    """
    __tablename__ = "google_drive_webhook_channels"

    id               = Column(String, primary_key=True)
    tenant_id        = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    folder_id        = Column(String, nullable=False, index=True)
    channel_id       = Column(String, nullable=False, unique=True, index=True)
    resource_id      = Column(String, nullable=False)
    expires_at       = Column(DateTime, nullable=False)
    status           = Column(String, default="active")  # active | renewal_needed | expired
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    renewed_at       = Column(DateTime, nullable=True)
    last_notification_at = Column(DateTime, nullable=True)

