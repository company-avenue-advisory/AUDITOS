import re
from typing import List, Dict, Any

class HSNGuardrail:
    """
    Stage 3: Strictly prevents HSN codes from being mapped as taxable values.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.hsn_patterns = [
            r"^\d{4}$",
            r"^\d{6}$",
            r"^\d{8}$",
            r"^\d{4}\.\d{2}$"
        ]

    def is_hsn_candidate(self, val_str: str) -> bool:
        clean_val = re.sub(r"[^\d.]", "", val_str)
        for pattern in self.hsn_patterns:
            if re.match(pattern, clean_val):
                return True
        return False

    def validate_guardrail(self, candidate_value: float, extracted_hsn: str, source_column: str) -> Dict[str, Any]:
        """
        Validates if a candidate is actually an HSN value.
        """
        val_str = str(int(candidate_value)) if candidate_value.is_integer() else str(candidate_value)
        
        is_hsn_match = self.is_hsn_candidate(val_str)
        is_extracted_hsn = val_str == re.sub(r"[^\d.]", "", str(extracted_hsn))
        is_hsn_col = source_column.upper() == "HSN"
        
        should_reject = is_hsn_match or is_extracted_hsn or is_hsn_col
        
        return {
            "rejected": should_reject,
            "reason": "Value identified as HSN/SAC code" if should_reject else "Valid amount candidate",
            "score_penalty": 1.0 if should_reject else 0.0,
            "severity": "BLOCKER" if should_reject else "INFO"
        }
