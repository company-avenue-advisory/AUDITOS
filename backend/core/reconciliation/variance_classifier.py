from typing import List, Dict, Any

class VarianceClassifier:
    """
    Stage 6: Categorizes structural discrepancies between extracted fields and reference totals.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def classify_variance(self, affected_fields: List[str], variance_amount: float, extra_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classifies variance and provides corrective suggestions.
        """
        category = "UNKNOWN"
        explanation = "Unrecognized variance pattern"
        suggested_action = "Request manual review of invoice numbers and totals"
        confidence = 0.5
        
        is_hsn_overlap = extra_context.get("is_hsn_overlap", False)
        is_discount_match = extra_context.get("is_discount_match", False)
        is_roundoff = extra_context.get("is_roundoff", False)
        is_freight = extra_context.get("is_freight", False)
        
        if is_hsn_overlap:
            category = "HSN_AS_AMOUNT"
            explanation = "HSN/SAC code incorrectly extracted as taxable value."
            suggested_action = "Discard value and use the actual amount from rate/quantity product"
            confidence = 0.95
        elif is_discount_match:
            category = "GLOBAL_DISCOUNT"
            explanation = "Invoice totals mismatch due to pre-tax discount value omission."
            suggested_action = "Apply extracted discount to line items or summary taxable value"
            confidence = 0.90
        elif is_roundoff and variance_amount <= 1.0:
            category = "ROUND_OFF"
            explanation = "Variance explained by mathematical roundoff adjustments."
            suggested_action = "Align values using a roundoff correction delta"
            confidence = 0.99
        elif is_freight:
            category = "FREIGHT_INCLUDED"
            explanation = "Difference represents logistics or freight charges."
            suggested_action = "Separate freight charges from taxable line items"
            confidence = 0.85
            
        return {
            "category": category,
            "affected_fields": affected_fields,
            "explanation": explanation,
            "confidence": confidence,
            "suggested_action": suggested_action,
            "variance_amount": variance_amount
        }
