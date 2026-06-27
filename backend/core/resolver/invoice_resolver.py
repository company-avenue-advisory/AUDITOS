from typing import List, Optional
from backend.core.extraction.candidate_detector import Candidate

def resolve_invoice_number(candidates: List[Candidate]) -> Optional[Candidate]:
    """
    Selects the single highest-confidence candidate for invoice_number.
    """
    inv_candidates = [c for c in candidates if c.field == "invoice_number"]
    if not inv_candidates:
        return None
    # Sort by confidence descending
    inv_candidates.sort(key=lambda x: x.confidence, reverse=True)
    return inv_candidates[0]
