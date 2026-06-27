from typing import List, Dict, Optional
from backend.core.extraction.candidate_detector import Candidate

def resolve_totals(candidates: List[Candidate]) -> Dict[str, Optional[Candidate]]:
    """
    Resolves total candidates into subtotal, grand_total, and round_off.
    """
    total_candidates = [c for c in candidates if c.field in ["subtotal", "grand_total", "round_off"]]
    
    subtotal = None
    grand_total = None
    round_off = None
    
    # Sort by confidence descending
    total_candidates.sort(key=lambda x: x.confidence, reverse=True)
    
    for c in total_candidates:
        if c.field == "subtotal" and not subtotal:
            subtotal = c
        elif c.field == "grand_total" and not grand_total:
            grand_total = c
        elif c.field == "round_off" and not round_off:
            round_off = c
            
    return {
        "subtotal": subtotal,
        "grand_total": grand_total,
        "round_off": round_off
    }
