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

# itc_category values recognised by the ITC eligibility validator below
ITC_ELIGIBLE       = "ITC_ELIGIBLE"
ITC_BLOCKED        = "ITC_BLOCKED"       # Section 17(5) hard block
ITC_RESTRICTED     = "ITC_RESTRICTED"    # Pro-rata or partial (e.g. mixed-use)
ITC_EXEMPT         = "ITC_EXEMPT"        # Used for exempt supplies
ITC_UNKNOWN        = "ITC_UNKNOWN"       # LLM could not determine

# Section 17(5) blocked HSN prefixes (CGST Act) — ITC not claimable
_SEC_17_5_HSN_PREFIXES = (
    "8703",   # Motor vehicles for persons (< 13 seats)
    "8711",   # Motorcycles
    "8716",   # Trailers — personal
    "3303", "3304", "3305", "3306", "3307",  # Beauty / cosmetic treatments
)

# Section 17(5) blocked service keywords in particulars
_SEC_17_5_BLOCKED_KEYWORDS = [
    "club membership", "health club", "fitness", "beauty treatment",
    "cosmetic surgery", "outdoor catering", "employee travel benefit",
    "works contract for immovable", "construction of immovable",
    "rent a cab", "life insurance", "health insurance",
]


def _apply_itc_rules(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Post-processes extracted purchase line items with deterministic Section 17(5)
    ITC eligibility rules. Overrides LLM's itc_category when a hard-block applies.
    Returns items with itc_category standardised to ITC_ELIGIBLE / ITC_BLOCKED /
    ITC_RESTRICTED / ITC_EXEMPT / ITC_UNKNOWN.
    """
    for item in items:
        hsn = str(item.get("hsn") or "").strip()
        particulars = str(item.get("particulars") or "").lower()
        current = str(item.get("itc_category") or "").upper()

        # Hard block: HSN matches Section 17(5) list
        if any(hsn.startswith(pfx) for pfx in _SEC_17_5_HSN_PREFIXES):
            item["itc_category"] = ITC_BLOCKED
            item["itc_block_reason"] = "Section 17(5) — blocked HSN"
            continue

        # Hard block: service description matches blocked keywords
        if any(kw in particulars for kw in _SEC_17_5_BLOCKED_KEYWORDS):
            item["itc_category"] = ITC_BLOCKED
            item["itc_block_reason"] = "Section 17(5) — blocked service description"
            continue

        # Normalise LLM output to standard values
        if current in ("ELIGIBLE", "FULL_ITC", "YES", "Y", "ALLOWED", ITC_ELIGIBLE):
            item["itc_category"] = ITC_ELIGIBLE
        elif current in ("BLOCKED", "NOT_ELIGIBLE", "NO", "N", "INELIGIBLE", ITC_BLOCKED):
            item["itc_category"] = ITC_BLOCKED
        elif current in ("RESTRICTED", "PARTIAL", "PRO_RATA", ITC_RESTRICTED):
            item["itc_category"] = ITC_RESTRICTED
        elif current in ("EXEMPT", "NIL_RATED", ITC_EXEMPT):
            item["itc_category"] = ITC_EXEMPT
        else:
            item["itc_category"] = ITC_UNKNOWN

    return items


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


def extract_items(text: str, client, model_name: str, vendor_hints: str = "") -> List[Dict[str, Any]]:
    """
    Extracts sales line items from the items table region.
    """
    hint_block = f"{vendor_hints}\n\n" if vendor_hints else ""
    prompt = f"""{hint_block}Extract sales line items as JSON matching this schema:
{json.dumps(ITEMS_SCHEMA)}

Rules:
1. ONLY extract actual goods/service line items from the line items table. Do NOT include subtotals, totals, or tax summary rows (SGST, CGST, IGST, Total Tax, Grand Total, Total Payable, Subtotal, Round Off).
2. NEVER invent placeholder items like "Supply of Goods" or "Supply of Services" — if no real items found, return empty array.
3. EXPORT INVOICES (text says "EXPORT INVOICE", "Under LUT", "Letter of Undertaking", "Without Payment of IGST", or Place of Supply is a foreign country):
   - gstr1_category = "EXPORT"
   - cgst_amount = 0, sgst_amount = 0, igst_amount = 0 (zero-rated under LUT)
   - taxable_value = the foreign currency amount shown (use numeric value as-is)
   - HSN/SAC = the SAC code from the invoice
4. DECIMAL FORMAT: European invoices use period as thousands separator and comma as decimal (e.g. "1.200,00" = 1200.00, "4.200,00" = 4200.00). US invoices use standard decimals (900.00 = 900.00).
5. "Late Fee Charges" / "Late Charges" → separate line item.
6. taxable_value = (qty × rate) − discount. For export, discount column "-" means 0.
7. For domestic invoices: compute cgst_amount = taxable_value × cgst_rate, sgst_amount = taxable_value × sgst_rate.
8. gstr1_category: B2B (customer has Indian GSTIN), B2C (no GSTIN, domestic), EXPORT (foreign buyer / LUT), SEZ, or NIL_EXEMPT.
9. Intrastate supply → cgst+sgst only (igst=0). Interstate → igst only (cgst/sgst=0). Export → all taxes = 0.

Table region:
{_truncate(text, 4000)}

Return JSON only."""
    try:
        res_text = llm_call(client, model_name, prompt)
        data = safe_json_loads(res_text)
        return data.get("items", [])
    except Exception as e:
        print(f"Error in items extraction: {e}")
        return []


def extract_purchase_items(text: str, client, model_name: str, vendor_hints: str = "") -> List[Dict[str, Any]]:
    """
    Purchase-specific extraction prompt with ITC eligibility focus.
    Applies deterministic Section 17(5) validation after LLM extraction.
    """
    hint_block = f"{vendor_hints}\n\n" if vendor_hints else ""
    prompt = f"""{hint_block}Extract purchase line items as JSON matching this schema:
{json.dumps(ITEMS_SCHEMA)}

Rules:
1. ONLY extract actual goods/service line items — do NOT include subtotals, totals, tax summary rows (SGST, CGST, IGST, Total Tax, Grand Total, Total Payable, Subtotal).
2. Include freight, packing, late charges as separate rows.
3. taxable_value = (qty × rate) − discount. GST only on taxable_value.
4. For each item, compute cgst_amount = taxable_value × cgst_rate, sgst_amount = taxable_value × sgst_rate, igst_amount = taxable_value × igst_rate.
5. IGST = inter-state supply; CGST+SGST = intra-state supply. Never mix.
6. itc_category per item: ITC_ELIGIBLE | ITC_BLOCKED | ITC_RESTRICTED | ITC_EXEMPT | ITC_UNKNOWN.
   Sec 17(5) blocks: motor vehicles (HSN 8703/8711), club memberships, health/beauty, outdoor catering, works contract for immovable property.
7. HSN ≠ invoice number — different fields.

Purchase table region:
{_truncate(text, 4000)}

Return JSON only."""
    try:
        res_text = llm_call(client, model_name, prompt)
        data = safe_json_loads(res_text)
        items = data.get("items", [])
        return _apply_itc_rules(items)
    except Exception as e:
        print(f"Error in purchase items extraction: {e}")
        return []
