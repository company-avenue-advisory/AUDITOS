from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .document import Document, OCRDocument
    from .invoice import CanonicalInvoice
    from .validation import ValidationReport
    from .confidence import FieldConfidence  # or confidence report
    from .audit import AuditMetadata

class VersionedBaseModel(BaseModel):
    """
    Base model that guarantees schema versioning and auditing on all major entities.
    """
    schema_version: str = Field("1.0.0", description="Semantic version of the data schema")
    pipeline_version: str = Field("1.0.0", description="Semantic version of the processing pipeline")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="ISO timestamp when this object was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="ISO timestamp when this object was last updated")


class DocumentBundle(VersionedBaseModel):
    """
    The top-level container (DocumentBundle) representing the complete processing result of a file.
    All downstream processors, human-review interfaces, and exports consume this bundle.
    """
    document: Optional["Document"] = Field(None, description="Raw document metadata and visual pages layout")
    invoice: Optional["CanonicalInvoice"] = Field(None, description="Extracted canonical business invoice representation")
    validation: Optional["ValidationReport"] = Field(None, description="GST/ERP compliance rules validation report")
    audit: Optional["AuditMetadata"] = Field(None, description="Pipeline latency, token usage, cost, and provider metadata")
