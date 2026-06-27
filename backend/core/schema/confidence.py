from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field

T = TypeVar('T')

class FieldProvenance(BaseModel):
    """
    Tracks the visual and processing origin of an extracted field value.
    Enables interactive UI highlighting and audit traceability.
    """
    page_number: Optional[int] = Field(None, description="1-indexed page number where the field was found")
    source_type: str = Field(..., description="Source type: 'ocr' | 'llm' | 'regex' | 'human_override' | 'db'")
    source_raw_text: Optional[str] = Field(None, description="The raw, uncleaned text string matched at source")
    bounding_box: Optional[List[float]] = Field(
        None, 
        description="Normalised bounding box coordinates [x_min, y_min, x_max, y_max] from 0.0 to 1.0"
    )
    line_number: Optional[int] = Field(None, description="Estimated line number in the source text extraction")

class FieldConfidence(BaseModel):
    """
    Detailed confidence evaluation for a single extracted field.
    """
    score: float = Field(..., description="Confidence score from 0.0 to 1.0")
    source: str = Field(..., description="Entity evaluating the confidence: e.g., 'Gemini', 'Regex', 'Human'")
    method: str = Field(..., description="Method used: e.g., 'Layout + OCR', 'Regex Match', 'DB Exact Match'")
    verified: bool = Field(False, description="True if verified by human review or exact DB reconciliation")
    reason: Optional[str] = Field(None, description="Human readable justification for the confidence rating")

class ProvenancedValue(BaseModel, Generic[T]):
    """
    Wrapper for any field value to attach traceability and confidence.
    """
    value: Optional[T] = Field(None, description="The actual typed value of the field")
    confidence: Optional[FieldConfidence] = Field(None, description="Confidence metadata for this field value")
    provenance: Optional[FieldProvenance] = Field(None, description="Provenance metadata tracing the source of this field")
