from typing import List, Dict, Optional
from backend.core.extraction.candidate_detector import Candidate

def resolve_dates(candidates: List[Candidate]) -> Dict[str, Optional[Candidate]]:
    """
    Resolves date candidates into invoice_date and due_date.
    """
    date_candidates = [c for c in candidates if c.field in ["invoice_date", "due_date"]]
    
    invoice_date = None
    due_date = None
    
    # Sort by confidence descending
    date_candidates.sort(key=lambda x: x.confidence, reverse=True)
    
    for c in date_candidates:
        if c.field == "invoice_date" and not invoice_date:
            invoice_date = c
        elif c.field == "due_date" and not due_date:
            due_date = c
            
    # Fallback if only invoice_date candidates exist and one is likely due date
    if not due_date and len(date_candidates) > 1:
        due_date = date_candidates[1]
        
    return {
        "invoice_date": invoice_date,
        "due_date": due_date
    }
