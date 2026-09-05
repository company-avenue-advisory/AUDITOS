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

def extract_metadata(text: str, candidates: List[Candidate], client, model_name: str, vendor_hints: str = "", invoice_type: str = "sales") -> Dict[str, Any]:
    """
    Calls the LLM to extract invoice header metadata using resolved candidates.
    """
    # Keep only the top-15 candidates by confidence; drop low-signal noise
    top_candidates = sorted(candidates, key=lambda c: c.confidence, reverse=True)[:15]
    candidates_summary = _truncate("\n".join([
        f"- {c.field}: {c.value} (conf={c.confidence:.2f})"
        for c in top_candidates
    ]), 600)

    hint_block = f"{vendor_hints}\n\n" if vendor_hints else ""

    # "party" means opposite directions depending on which ledger this invoice
    # is being extracted for. Sales: OneStack/Marquecom is the seller, so
    # party = the customer/buyer. Purchase: OneStack is the BUYER receiving
    # this bill, so party must be the SUPPLIER/vendor who issued it — even
    # though OneStack's own name/GSTIN also appears in the document (as the
    # recipient) and must NOT be picked instead.
    if invoice_type.lower() == "purchase":
        party_rule = (
            'IMPORTANT: This is a PURCHASE invoice — "One Stack Solution" / "Marquecom" (or any of '
            'their GSTINs, e.g. any GSTIN with PAN AADCO0061H) is the BUYER/recipient here, NOT the party. '
            "party_ledger_name and party_gstin must identify the SUPPLIER/vendor who issued this invoice "
            "(the company whose letterhead, signatory, and bank details appear on the bill), never the buyer."
        )
    else:
        party_rule = (
            'IMPORTANT: Do NOT return "One Stack Solution" or "Marquecom" as party_ledger_name — '
            "those are the seller. party_ledger_name is the customer/buyer."
        )

    prompt = f"""{hint_block}Extract invoice metadata as JSON matching this schema:
{json.dumps(METADATA_SCHEMA)}

{party_rule}

Metadata region:
{_truncate(text, 6000 if invoice_type.lower() == "purchase" else 2000)}

Detected candidates:
{candidates_summary}

Return JSON only."""
    res_text = ""
    try:
        res_text = llm_call(client, model_name, prompt)
        result = safe_json_loads(res_text)
        if isinstance(result, list):
            # Model occasionally returns a bare array when it perceives multiple
            # invoices/pages in one document — this pipeline handles one invoice
            # per PDF, so take the first entry rather than crashing on .get().
            result = result[0] if result and isinstance(result[0], dict) else {}
        return result
    except Exception as e:
        print(f"Error in metadata extraction: {e}")
        if res_text:
            print(f"Raw res_text on failure: {repr(res_text)}")
        return {}
