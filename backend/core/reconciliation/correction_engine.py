from typing import List, Dict, Any

class AutoCorrectionProposal:
    def __init__(self, original_value: float, suggested_value: float, explanation: str, 
                 evidence: List[Dict[str, Any]], confidence: float, category: str):
        self.original_value = original_value
        self.suggested_value = suggested_value
        self.explanation = explanation
        self.evidence = evidence
        self.confidence = confidence
        self.category = category

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_value": self.original_value,
            "suggested_value": self.suggested_value,
            "explanation": self.explanation,
            "deterministic_evidence": self.evidence,
            "confidence": self.confidence,
            "variance_category": self.category
        }

class CorrectionEngine:
    """
    Stage 7: Generates explainable correction proposals for downstream verification.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def generate_proposal(self, field_name: str, original: float, suggested: float, 
                          reason: str, evidence: List[Dict[str, Any]], category: str) -> Dict[str, Any]:
        """
        Creates an auto-correction proposal object.
        """
        proposal = AutoCorrectionProposal(
            original_value=original,
            suggested_value=suggested,
            explanation=reason,
            evidence=evidence,
            confidence=0.95 if evidence else 0.50,
            category=category
        )
        return {
            "field": field_name,
            "proposal": proposal.to_dict()
        }
