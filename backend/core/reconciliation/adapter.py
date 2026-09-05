"""
Adapter: internal extraction result (SuvitSalesItem / SuvitPurchaseItem lists,
as produced by invoice_processor.process_pdf) -> CanonicalInvoice, the shape
FinancialReconciliationEngine.reconcile() actually expects.

This exists because the reconciliation engine's schema (core/schema/*) evolved
independently of the call sites that build CanonicalInvoice by hand — every
prior call site (async_tasks.py, and copies of it) passed field names/types
that don't match the current schema (e.g. raw floats where ProvenancedValue
was required, "particulars"/"hsn"/"total_invoice_value" where the schema
expects "description"/"hsn_sac"/"total", and a "metadata" kwarg that
CanonicalInvoice doesn't even have). Those call sites were silently failing
via a bare except-and-log, so recon_status was never actually being set.
This module is the single place that maps our fields correctly so it only
needs to be right once.
"""

import os
import sys
from typing import List

# Match core/reconciliation/engine.py's import convention exactly so the
# CanonicalInvoice/LineItem/etc. classes built here are the SAME class objects
# reconcile() expects (see engine.py's comment — the whole core/ package uses
# "backend.core...." absolute imports which need the repo root on sys.path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backend.core.schema import CanonicalInvoice
from backend.core.schema.tax import TaxSummary
from backend.core.schema.confidence import ProvenancedValue, FieldConfidence
from backend.core.schema.items import LineItem


def _pv(value, source: str):
    """Wrap a raw scalar in the ProvenancedValue shape the schema requires."""
    return ProvenancedValue(
        value=value,
        confidence=FieldConfidence(score=0.9, source=source, method="LLM extraction"),
    )


def build_canonical_invoice(sales_items: List, purchase_items: List,
                             overall_taxable_value, overall_cgst_amount,
                             overall_sgst_amount, overall_igst_amount,
                             overall_total_invoice_value,
                             overall_round_off=0.0, source: str = "extraction") -> CanonicalInvoice:
    """
    Build a CanonicalInvoice from the raw extraction result fields
    (SuvitSalesItem / SuvitPurchaseItem + InvoiceExtractionResponse overall_* totals)
    so it can be passed into FinancialReconciliationEngine.reconcile().
    """
    tax_summary = TaxSummary(
        taxable_value=_pv(float(overall_taxable_value or 0.0), source),
        cgst_amount=_pv(float(overall_cgst_amount or 0.0), source),
        sgst_amount=_pv(float(overall_sgst_amount or 0.0), source),
        igst_amount=_pv(float(overall_igst_amount or 0.0), source),
        cess_amount=_pv(0.0, source),
        round_off=_pv(float(overall_round_off or 0.0), source),
        grand_total=_pv(float(overall_total_invoice_value or 0.0), source),
    )

    line_items: List[LineItem] = []
    for it in (sales_items or []) + (purchase_items or []):
        line_items.append(LineItem(
            description=_pv(str(it.particulars or ""), source),
            hsn_sac=_pv(str(it.hsn or ""), source),
            quantity=_pv(float(getattr(it, "qty", 0) or 0), source),
            unit=_pv("", source),
            rate=_pv(float(getattr(it, "rate", 0) or 0), source),
            discount=_pv(float(getattr(it, "discount", 0) or 0), source),
            taxable_value=_pv(float(it.taxable_value or 0.0), source),
            cgst_amount=_pv(float(it.cgst_amount or 0.0), source),
            sgst_amount=_pv(float(it.sgst_amount or 0.0), source),
            igst_amount=_pv(float(it.igst_amount or 0.0), source),
            cess_amount=_pv(0.0, source),
            advances=_pv(float(getattr(it, "advances", 0) or 0), source),
            total=_pv(float(it.total_invoice_value or 0.0), source),
        ))

    return CanonicalInvoice(
        tax_summary=tax_summary,
        line_items=line_items,
    )
