from sqlalchemy import Column, String, DateTime, Integer, Enum, Float, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from database import Base

class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class BatchJob(Base):
    __tablename__ = "batch_jobs"
    
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_files = Column(Integer, default=0)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    
    tasks = relationship("InvoiceTask", back_populates="batch", cascade="all, delete-orphan")

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

