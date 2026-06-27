from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.core.schema import CanonicalInvoice

class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

class RuleResult(BaseModel):
    """
    Detailed output of executing a single validation rule, containing audit evidence.
    """
    rule_id: str = Field(..., description="Unique rule code (e.g. GST_001)")
    rule_name: str = Field(..., description="Short name of the validation rule")
    passed: bool = Field(..., description="True if the rule passed")
    status: str = Field(..., description="Execution status: 'PASS' | 'FAIL' | 'WARNING'")
    severity: Severity = Field(Severity.ERROR, description="Severity if rule fails")
    reason: str = Field(..., description="Chartered Accountant reasoning explanation")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Audit evidence containing expected and actual values")
    recommendation: str = Field(..., description="Suggested fix details")
    auto_fix: bool = Field(False, description="True if the system can fix this automatically")
    execution_time_ms: float = Field(0.0, description="Rule execution latency in milliseconds")

class BaseRule(ABC):
    """
    Abstract validation rule class. Supports declaration of dependencies.
    """
    rule_id: str
    rule_name: str
    category: str
    severity: Severity
    description: str
    depends_on: List[str] = []

    @abstractmethod
    def evaluate(self, invoice: CanonicalInvoice) -> RuleResult:
        """
        Runs the rule check and returns a RuleResult.
        """
        pass
