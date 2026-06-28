from typing import Dict, Any, List
from backend.core.extraction.candidate_detector import Candidate
from .metadata_extractor import extract_metadata
from .item_extractor import extract_items
from .totals_extractor import extract_totals

def run_ai_extraction(regions, candidates: List[Candidate], client, model_name: str, invoice_type: str = "both") -> Dict[str, Any]:
    """
    Coordinates metadata, line items, and totals extraction models.
    """
    metadata_res = extract_metadata(regions.get_region_text("metadata_region"), candidates, client, model_name)
    items_res = extract_items(regions.get_region_text("items_table_region"), client, model_name)
    totals_res = extract_totals(regions.get_region_text("totals_region"), candidates, client, model_name)
    
    consolidated = {
        "overall_taxable_value": totals_res.get("overall_taxable_value") or 0.0,
        "overall_cgst_amount": totals_res.get("overall_cgst_amount") or 0.0,
        "overall_sgst_amount": totals_res.get("overall_sgst_amount") or 0.0,
        "overall_igst_amount": totals_res.get("overall_igst_amount") or 0.0,
        "overall_round_off": totals_res.get("overall_round_off") or 0.0,
        "overall_advance_amount": totals_res.get("overall_advance_amount") or 0.0,
        "overall_total_invoice_value": totals_res.get("overall_total_invoice_value") or 0.0,
        "sales_items": [],
        "purchase_items": []
    }
    
    voucher_date = metadata_res.get("voucher_date")
    voucher_type = metadata_res.get("voucher_type") or ("Sales" if invoice_type == "Sales" else ("Purchase" if invoice_type == "Purchase" else "both"))
    invoice_no = metadata_res.get("invoice_no")
    party_ledger_name = metadata_res.get("party_ledger_name")
    party_gstin = metadata_res.get("party_gstin")
    place_of_supply = metadata_res.get("place_of_supply")

    consolidated["invoice_no"] = invoice_no
    consolidated["voucher_date"] = voucher_date
    consolidated["party_ledger_name"] = party_ledger_name
    consolidated["party_gstin"] = party_gstin
    consolidated["place_of_supply"] = place_of_supply
    
    for item in items_res:
        item["voucher_date"] = item.get("voucher_date") or voucher_date
        item["voucher_type"] = item.get("voucher_type") or voucher_type
        item["invoice_no"] = item.get("invoice_no") or invoice_no
        item["party_ledger_name"] = item.get("party_ledger_name") or party_ledger_name
        item["party_gstin"] = item.get("party_gstin") or party_gstin
        item["place_of_supply"] = item.get("place_of_supply") or place_of_supply
        
        vtype = item.get("voucher_type") or ""
        if "purchase" in vtype.lower() or invoice_type == "Purchase":
            consolidated["purchase_items"].append(item)
        else:
            consolidated["sales_items"].append(item)
            
    return consolidated
