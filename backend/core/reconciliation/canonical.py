from typing import Any, Dict
from backend.core.schema import CanonicalInvoice
from backend.core.reconciliation.source_hierarchy import FIELD_SOURCE_AUTHORITY, SourceRank
from backend.core.reconciliation.tolerance import TOLERANCE_INR

# Fields the reconciliation engine can canonicalize. Each maps to its
# line-item-derived candidate value where one exists.
CANONICAL_FIELDS = ("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "grand_total")


def compute_canonical_values(
    invoice: CanonicalInvoice,
    lvl1_passed: bool,
    master_trace: Dict[str, Any],
    extracted: Dict[str, float],
) -> Dict[str, Dict[str, Any]]:
    """
    Derives the canonical value for each field, promoting the line-item-derived
    value over the extracted invoice summary only when FIELD_SOURCE_AUTHORITY
    already ranks line items as the stronger source for that field (today:
    taxable_value, grand_total — cgst/sgst/igst/round_off are ranked
    INVOICE_TAX_SUMMARY-authoritative and always pass through unchanged).

    Promotion additionally requires:
      - at least one line item exists,
      - line items are internally self-consistent (lvl1_passed — each line's
        own qty*rate/taxable/tax math already reconciles), and
      - the extracted summary actually disagrees with the line-item evidence
        beyond tolerance (otherwise there's nothing to correct).

    grand_total's line-item-derived candidate is master_trace's own
    calculated_grand_total (sum of line taxable + taxes − discount − advances)
    — reused as-is, not recomputed here.
    """
    has_line_items = bool(invoice.line_items)

    line_item_sums = {
        "taxable_value": sum(item.taxable_value.value or 0.0 for item in invoice.line_items),
        "grand_total": master_trace.get("calculated_grand_total", extracted.get("grand_total", 0.0)),
    }

    canonical: Dict[str, Dict[str, Any]] = {}
    for field in CANONICAL_FIELDS:
        extracted_val = extracted.get(field, 0.0)
        authority = FIELD_SOURCE_AUTHORITY.get(field, SourceRank.LLM_EXTRACTION)

        if authority == SourceRank.LINE_ITEM_CALCULATION and field in line_item_sums:
            calc_val = line_item_sums[field]
            variance = abs(extracted_val - calc_val)
            if has_line_items and lvl1_passed and variance > TOLERANCE_INR:
                canonical[field] = {
                    "value": round(calc_val, 2),
                    "source": SourceRank.LINE_ITEM_CALCULATION.name,
                    "corrected": True,
                }
                continue

        canonical[field] = {
            "value": round(extracted_val, 2),
            "source": authority.name,
            "corrected": False,
        }

    return canonical
