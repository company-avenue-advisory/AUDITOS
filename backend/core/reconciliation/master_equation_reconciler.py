from typing import Tuple, Dict, Any
from backend.core.schema import CanonicalInvoice
from backend.core.reconciliation.tolerance import TOLERANCE_INR


def reconcile_master_equation(invoice: CanonicalInvoice) -> Tuple[bool, Dict[str, Any]]:
    """
    Anchor check: Sigma(Taxable) + Sigma(Taxes) - Sigma(Discount) - Sigma(Advances)
    == Total Invoice Value (grand total), computed purely from line-item evidence.

    Exists because the extracted SUMMARY taxable/cgst/sgst/igst fields have been
    confirmed unreliable on real invoices (see OneStack invoice audit — summary
    taxable value was wrong on multiple invoices while line items were correct),
    whereas the extracted grand total has been reliable on every invoice checked
    so far. Discount and advance-paid rows are first-class line items (see
    item_extractor.py prompt rules) rather than silently dropped, so this
    equation only balances once all monetary evidence on the invoice has
    actually been captured.

    This does not replace the summary-level checks (reconcile_taxable_value /
    reconcile_summary_totals) — it supplements them, so an invoice can still be
    reconciled even when the printed summary block itself is untrustworthy.
    """
    sum_taxable = sum(item.taxable_value.value or 0.0 for item in invoice.line_items)
    sum_taxes = sum(
        (item.cgst_amount.value or 0.0) + (item.sgst_amount.value or 0.0) +
        (item.igst_amount.value or 0.0) + (item.cess_amount.value or 0.0)
        for item in invoice.line_items
    )
    sum_discount = sum(item.discount.value or 0.0 for item in invoice.line_items)
    sum_advances = sum(item.advances.value or 0.0 for item in invoice.line_items)

    grand_total = invoice.tax_summary.grand_total.value or 0.0

    calculated_grand_total = sum_taxable + sum_taxes - sum_discount - sum_advances
    variance = abs(calculated_grand_total - grand_total)
    passed = variance <= TOLERANCE_INR

    trace = {
        "sum_taxable": sum_taxable,
        "sum_taxes": sum_taxes,
        "sum_discount": sum_discount,
        "sum_advances": sum_advances,
        "calculated_grand_total": calculated_grand_total,
        "extracted_grand_total": grand_total,
        "variance": variance,
        "passed": passed,
    }
    return passed, trace
