from typing import Tuple, List, Dict, Any
from backend.core.schema import CanonicalInvoice
from backend.core.reconciliation.tolerance import TOLERANCE_INR

class DualStateTaxableReconciler:
    """
    Stage 5: Evaluates if an invoice's taxable representation is gross-based or net-based.
    Maps discount, round-off, freight, packing, and insurance parameters dynamically.
    """
    def __init__(self, tolerance: float = 1.50):
        self.tolerance = tolerance

    def reconcile_dual_state(self, summary_taxable: float, gross_taxable: float, discount: float, 
                             freight: float = 0.0, packing: float = 0.0, insurance: float = 0.0) -> Dict[str, Any]:
        
        net_taxable = gross_taxable - discount
        net_reconciled = abs(summary_taxable - net_taxable) <= self.tolerance
        gross_reconciled = abs(summary_taxable - gross_taxable) <= self.tolerance
        
        # Check if auxiliary charges explain the difference
        aux_net = gross_taxable - discount + freight + packing + insurance
        aux_reconciled = abs(summary_taxable - aux_net) <= self.tolerance
        
        classification = "UNKNOWN"
        if net_reconciled or aux_reconciled:
            classification = "NET_BASED"
        elif gross_reconciled:
            classification = "GROSS_BASED"
            
        return {
            "summary_taxable": summary_taxable,
            "gross_taxable": gross_taxable,
            "net_taxable": net_taxable,
            "discount": discount,
            "freight": freight,
            "packing": packing,
            "insurance": insurance,
            "classification": classification,
            "reconciliation_metadata": {
                "is_net_based": classification == "NET_BASED",
                "is_gross_based": classification == "GROSS_BASED",
                "mapped_discount": discount if classification == "NET_BASED" else 0.0,
                "mapped_freight": freight,
                "mapped_packing": packing,
                "mapped_insurance": insurance
            }
        }

def reconcile_taxable_value(invoice: CanonicalInvoice) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Level 2: Reconciles line taxable values against summary taxable.
    Maintains backward compatibility with original pipeline signature.
    """
    overall_taxable = invoice.tax_summary.taxable_value.value or 0.0
    sum_lines = sum(item.taxable_value.value or 0.0 for item in invoice.line_items)
    
    # Calculate discount from line items if present
    total_discount = sum(getattr(item, 'discount', None) and item.discount.value or 0.0 for item in invoice.line_items)
    
    reconciler = DualStateTaxableReconciler(TOLERANCE_INR)
    res = reconciler.reconcile_dual_state(overall_taxable, sum_lines, total_discount)
    
    passed = abs(overall_taxable - sum_lines) <= TOLERANCE_INR or res["classification"] != "UNKNOWN"
    errors = []
    
    if not passed:
        errors.append(f"Summary taxable value (₹{overall_taxable:.2f}) does not match line-items sum (₹{sum_lines:.2f}).")
        
    trace = {
        "overall_taxable": overall_taxable,
        "sum_line_taxable": sum_lines,
        "variance": abs(overall_taxable - sum_lines),
        "passed": passed,
        "classification": res["classification"],
        "metadata": res["reconciliation_metadata"]
    }
    
    return passed, errors, trace
