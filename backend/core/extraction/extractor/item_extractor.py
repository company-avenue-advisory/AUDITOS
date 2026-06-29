import json
from typing import Dict, Any, List
from backend.core.extraction.llm_call import llm_call, _truncate

ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "particulars": {"type": "string"},
                    "hsn": {"type": "string"},
                    "qty": {"type": "number"},
                    "rate": {"type": "number"},
                    "taxable_value": {"type": "number"},
                    "discount": {"type": "number"},
                    "advances": {"type": "number"},
                    "cgst_amount": {"type": "number"},
                    "sgst_amount": {"type": "number"},
                    "igst_amount": {"type": "number"},
                    "total_invoice_value": {"type": "number"},
                    "gstr1_category": {"type": "string"},
                    "itc_category": {"type": "string"},
                    "narration": {"type": "string"}
                }
            }
        }
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

def extract_items(text: str, client, model_name: str) -> List[Dict[str, Any]]:
    """
    Calls the LLM to extract individual line items from the items table region.
    """
    prompt = f"""
You are a CA audit assistant. Extract individual line item rows from the items table matching the schema:
{json.dumps(ITEMS_SCHEMA)}

CRITICAL INSTRUCTIONS:
1. Extract any 'Late Fee Charges' or 'Late Charges' as a distinct, individual line item if present.
2. If there are line-item specific discounts or advances, you must extract them onto the exact line item ('particulars') row to which they apply. Do not sum them up globally if they belong to specific items.
3. taxable_value MUST equal (qty × rate) − discount. GST (CGST/SGST/IGST) is always applied on this net taxable_value, never on the gross amount before discount. If no discount is present, taxable_value = qty × rate.
4. Ensure all values are mathematically consistent.

Here is the table region:
{_truncate(text, 6000)}

Return the correct lines list in JSON matching the schema.
"""
    try:
        res_text = llm_call(client, model_name, prompt)
        data = safe_json_loads(res_text)
        return data.get("items", [])
    except Exception as e:
        print(f"Error in items extraction: {e}")
        return []
