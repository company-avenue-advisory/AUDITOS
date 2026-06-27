from typing import Optional, Any, List
from pydantic import BaseModel, Field

class Candidate(BaseModel):
    """
    Structured model for deterministic field candidate detection.
    """
    field: str = Field(..., description="Target field name (e.g. gstin, invoice_number)")
    value: Any = Field(..., description="Detected field value")
    page: int = Field(..., description="1-indexed page number of candidate detection")
    line: int = Field(..., description="Estimated line index in text extraction")
    keyword: Optional[str] = Field(None, description="Nearby matching keyword triggering this candidate")
    bbox: Optional[List[float]] = Field(None, description="Normalised bounding box coordinate [x_min, y_min, x_max, y_max]")
    method: str = Field(..., description="Detection method (e.g. 'regex', 'keyword_search')")
    confidence: float = Field(..., description="Rule-based matching confidence score (0.0 to 1.0)")
    context: str = Field(..., description="Surrounding text line context containing the value")
