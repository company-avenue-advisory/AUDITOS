from typing import List, Dict, Any, Tuple
from backend.core.extraction.candidate_detector.candidate import Candidate

DEFAULT_WEIGHTS = {
    "math_consistency": 0.40,
    "ocr_confidence": 0.20,
    "layout_confidence": 0.15,
    "keyword_match": 0.15,
    "vendor_history": 0.10
}

def resolve_financial_candidates(
    candidates: List[Candidate], 
    field_name: str, 
    math_value: float = None, 
    weights: Dict[str, float] = None
) -> Tuple[float, float, str]:
    """
    Evaluates candidate list for a specific field and selects the best value using evidence scoring.
    Returns: (Selected Value, Final Score, Decision Reason Log)
    """
    # Filter candidates for this specific field
    field_candidates = [c for c in candidates if c.field == field_name]
    
    if not field_candidates:
        return 0.0, 0.0, f"No candidates found for field '{field_name}'."
        
    w = weights or DEFAULT_WEIGHTS
    scored_candidates = []
    log_lines = [f"Resolving candidates for {field_name} (Total: {len(field_candidates)}):"]
    
    for idx, c in enumerate(field_candidates):
        ocr_score = c.confidence
        layout_score = 0.8  # Layout position placeholder
        keyword_score = 0.95 if c.keyword else 0.5
        vendor_score = 0.5  # Future vendor intelligence hook
        
        # Math consistency checking
        math_score = 0.5
        if math_value is not None:
            try:
                c_val = float(c.value)
                if abs(c_val - math_value) <= 1.5:
                    math_score = 1.0
                elif abs(c_val - math_value) <= 10.0:
                    math_score = 0.8
                else:
                    math_score = 0.2
            except (ValueError, TypeError):
                pass
                
        final_score = (
            w["math_consistency"] * math_score +
            w["ocr_confidence"] * ocr_score +
            w["layout_confidence"] * layout_score +
            w["keyword_match"] * keyword_score +
            w["vendor_history"] * vendor_score
        )
        
        scored_candidates.append(
            (c, final_score, f"Candidate #{idx+1} [Value: {c.value}]: Math: {math_score:.2f}, OCR: {ocr_score:.2f}, Final: {final_score:.2f}")
        )
        
    # Sort by final score descending
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    best_c, best_score, best_log = scored_candidates[0]
    
    for _, _, l in scored_candidates:
        log_lines.append("  " + l)
        
    log_lines.append(f"Selected Candidate value: {best_c.value} (Score: {best_score:.2f}). Reason: Highest evidence score match.")
    
    try:
        selected_val = float(best_c.value)
    except (ValueError, TypeError):
        selected_val = 0.0
        
    return selected_val, best_score, "\n".join(log_lines)
