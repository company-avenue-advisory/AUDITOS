from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class ReviewContextItem(BaseModel):
    """
    A single failed reconciliation field item flagged for manual review.
    """
    field_name: str = Field(..., description="Target field name (e.g. taxable_value)")
    extracted_value: Optional[float] = Field(None, description="The raw extracted value")
    calculated_value: Optional[float] = Field(None, description="The mathematically calculated value")
    expected_value: Optional[float] = Field(None, description="The expected value based on priority sources")
    variance: float = Field(0.0, description="Numerical difference")
    source_page: Optional[int] = Field(None, description="1-indexed source page")
    source_line: Optional[int] = Field(None, description="Estimated line number")
    candidate_list: List[Dict[str, Any]] = Field(default_factory=list, description="All matching candidates for resolution context")
    reason: str = Field(..., description="Details regarding why reconciliation failed")
    recommendation: str = Field(..., description="Suggested fix details for the CA reviewer")
    severity: str = Field("ERROR", description="Severity level: 'BLOCKER' | 'ERROR' | 'WARNING'")
    failure_category: str = Field("MATH_ERROR", description="Failure type: e.g. OCR_ERROR, MATH_ERROR, GST_RULE_ERROR")

class ReviewContext(BaseModel):
    """
    Complete context dashboard powering human correction UI.
    """
    is_blocked: bool = Field(False, description="True if block rules are triggered")
    items: List[ReviewContextItem] = Field(default_factory=list, description="Flagged fields requiring attention")
