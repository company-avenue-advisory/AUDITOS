import json
from typing import Dict, Any, List
from backend.core.extraction.candidate_detector import Candidate

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
    candidates_summary = "\n".join([
        f"- Field: {c.field}, Value: {c.value}, Method: {c.method}, Confidence: {c.confidence}"
        for c in candidates
    ])

    prompt = f"""
Extract overall tax totals matching the schema:
{json.dumps(TOTALS_SCHEMA)}

Here is the totals region:
{text}

Here are the deterministically detected candidates:
{candidates_summary}

RULES:
1. overall_taxable_value = gross taxable BEFORE any advance deduction. GST is computed on this.
2. overall_advance_amount = the advance/previous payment deducted (positive number). 0 if absent.
3. overall_total_invoice_value = net amount payable = taxable + tax + round_off - advance.
4. If you see "Less: Advance", "Advance received", "Previous payment", or similar lines, extract that amount as overall_advance_amount.

Resolve any conflicts and return the correct overall values in JSON matching the schema.
"""
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        res_text = response.choices[0].message.content.strip()
        return safe_json_loads(res_text)
    except Exception as e:
        print(f"Error in totals extraction: {e}")
        return {}
