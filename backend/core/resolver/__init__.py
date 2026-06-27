from typing import List, Dict, Any
from backend.core.extraction.candidate_detector import Candidate
from .invoice_resolver import resolve_invoice_number
from .gstin_resolver import resolve_gstin
from .date_resolver import resolve_dates
from .totals_resolver import resolve_totals
from .hsn_resolver import resolve_hsn_candidates

def resolve_all_candidates(candidates: List[Candidate]) -> Dict[str, Any]:
    """
    Orchestrates candidate filtering and returns the highest-scoring candidate for each field.
    """
    resolved = {}
    resolved["invoice_number"] = resolve_invoice_number(candidates)
    
    gst_res = resolve_gstin(candidates)
    resolved["supplier_gstin"] = gst_res["supplier_gstin"]
    resolved["buyer_gstin"] = gst_res["buyer_gstin"]
    
    date_res = resolve_dates(candidates)
    resolved["invoice_date"] = date_res["invoice_date"]
    resolved["due_date"] = date_res["due_date"]
    
    totals_res = resolve_totals(candidates)
    resolved["subtotal"] = totals_res["subtotal"]
    resolved["grand_total"] = totals_res["grand_total"]
    resolved["round_off"] = totals_res["round_off"]
    
    resolved["hsn_candidates"] = resolve_hsn_candidates(candidates)
    
    return resolved
