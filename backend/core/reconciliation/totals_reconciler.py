from typing import Tuple, List, Dict, Any
from backend.core.schema import CanonicalInvoice
from backend.core.reconciliation.tolerance import TOLERANCE_INR

def reconcile_summary_totals(invoice: CanonicalInvoice) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Level 2: Reconciles subtotal + taxes + round_off == grand_total.
    """
    taxable = invoice.tax_summary.taxable_value.value or 0.0
    cgst = invoice.tax_summary.cgst_amount.value or 0.0
    sgst = invoice.tax_summary.sgst_amount.value or 0.0
    igst = invoice.tax_summary.igst_amount.value or 0.0
    cess = invoice.tax_summary.cess_amount.value or 0.0
    round_off = invoice.tax_summary.round_off.value or 0.0
    grand_total = invoice.tax_summary.grand_total.value or 0.0
    
    calculated_total = taxable + cgst + sgst + igst + cess + round_off
    variance = abs(calculated_total - grand_total)
    passed = variance <= TOLERANCE_INR
    errors = []
    
    if not passed:
        errors.append(f"Summary Grand Total mismatch. Calculated: ₹{calculated_total:.2f}, Extracted: ₹{grand_total:.2f}. Variance: ₹{variance:.2f}.")
        
    trace = {
        "calculated_total": calculated_total,
        "grand_total": grand_total,
        "variance": variance,
        "passed": passed
    }
    
    return passed, errors, trace
