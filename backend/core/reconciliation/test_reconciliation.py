import unittest
from backend.core.schema import CanonicalInvoice, LineItem, ProvenancedValue
from backend.core.reconciliation import FinancialReconciliationEngine, resolve_financial_candidates
from backend.core.extraction.candidate_detector.candidate import Candidate

class TestFinancialReconciliationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = FinancialReconciliationEngine()

    def test_perfect_invoice(self):
        invoice = CanonicalInvoice()
        invoice.supplier.gstin.value = "27AAAAA1111A1Z1"
        invoice.buyer.gstin.value = "27BBBBB2222B2Z2"
        
        # Line item
        item = LineItem(
            description=ProvenancedValue[str](value="Goods"),
            quantity=ProvenancedValue[float](value=1.0),
            rate=ProvenancedValue[float](value=1000.0),
            taxable_value=ProvenancedValue[float](value=1000.0),
            cgst_amount=ProvenancedValue[float](value=90.0),
            sgst_amount=ProvenancedValue[float](value=90.0),
            total=ProvenancedValue[float](value=1180.0)
        )
        invoice.line_items.append(item)
        
        invoice.tax_summary.taxable_value.value = 1000.0
        invoice.tax_summary.cgst_amount.value = 90.0
        invoice.tax_summary.sgst_amount.value = 90.0
        invoice.tax_summary.grand_total.value = 1180.0
        
        report = self.engine.reconcile(invoice)
        self.assertTrue(report.is_reconciled)
        self.assertEqual(report.status, "ERP_READY")
        self.assertEqual(report.variance_taxable, 0.0)

    def test_taxable_variance_blocking(self):
        invoice = CanonicalInvoice()
        invoice.supplier.gstin.value = "27AAAAA1111A1Z1"
        invoice.buyer.gstin.value = "27BBBBB2222B2Z2"
        
        # Line sum is 1000.0
        item = LineItem(
            taxable_value=ProvenancedValue[float](value=1000.0),
            total=ProvenancedValue[float](value=1000.0)
        )
        invoice.line_items.append(item)
        
        # Summary taxable is set to 2000.0
        invoice.tax_summary.taxable_value.value = 2000.0
        invoice.tax_summary.grand_total.value = 2000.0
        
        report = self.engine.reconcile(invoice)
        self.assertFalse(report.is_reconciled)
        # Summary mismatch blocks export
        self.assertEqual(report.status, "BLOCKED")
        self.assertIn("taxable_value", [item.field_name for item in report.review_context.items])
        
    def test_candidate_scoring(self):
        c1 = Candidate(field="taxable_value", value="1000", page=1, line=5, keyword="taxable", bbox=None, method="regex", confidence=0.8, context="Total taxable: 1000")
        c2 = Candidate(field="taxable_value", value="1050", page=1, line=7, keyword="taxable", bbox=None, method="regex", confidence=0.9, context="Taxable amount: 1050")
        
        # Resolve candidates matching math expected value of 1000.0
        val, score, log = resolve_financial_candidates([c1, c2], "taxable_value", math_value=1000.0)
        self.assertEqual(val, 1000.0)
        self.assertIn("Selected Candidate value: 1000", log)

if __name__ == "__main__":
    unittest.main()
