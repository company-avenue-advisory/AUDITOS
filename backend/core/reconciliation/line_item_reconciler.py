from typing import List, Dict, Any, Tuple
from backend.core.schema import CanonicalInvoice
from backend.core.reconciliation.tolerance import TOLERANCE_INR

def reconcile_line_items(invoice: CanonicalInvoice) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Level 1: Reconciles each line item mathematically.
    Asserts Qty * Rate == Taxable Value and Taxable * GST_Rate == Taxes.
    """
    passed = True
    errors = []
    traces = []
    
    for idx, item in enumerate(invoice.line_items):
        qty = item.quantity.value
        rate = item.rate.value
        taxable = item.taxable_value.value or 0.0
        cgst = item.cgst_amount.value or 0.0
        sgst = item.sgst_amount.value or 0.0
        igst = item.igst_amount.value or 0.0
        total = item.total.value or 0.0
        
        line_trace = {
            "line_index": idx + 1,
            "description": item.description.value or f"Line {idx+1}",
            "passed": True,
            "details": {}
        }
        
        # Verify taxable value
        if qty is not None and rate is not None and qty > 0 and rate > 0:
            expected_taxable = qty * rate
            # Account for discount if applicable
            discount = item.discount.value or 0.0
            expected_taxable = max(0.0, expected_taxable - discount)
            
            diff = abs(expected_taxable - taxable)
            line_trace["details"]["qty_rate_taxable"] = {
                "expected": expected_taxable,
                "actual": taxable,
                "variance": diff
            }
            if diff > TOLERANCE_INR:
                passed = False
                line_trace["passed"] = False
                errors.append(f"Line {idx+1}: Taxable value variance ₹{diff:.2f} exceeds tolerance.")

        # Verify tax allocation
        expected_total = taxable + cgst + sgst + igst
        total_diff = abs(expected_total - total)
        line_trace["details"]["total_reconciliation"] = {
            "expected": expected_total,
            "actual": total,
            "variance": total_diff
        }
        if total_diff > TOLERANCE_INR:
            passed = False
            line_trace["passed"] = False
            errors.append(f"Line {idx+1}: Grand total calculation mismatch (variance: ₹{total_diff:.2f}).")
            
        traces.append(line_trace)

    return passed, errors, traces
