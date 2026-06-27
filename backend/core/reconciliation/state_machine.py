from enum import Enum

class FinancialState(str, Enum):
    """
    Independent lifecycle states for important financial fields.
    """
    EXTRACTED = "EXTRACTED"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    HUMAN_CORRECTED = "HUMAN_CORRECTED"
    ERP_READY = "ERP_READY"
    EXPORTED = "EXPORTED"
