from typing import Tuple, List, Dict, Any
from backend.core.schema import CanonicalInvoice

def reconcile_gst_logic(invoice: CanonicalInvoice) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Level 3: Verifies business-level GST rule alignment.
    Supplier State vs POS and CGST/SGST vs IGST exclusivity.
    """
    passed = True
    errors = []
    
    supplier_gst = (invoice.supplier.gstin.value or "").strip()
    buyer_gst = (invoice.buyer.gstin.value or "").strip()
    pos = (invoice.invoice_metadata.place_of_supply.value or "").strip().upper()
    
    cgst = invoice.tax_summary.cgst_amount.value or 0.0
    sgst = invoice.tax_summary.sgst_amount.value or 0.0
    igst = invoice.tax_summary.igst_amount.value or 0.0
    
    # 1. State matching vs POS rule
    # Intra-state vs Inter-state determination
    is_interstate = False
    if len(supplier_gst) >= 2 and len(buyer_gst) >= 2:
        is_interstate = supplier_gst[:2] != buyer_gst[:2]
        
    # 2. Exclusivity checks
    has_cgst_sgst = cgst > 0.0 or sgst > 0.0
    has_igst = igst > 0.0
    
    if has_cgst_sgst and has_igst:
        passed = False
        errors.append("Invalid GST configuration: Both CGST/SGST and IGST have positive values on the same summary.")
        
    if is_interstate and has_cgst_sgst:
        # Warning/Info level or strict check
        # We can flag it as an error since inter-state should use IGST
        passed = False
        errors.append(f"Interstate transaction (Supplier State {supplier_gst[:2]} != Buyer State {buyer_gst[:2]}) contains CGST/SGST.")
        
    if not is_interstate and has_igst and len(supplier_gst) >= 2 and len(buyer_gst) >= 2:
        passed = False
        errors.append(f"Intrastate transaction (Supplier State {supplier_gst[:2]} == Buyer State {buyer_gst[:2]}) contains IGST.")

    trace = {
        "is_interstate": is_interstate,
        "supplier_gst_prefix": supplier_gst[:2] if len(supplier_gst) >= 2 else "Unknown",
        "buyer_gst_prefix": buyer_gst[:2] if len(buyer_gst) >= 2 else "Unknown",
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "passed": passed
    }
    
    return passed, errors, trace
