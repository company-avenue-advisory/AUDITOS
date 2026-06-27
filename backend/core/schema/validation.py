from typing import Optional, List, Dict, Any
from pydantic import Field, BaseModel
from .bundle import VersionedBaseModel

class ValidationResult(BaseModel):
    """
    Result of executing a single compliance, validation or auditing check.
    """
    rule_id: str = Field(..., description="Unique code identifying the validation rule (e.g. GST_MATH_001)")
    rule_name: str = Field(..., description="Name of the validation rule")
    category: str = Field(..., description="Category of the validation rule (e.g. GST, Math, Date)")
    severity: str = Field("MEDIUM", description="Severity level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'")
    passed: bool = Field(..., description="True if the validation check passed")
    status: str = Field(..., description="Execution status: 'PASS' | 'FAIL' | 'WARNING'")
    expected_value: Optional[str] = Field(None, description="Expected value for validation comparison")
    actual_value: Optional[str] = Field(None, description="Actual value extracted or calculated")
    variance: Optional[float] = Field(None, description="Numerical difference if math verification failed")
    message: str = Field(..., description="Details and context regarding validation outcome")
    suggested_fix: Optional[str] = Field(None, description="Suggested action to resolve validation failure")
    auto_fix_possible: bool = Field(False, description="True if this rule failure can be resolved automatically")
    execution_time_ms: float = Field(0.0, description="Rule execution latency in milliseconds")

class ValidationReport(VersionedBaseModel):
    """
    Full report detailing the overall outcome of invoice validations.
    """
    math_status: str = Field("PENDING", description="Math verification status: 'PASSED' | 'FAILED' | 'WARNING' | 'PENDING'")
    gst_status: str = Field("PENDING", description="GST registration and formatting check status: 'PASSED' | 'FAILED' | 'WARNING' | 'PENDING'")
    overall_status: str = Field("PENDING", description="Overall CA audit readiness status: 'ERP_READY' | 'NEEDS_REVIEW' | 'BLOCKED' | 'PENDING'")
    overall_score: float = Field(100.0, description="Calculated compliance score from 0.0 to 100.0")
    total_rules: int = Field(0, description="Total validation rules executed")
    errors: List[str] = Field(default_factory=list, description="List of blocking errors found")
    warnings: List[str] = Field(default_factory=list, description="List of non-blocking warnings found")
    passed_rules: List[str] = Field(default_factory=list, description="Identifiers of validation rules that passed")
    failed_rules: List[str] = Field(default_factory=list, description="Identifiers of validation rules that failed")
    results: List[ValidationResult] = Field(default_factory=list, description="List of detailed individual rule outcomes")
    execution_time_ms: float = Field(0.0, description="Total execution time of the validation run in milliseconds")
