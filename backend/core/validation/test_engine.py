import unittest
from backend.core.schema import (
    CanonicalInvoice, Supplier, Buyer, InvoiceMetadata, TaxSummary, LineItem, Classification, ProvenancedValue
)
from backend.core.validation import ValidationEngine
from backend.core.validation.registry import RuleRegistry

class TestCAValidationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ValidationEngine()

    def test_happy_path_invoice(self):
        invoice = CanonicalInvoice()
        
        # Populate happy path metadata
        invoice.invoice_metadata.invoice_number.value = "INV-2026-001"
        invoice.invoice_metadata.invoice_date.value = "27-Jun-2026"
        invoice.invoice_metadata.due_date.value = "30-Jun-2026"
        invoice.invoice_metadata.invoice_type.value = "Sales"
        invoice.invoice_metadata.currency.value = "INR"
        invoice.invoice_metadata.reverse_charge.value = False
        invoice.invoice_metadata.place_of_supply.value = "Maharashtra"
        invoice.classification.gstr1_category = "B2B"
        
        # Parties
        invoice.supplier.legal_name.value = "Acme Corp"
        invoice.supplier.gstin.value = "27AAAAA1111A1Z1"
        invoice.supplier.state_code.value = "27"
        
        invoice.buyer.name.value = "Beta Systems"
        invoice.buyer.gstin.value = "27BBBBB2222B2Z2"
        invoice.buyer.state_code.value = "27"
        
        # Line Items
        item = LineItem(
            description=ProvenancedValue[str](value="Laptop computer"),
            quantity=ProvenancedValue[float](value=1.0),
            rate=ProvenancedValue[float](value=50000.0),
            taxable_value=ProvenancedValue[float](value=50000.0),
            cgst_amount=ProvenancedValue[float](value=4500.0),
            sgst_amount=ProvenancedValue[float](value=4500.0),
            total=ProvenancedValue[float](value=59000.0)
        )
        invoice.line_items.append(item)
        
        # Summary
        invoice.tax_summary.taxable_value.value = 50000.0
        invoice.tax_summary.cgst_amount.value = 4500.0
        invoice.tax_summary.sgst_amount.value = 4500.0
        invoice.tax_summary.grand_total.value = 59000.0
        
        report = self.engine.validate(invoice)
        self.assertEqual(report.overall_status, "ERP_READY")
        self.assertEqual(report.overall_score, 100.0)
        self.assertEqual(len(report.failed_rules), 0)

    def test_dependency_skipping(self):
        invoice = CanonicalInvoice()
        # Missing supplier GSTIN -> GST_001 fails
        invoice.supplier.gstin.value = ""
        invoice.buyer.gstin.value = "27BBBBB2222B2Z2"
        
        report = self.engine.validate(invoice)
        # GST_001 fails because gstin is missing
        self.assertIn("GST_001", report.failed_rules)
        # GST_002 depends on GST_001 in our configuration (RuleGST002 class depends_on = ["GST_001"])
        # Thus, GST_002 fails/skips automatically because GST_001 failed
        self.assertIn("GST_002", report.failed_rules)
        
        # Verify reason traces the skip
        gst_002_res = next(r for r in report.results if r.rule_id == "GST_002")
        self.assertIn("Skipped", gst_002_res.message)

    def test_math_total_mismatch(self):
        invoice = CanonicalInvoice()
        
        # Populate metadata
        invoice.invoice_metadata.invoice_number.value = "INV-2026-002"
        invoice.invoice_metadata.invoice_date.value = "27-Jun-2026"
        invoice.invoice_metadata.invoice_type.value = "Sales"
        invoice.supplier.legal_name.value = "Acme Corp"
        invoice.buyer.name.value = "Beta Systems"
        
        # Mismatched math: taxable + tax != grand total
        invoice.tax_summary.taxable_value.value = 1000.0
        invoice.tax_summary.cgst_amount.value = 90.0
        invoice.tax_summary.sgst_amount.value = 90.0
        # Grand total is set to 2000.0 instead of 1180.0
        invoice.tax_summary.grand_total.value = 2000.0
        
        report = self.engine.validate(invoice)
        self.assertIn("MATH_001", report.failed_rules)
        self.assertEqual(report.math_status, "FAILED")

if __name__ == "__main__":
    unittest.main()
