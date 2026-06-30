import json
from typing import Dict, Any, List
from backend.core.extraction.candidate_detector import Candidate
from backend.core.extraction.llm_call import llm_call, _truncate

TOTALS_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_taxable_value": {"type": "number", "description": "Total taxable value BEFORE any advance/credit deduction. This is the gross GST base."},
        "overall_cgst_amount": {"type": "number"},
        "overall_sgst_amount": {"type": "number"},
        "overall_igst_amount": {"type": "number"},
        "overall_round_off": {"type": "number", "description": "Rounding off / rounding adjustment on final invoice total"},
        "overall_advance_amount": {"type": "number", "description": "Advance payment / previous payment deducted from the invoice total. Extract from lines like 'Less: Advance', 'Advance received', 'Previous payment', 'Adjustment'. Positive number even though it is deducted."},
        "overall_total_invoice_value": {"type": "number", "description": "Net amount payable AFTER deducting advance. This is what the customer actually pays."}
    }
}

def safe_json_loads(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)

def extract_totals(text: str, candidates: List[Candidate], client, model_name: str) -> Dict[str, Any]:
    """
    Calls the LLM to extract overall tax totals and summary using resolved candidates.
    """
    # Keep only the top-10 totals-relevant candidates to save tokens
    top_candidates = sorted(candidates, key=lambda c: c.confidence, reverse=True)[:10]
    candidates_summary = _truncate("\n".join([
        f"- {c.field}: {c.value} (conf={c.confidence:.2f})"
        for c in top_candidates
    ]), 400)

    prompt = f"""Extract overall tax totals as JSON matching this schema:
{json.dumps(TOTALS_SCHEMA)}

Totals region:
{_truncate(text, 2000)}

Detected candidates:
{candidates_summary}

RULES:
1. overall_taxable_value = gross taxable BEFORE advance deduction. GST base.
2. overall_advance_amount = advance/previous payment deducted (positive). 0 if absent.
3. overall_total_invoice_value = taxable + tax + round_off - advance.
4. "Less: Advance" / "Advance received" / "Previous payment" → overall_advance_amount.

Return JSON only."""
    try:
        res_text = llm_call(client, model_name, prompt)
        return safe_json_loads(res_text)
    except Exception as e:
        print(f"Error in totals extraction: {e}")
        return {}
