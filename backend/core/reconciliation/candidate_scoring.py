from typing import List, Dict, Any

class EvidenceItem:
    def __init__(self, source: str, explanation: str, contribution: float, penalty: float, severity: str = "INFO"):
        self.source = source
        self.explanation = explanation
        self.contribution = contribution
        self.penalty = penalty
        self.severity = severity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "explanation": self.explanation,
            "score_contribution": self.contribution,
            "penalty": self.penalty,
            "severity": self.severity
        }

class CandidateScorer:
    """
    Stage 2: Scores candidates based on structured pieces of evidence.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def score_candidate(self, value: float, evidence_list: List[EvidenceItem]) -> Dict[str, Any]:
        """
        Computes aggregated score and provides an explainability model.
        """
        base_score = 0.5
        total_contrib = 0.0
        total_penalty = 0.0
        
        for item in evidence_list:
            total_contrib += item.contribution
            total_penalty += item.penalty

        final_score = base_score + total_contrib - total_penalty
        final_score = max(0.0, min(1.0, final_score))
        
        return {
            "value": value,
            "score": final_score,
            "evidence": [item.to_dict() for item in evidence_list],
            "explanation": f"Candidate {value} resolved with final confidence score of {final_score:.2f} based on {len(evidence_list)} evidence checks."
        }
