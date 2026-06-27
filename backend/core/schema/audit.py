from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import Field, BaseModel
from .bundle import VersionedBaseModel

class HumanCorrection(BaseModel):
    """
    Log of modification made to an extracted field by a human reviewer.
    """
    field_name: str = Field(..., description="Dot-notated path of the field modified (e.g. supplier.gstin)")
    original_value: Optional[str] = Field(None, description="Value prior to manual modification")
    corrected_value: Optional[str] = Field(None, description="Value saved by human override")
    reason: Optional[str] = Field(None, description="Justification supplied for the modification")
    modified_by: str = Field(..., description="ID or email of the human reviewer making the modification")
    modified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of modification")


class ReviewMetadata(BaseModel):
    """
    Audit details of human corrections and verification stages.
    """
    reviewed_by: Optional[str] = Field(None, description="ID or email of final approver")
    reviewed_at: Optional[datetime] = Field(None, description="Timestamp when review was finalized")
    correction_history: List[HumanCorrection] = Field(default_factory=list, description="Audit trail of corrections")

class AuditMetadata(VersionedBaseModel):
    """
    Observability metadata for pipeline tracking, metrics and usage costs.
    """
    extraction_id: str = Field(..., description="Unique ID for this extraction run")
    model_identifier: str = Field(..., description="e.g. gemini-1.5-pro, gemini-1.5-flash")
    prompt_version: str = Field(..., description="Version of the extraction prompt template")
    pipeline_version: str = Field(..., description="Version of the document pipeline code")
    processing_cost: float = Field(0.0, description="Calculated API cost of the execution run")
    latency_ms: int = Field(0, description="Latency of the extraction process in milliseconds")
    ocr_engine: Optional[str] = Field(None, description="OCR tool or model used (e.g. EasyOCR, PDFPlumber)")
    replay_id: Optional[str] = Field(None, description="ID of run this execution is replaying/re-evaluating")
    future_replay_id: Optional[str] = Field(None, description="Reserved for future replay tracking linkage")
    vendor_id: Optional[str] = Field(None, description="Associated vendor database identifier")
    document_fingerprint: Optional[str] = Field(None, description="Unique signature/hash of visual content")
