from typing import List
from backend.core.extraction.candidate_detector import Candidate

def resolve_hsn_candidates(candidates: List[Candidate]) -> List[Candidate]:
    """
    Returns high-confidence HSN candidates.
    """
    hsn_candidates = [c for c in candidates if c.field == "hsn"]
    hsn_candidates.sort(key=lambda x: x.confidence, reverse=True)
    return hsn_candidates
