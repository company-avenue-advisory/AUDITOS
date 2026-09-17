from typing import Dict, Any, List
from backend.core.extraction.candidate_detector import Candidate
from .metadata_extractor import extract_metadata
from .item_extractor import extract_items, extract_purchase_items
from .totals_extractor import extract_totals


def sum_line_item_taxes(items: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Deterministically sums the tax fields already present on extracted line
    items. See run_ai_extraction's comment for why this is preferred over
    the totals-region LLM call for these specific fields.
    """
    return {
        "overall_taxable_value": sum(float(it.get("taxable_value") or 0.0) for it in items),
        "overall_cgst_amount": sum(float(it.get("cgst_amount") or 0.0) for it in items),
        "overall_sgst_amount": sum(float(it.get("sgst_amount") or 0.0) for it in items),
        "overall_igst_amount": sum(float(it.get("igst_amount") or 0.0) for it in items),
    }


def run_ai_extraction(regions, candidates: List[Candidate], client, model_name: str, invoice_type: str = "both", vendor_hints: str = "") -> Dict[str, Any]:
    """
    Coordinates metadata, line items, and totals extraction.
    Uses a purchase-specific prompt with ITC eligibility rules when invoice_type is 'purchase'.
    """
    # Route to the correct extractor based on invoice type
    is_purchase = invoice_type.lower() in ("purchase", "both")
    is_sales    = invoice_type.lower() in ("sales", "both")
    # The keyword-based region splitter (layout.py) is unreliable on generic
    # vendor invoices: a stray mention of a table-header word (e.g. "HSN" in a
    # legend paragraph) can start "items_table_region" early on boilerplate
    # text, while the real HSN/tax breakdown table then gets swallowed into
    # totals_region because its own header row contains a totals keyword
    # (e.g. "Total Tax"). Concatenating both regions is a safe superset fix —
    # both extract_items and extract_purchase_items prompts already instruct
    # the LLM to exclude subtotal/grand-total rows, so this never causes
    # double-counting, it just prevents real line/tax data from being dropped
    # entirely when the splitter misclassifies it.
    items_table = "\n".join(filter(None, [
        regions.get_region_text("items_table_region"),
        regions.get_region_text("totals_region"),
    ]))

    # Purchase invoices from third-party vendors commonly print their own
    # GST registration number in footer/registration boilerplate, not near
    # the header — and that boilerplate frequently lands in items_table_region
    # (see above) rather than metadata_region because of the same splitter
    # bug. Give the purchase-side metadata call the whole document so the
    # supplier's real GSTIN/name isn't missed; sales keeps its narrower,
    # already-verified metadata_region input unchanged.
    metadata_text = regions.get_region_text("metadata_region")
    if is_purchase and not is_sales:
        metadata_text = "\n".join(filter(None, [metadata_text, items_table]))

    metadata_res = extract_metadata(
        metadata_text, candidates, client, model_name,
        vendor_hints=vendor_hints,
        invoice_type="purchase" if invoice_type.lower() == "purchase" else "sales",
    )

    if is_purchase and not is_sales:
        # Pure purchase — use purchase-specific prompt + ITC rules
        purchase_items_raw = extract_purchase_items(items_table, client, model_name, vendor_hints=vendor_hints)
        sales_items_raw    = []
    elif is_sales and not is_purchase:
        # Pure sales
        sales_items_raw    = extract_items(items_table, client, model_name, vendor_hints=vendor_hints)
        purchase_items_raw = []
    else:
        # "both" — extract once with sales prompt then classify by voucher_type
        sales_items_raw    = extract_items(items_table, client, model_name, vendor_hints=vendor_hints)
        purchase_items_raw = []

    totals_res = extract_totals(regions.get_region_text("totals_region"), candidates, client, model_name)

    # Prefer summing the already-extracted line items' own tax fields over the
    # totals-region LLM call for taxable/CGST/SGST/IGST. The totals call has to
    # re-derive these from free-text in one shot, and silently returns 0 on
    # invoices whose tax breakdown is only ever printed per-line (e.g. a table
    # with a CGST/SGST column per row but no separate "Total CGST" summary row)
    # -- confirmed on a real invoice where the totals call returned 0 for both
    # while the correctly-extracted line items summed to the exact missing
    # amount. Line items are extracted per-row against a table, which is more
    # grounded, and the item-extraction prompt already requires their sum to
    # match the invoice's printed grand total, so this is not a new invariant.
    _all_items_raw = purchase_items_raw + sales_items_raw
    _line_sums = sum_line_item_taxes(_all_items_raw)

    consolidated = {
        "overall_taxable_value":      _line_sums["overall_taxable_value"] if _all_items_raw else (totals_res.get("overall_taxable_value") or 0.0),
        "overall_cgst_amount":        _line_sums["overall_cgst_amount"] if _all_items_raw else (totals_res.get("overall_cgst_amount") or 0.0),
        "overall_sgst_amount":        _line_sums["overall_sgst_amount"] if _all_items_raw else (totals_res.get("overall_sgst_amount") or 0.0),
        "overall_igst_amount":        _line_sums["overall_igst_amount"] if _all_items_raw else (totals_res.get("overall_igst_amount") or 0.0),
        "overall_round_off":          totals_res.get("overall_round_off") or 0.0,
        "overall_advance_amount":     totals_res.get("overall_advance_amount") or 0.0,
        "overall_total_invoice_value":totals_res.get("overall_total_invoice_value") or 0.0,
        "sales_items":    [],
        "purchase_items": [],
    }

    voucher_date      = metadata_res.get("voucher_date")
    voucher_type      = metadata_res.get("voucher_type") or ("Sales" if is_sales else "Purchase")
    invoice_no        = metadata_res.get("invoice_no")
    party_ledger_name = metadata_res.get("party_ledger_name")
    party_gstin       = metadata_res.get("party_gstin")
    place_of_supply   = metadata_res.get("place_of_supply")

    consolidated.update({
        "invoice_no": invoice_no, "voucher_date": voucher_date,
        "party_ledger_name": party_ledger_name, "party_gstin": party_gstin,
        "place_of_supply": place_of_supply,
    })

    def _enrich(item, default_vtype):
        item["voucher_date"]      = item.get("voucher_date")      or voucher_date
        item["voucher_type"]      = item.get("voucher_type")      or default_vtype
        item["invoice_no"]        = item.get("invoice_no")        or invoice_no
        item["party_ledger_name"] = item.get("party_ledger_name") or party_ledger_name
        item["party_gstin"]       = item.get("party_gstin")       or party_gstin
        # Derive place_of_supply from buyer GSTIN state code when not explicitly set
        resolved_pos = item.get("place_of_supply") or place_of_supply
        if not resolved_pos:
            gstin_val = item.get("party_gstin") or party_gstin or ""
            if len(str(gstin_val).strip()) >= 2 and str(gstin_val).strip()[:2].isdigit():
                resolved_pos = str(gstin_val).strip()[:2]
        item["place_of_supply"] = resolved_pos
        return item

    # Items from purchase extractor always go to purchase_items
    for item in purchase_items_raw:
        consolidated["purchase_items"].append(_enrich(item, "Purchase"))

    # Items from sales extractor: classify by voucher_type when "both"
    for item in sales_items_raw:
        _enrich(item, voucher_type)
        vtype = (item.get("voucher_type") or "").lower()
        if "purchase" in vtype or invoice_type.lower() == "purchase":
            consolidated["purchase_items"].append(item)
        else:
            consolidated["sales_items"].append(item)

    return consolidated
