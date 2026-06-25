from sqlalchemy import Column, String, DateTime, Integer, Enum, Float, ForeignKey
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
