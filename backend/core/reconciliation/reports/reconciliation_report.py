from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.core.reconciliation.evidence import FinancialEvidence
from backend.core.reconciliation.review_context import ReviewContext

class ReconciliationReport(BaseModel):
    """
    Consolidated financial verification audit report.
    """
    is_reconciled: bool = Field(..., description="True if no blocking variances remain")
    status: str = Field(..., description="Overall invoice status: 'ERP_READY' | 'NEEDS_REVIEW' | 'BLOCKED'")
    overall_confidence: float = Field(0.0, description="Calculated aggregate confidence score (0.0 to 1.0)")
    calculated_taxable: float = Field(0.0, description="Sum of line taxable values")
    calculated_tax: float = Field(0.0, description="Sum of line CGST + SGST + IGST + CESS")
    calculated_total: float = Field(0.0, description="Sum of calculated taxable + tax + round_off")
    variance_taxable: float = Field(0.0, description="Variance on taxable sum vs summary taxable")
    variance_total: float = Field(0.0, description="Variance on total sum vs summary total")
    failed_fields: List[str] = Field(default_factory=list, description="Fields failing reconciliation")
    hierarchical_failures: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="Failures mapped by hierarchy level (e.g. Level 1, Level 2)"
    )
    calculation_trace: Dict[str, Any] = Field(default_factory=dict, description="Math calculation trace tree")
    field_evidence: Dict[str, FinancialEvidence] = Field(default_factory=dict, description="Evidence details per field")
    review_context: ReviewContext = Field(..., description="Review dashboard parameters for UI")
    execution_time_ms: float = Field(0.0, description="Reconciliation run latency in milliseconds")
