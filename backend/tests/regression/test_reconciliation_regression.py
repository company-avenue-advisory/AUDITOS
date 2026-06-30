"""
Regression tests for FinancialReconciliationEngine.

Tests lock the status, is_reconciled flag, and variance values so that
any change to the 8-stage reconciliation logic is immediately surfaced.

No LLM calls — all inputs are hand-constructed CanonicalInvoice objects.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.core.schema import CanonicalInvoice, LineItem, ProvenancedValue
from backend.core.reconciliation import FinancialReconciliationEngine


def _make_engine():
    return FinancialReconciliationEngine()


def _pv(val):
    """Shorthand: wrap a value in ProvenancedValue."""
    return ProvenancedValue(value=val)


def _build_intrastate_invoice(taxable=10000.0, cgst=900.0, sgst=900.0, total=11800.0):
    """Perfect intrastate B2B invoice — all math consistent."""
    inv = CanonicalInvoice()
    inv.supplier.gstin = _pv("27AAAAA1111A1Z1")
    inv.buyer.gstin    = _pv("27BBBBB2222B2Z2")

    item = LineItem()
    item.taxable_value = _pv(taxable)
    item.cgst_amount   = _pv(cgst)
    item.sgst_amount   = _pv(sgst)
    item.igst_amount   = _pv(0.0)
    item.total         = _pv(total)
    inv.line_items.append(item)

    inv.tax_summary.taxable_value = _pv(taxable)
    inv.tax_summary.cgst_amount   = _pv(cgst)
    inv.tax_summary.sgst_amount   = _pv(sgst)
    inv.tax_summary.igst_amount   = _pv(0.0)
    inv.tax_summary.grand_total   = _pv(total)
    return inv


def _build_interstate_invoice():
    """Perfect interstate B2B invoice — IGST only."""
    inv = CanonicalInvoice()
    inv.supplier.gstin = _pv("27AAAAA1111A1Z1")
    inv.buyer.gstin    = _pv("29CCCCC3333C3Z3")

    item = LineItem()
    item.taxable_value = _pv(100000.0)
    item.cgst_amount   = _pv(0.0)
    item.sgst_amount   = _pv(0.0)
    item.igst_amount   = _pv(18000.0)
    item.total         = _pv(118000.0)
    inv.line_items.append(item)

    inv.tax_summary.taxable_value = _pv(100000.0)
    inv.tax_summary.cgst_amount   = _pv(0.0)
    inv.tax_summary.sgst_amount   = _pv(0.0)
    inv.tax_summary.igst_amount   = _pv(18000.0)
    inv.tax_summary.grand_total   = _pv(118000.0)
    return inv


class TestReconciliationHappyPath(unittest.TestCase):

    def setUp(self):
        self.engine = _make_engine()

    def test_perfect_intrastate_reconciles(self):
        report = self.engine.reconcile(_build_intrastate_invoice())
        self.assertTrue(report.is_reconciled, "Perfect intrastate invoice must reconcile")
        self.assertEqual(report.status, "ERP_READY")
        self.assertAlmostEqual(report.variance_taxable, 0.0, places=2)

    def test_perfect_interstate_reconciles(self):
        report = self.engine.reconcile(_build_interstate_invoice())
        self.assertTrue(report.is_reconciled, "Perfect interstate invoice must reconcile")
        self.assertEqual(report.status, "ERP_READY")

    def test_intrastate_variance_is_zero(self):
        report = self.engine.reconcile(_build_intrastate_invoice())
        self.assertAlmostEqual(report.variance_taxable, 0.0, places=2)

    def test_report_has_required_fields(self):
        report = self.engine.reconcile(_build_intrastate_invoice())
        self.assertIsNotNone(report.status)
        self.assertIsNotNone(report.is_reconciled)
        self.assertIsNotNone(report.review_context)


class TestReconciliationVarianceBlocking(unittest.TestCase):

    def setUp(self):
        self.engine = _make_engine()

    def test_taxable_mismatch_blocks(self):
        """Summary taxable (2×) doesn't match line-item sum → BLOCKED."""
        inv = _build_intrastate_invoice(taxable=10000.0, total=11800.0)
        # Override summary to wrong value
        inv.tax_summary.taxable_value = _pv(20000.0)
        inv.tax_summary.grand_total   = _pv(21800.0)

        report = self.engine.reconcile(inv)
        self.assertFalse(report.is_reconciled)
        self.assertEqual(report.status, "BLOCKED")

    def test_grand_total_mismatch_detected(self):
        """grand_total doesn't match taxable + taxes → not reconciled."""
        inv = _build_intrastate_invoice()
        # Wrong grand total
        inv.tax_summary.grand_total = _pv(99999.0)

        report = self.engine.reconcile(inv)
        self.assertFalse(report.is_reconciled)

    def test_grand_total_vs_line_sum_mismatch_blocks(self):
        """Grand total that doesn't match line-item sum + taxes → blocked."""
        inv = CanonicalInvoice()
        inv.supplier.gstin = _pv("27AAAAA1111A1Z1")
        inv.buyer.gstin    = _pv("27BBBBB2222B2Z2")

        item = LineItem()
        item.taxable_value = _pv(10000.0)
        item.cgst_amount   = _pv(900.0)
        item.sgst_amount   = _pv(900.0)
        item.igst_amount   = _pv(0.0)
        item.total         = _pv(11800.0)
        inv.line_items.append(item)

        inv.tax_summary.taxable_value = _pv(10000.0)
        inv.tax_summary.cgst_amount   = _pv(900.0)
        inv.tax_summary.sgst_amount   = _pv(900.0)
        inv.tax_summary.igst_amount   = _pv(0.0)
        # Grand total doesn't add up: taxable+CGST+SGST = 11800 but summary says 15000
        inv.tax_summary.grand_total   = _pv(15000.0)

        report = self.engine.reconcile(inv)
        self.assertFalse(report.is_reconciled)
        self.assertNotEqual(report.status, "ERP_READY")

    def test_review_context_populated_on_block(self):
        """Blocked report must have at least one review context item."""
        inv = _build_intrastate_invoice()
        inv.tax_summary.taxable_value = _pv(99999.0)

        report = self.engine.reconcile(inv)
        self.assertFalse(report.is_reconciled)
        self.assertGreater(len(report.review_context.items), 0)


class TestReconciliationEdgeCases(unittest.TestCase):

    def setUp(self):
        self.engine = _make_engine()

    def test_empty_invoice_does_not_crash(self):
        """Empty invoice must return a report without throwing."""
        inv = CanonicalInvoice()
        report = self.engine.reconcile(inv)
        self.assertIsNotNone(report)
        self.assertIsNotNone(report.status)

    def test_multi_line_item_sum_checked(self):
        """Two line items: sum must match summary taxable_value."""
        inv = CanonicalInvoice()
        inv.supplier.gstin = _pv("27AAAAA1111A1Z1")
        inv.buyer.gstin    = _pv("27BBBBB2222B2Z2")

        for tv, cgst, sgst, tot in [
            (5000.0, 450.0, 450.0, 5900.0),
            (5000.0, 450.0, 450.0, 5900.0),
        ]:
            item = LineItem()
            item.taxable_value = _pv(tv)
            item.cgst_amount   = _pv(cgst)
            item.sgst_amount   = _pv(sgst)
            item.igst_amount   = _pv(0.0)
            item.total         = _pv(tot)
            inv.line_items.append(item)

        inv.tax_summary.taxable_value = _pv(10000.0)
        inv.tax_summary.cgst_amount   = _pv(900.0)
        inv.tax_summary.sgst_amount   = _pv(900.0)
        inv.tax_summary.igst_amount   = _pv(0.0)
        inv.tax_summary.grand_total   = _pv(11800.0)

        report = self.engine.reconcile(inv)
        self.assertTrue(report.is_reconciled)
        self.assertEqual(report.status, "ERP_READY")

    def test_rounding_within_tolerance(self):
        """₹1 rounding difference must still reconcile."""
        report = self.engine.reconcile(
            _build_intrastate_invoice(total=11801.0)  # ₹1 rounding
        )
        # Rounding within tolerance should not block export
        self.assertNotEqual(report.status, "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
