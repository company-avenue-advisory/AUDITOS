from typing import List, Dict, Optional
from backend.core.extraction.candidate_detector import Candidate

def resolve_gstin(candidates: List[Candidate]) -> Dict[str, Optional[Candidate]]:
    """
    Filters and resolves GSTIN candidates, separating them into supplier_gstin and buyer_gstin.
    """
    gst_candidates = [c for c in candidates if c.field == "gstin"]
    if not gst_candidates:
        return {"supplier_gstin": None, "buyer_gstin": None}

    # Sort by confidence descending
    gst_candidates.sort(key=lambda x: x.confidence, reverse=True)
    
    supplier_gst = None
    buyer_gst = None
    
    for c in gst_candidates:
        if c.keyword == "supplier" and not supplier_gst:
            supplier_gst = c
        elif c.keyword == "buyer" and not buyer_gst:
            buyer_gst = c
            
    # Fallbacks if keywords didn't partition them cleanly
    remaining = [c for c in gst_candidates if c != supplier_gst and c != buyer_gst]
    if remaining:
        if not supplier_gst:
            supplier_gst = remaining.pop(0)
        if not buyer_gst and remaining:
            buyer_gst = remaining.pop(0)

    return {
        "supplier_gstin": supplier_gst,
        "buyer_gstin": buyer_gst
    }
