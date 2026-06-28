import json
from typing import Dict, Any, List
from backend.core.extraction.candidate_detector import Candidate
from backend.core.extraction.llm_call import llm_call, _truncate

METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_no": {"type": "string"},
        "voucher_date": {"type": "string"},
        "party_ledger_name": {"type": "string"},
        "party_gstin": {"type": "string"},
        "place_of_supply": {"type": "string"},
        "voucher_type": {"type": "string"}
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

def extract_metadata(text: str, candidates: List[Candidate], client, model_name: str) -> Dict[str, Any]:
    """
    Calls the LLM to extract invoice header metadata using resolved candidates.
    """
    candidates_summary = "\n".join([
        f"- Field: {c.field}, Value: {c.value}, Method: {c.method}, Confidence: {c.confidence}"
        for c in candidates
    ])
    
    prompt = f"""
Extract invoice metadata matching the schema:
{json.dumps(METADATA_SCHEMA)}

Here is the document metadata region:
{_truncate(text, 2000)}

Here are the deterministically detected candidates:
{candidates_summary}

Resolve any conflicts and return the correct values in JSON matching the schema.
"""
    res_text = ""
    try:
        res_text = llm_call(client, model_name, prompt)
        return safe_json_loads(res_text)
    except Exception as e:
        print(f"Error in metadata extraction: {e}")
        if res_text:
            print(f"Raw res_text on failure: {repr(res_text)}")
        return {}
