from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from .state_machine import FinancialState
from .source_hierarchy import SourceRank

class AutoCorrectionSuggestion(BaseModel):
    """
    Suggested corrective action for a failed reconciliation field.
    """
    suggested_value: float = Field(..., description="The calculated/proven corrected value")
    reason: str = Field(..., description="Chartered Accountant justification for the suggestion")
    action_type: str = Field("REPLACE", description="Type of correction recommendation: e.g. REPLACE, INJECT")

class FinancialEvidence(BaseModel):
    """
    Wraps important financial values to attach explainability, calculations and audit history.
    """
    value: float = Field(0.0, description="The extracted/selected value")
    calculated_value: float = Field(0.0, description="The mathematically calculated value")
    variance: float = Field(0.0, description="Difference between extracted and calculated values")
    confidence: float = Field(0.0, description="Field-level confidence score (0.0 to 1.0)")
    evidence_score: float = Field(0.0, description="Rank value matching evidence source authority")
    source: str = Field("llm", description="Source of selection: e.g. 'line_item_math', 'ocr', 'llm'")
    calculation: Optional[str] = Field(None, description="The mathematical formula path/trace used")
    verified: bool = Field(False, description="True if mathematically proven or manually approved")
    status_state: FinancialState = Field(FinancialState.EXTRACTED, description="The current field lifecycle state")
    suggested_correction: Optional[AutoCorrectionSuggestion] = Field(None, description="Auto correction details if applicable")
