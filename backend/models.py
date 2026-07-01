from sqlalchemy import Column, String, DateTime, Integer, Enum, Float, ForeignKey, Text, Boolean, JSON
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
    """
    __tablename__ = "google_drive_sync_configs"

    tenant_id    = Column(String, ForeignKey("tenants.id"), primary_key=True)
    folder_id    = Column(String, nullable=False)
    invoice_type = Column(String, default="both")  # sales | purchase | both
    schedule     = Column(String, default="0 0 1 * *")  # cron expression
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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

