import unittest
from datetime import datetime
from backend.core.schema import (
    DocumentBundle, Document, CanonicalInvoice, LineItem, 
    ProvenancedValue, FieldConfidence, FieldProvenance
)
from backend.core.mappers.gemini_mapper import map_gemini_to_canonical
from backend.core.mappers.sql_mapper import (
    map_sql_items_to_canonical, map_canonical_to_sales_items, map_canonical_to_purchase_items
)
from backend.models import SalesLineItem, PurchaseLineItem

class TestCanonicalInvoiceSchema(unittest.TestCase):

    def test_versioning_and_defaults(self):
        bundle = DocumentBundle()
        self.assertEqual(bundle.schema_version, "1.0.0")
        self.assertEqual(bundle.pipeline_version, "1.0.0")
        self.assertIsInstance(bundle.created_at, datetime)
        self.assertIsNone(bundle.invoice)

    def test_field_provenance_and_confidence(self):
        provenance = FieldProvenance(
            page_number=1,
            source_type="ocr",
            source_raw_text="INV-12345",
            bounding_box=[0.1, 0.2, 0.3, 0.4]
        )
        confidence = FieldConfidence(
            score=0.98,
            source="Gemini",
            method="Layout + OCR",
            verified=True,
            reason="Matches invoice template format"
        )
        provenanced_str = ProvenancedValue[str](
            value="INV-12345",
            confidence=confidence,
            provenance=provenance
        )
        self.assertEqual(provenanced_str.value, "INV-12345")
        self.assertEqual(provenanced_str.confidence.score, 0.98)
        self.assertEqual(provenanced_str.provenance.page_number, 1)

    def test_gemini_mapper_sales(self):
        mock_response = {
            "overall_taxable_value": 1000.0,
            "overall_cgst_amount": 90.0,
            "overall_sgst_amount": 90.0,
            "overall_igst_amount": 0.0,
            "overall_total_invoice_value": 1180.0,
            "sales_items": [
                {
                    "voucher_date": "2026-06-27",
                    "voucher_type": "Sales",
                    "invoice_no": "S-001",
                    "party_ledger_name": "Acme Corp",
                    "party_gstin": "27AAAAA1111A1Z1",
                    "place_of_supply": "Maharashtra",
                    "particulars": "Consulting Services",
                    "hsn": "998311",
                    "qty": 1.0,
                    "rate": 1000.0,
                    "taxable_value": 1000.0,
                    "discount": 0.0,
                    "cgst_amount": 90.0,
                    "sgst_amount": 90.0,
                    "igst_amount": 0.0,
                    "total_invoice_value": 1180.0,
                    "gstr1_category": "B2B"
                }
            ],
            "purchase_items": []
        }
        
        canonical = map_gemini_to_canonical(mock_response)
        self.assertEqual(canonical.invoice_metadata.invoice_number.value, "S-001")
        self.assertEqual(canonical.buyer.name.value, "Acme Corp")
        self.assertEqual(canonical.buyer.gstin.value, "27AAAAA1111A1Z1")
        self.assertEqual(canonical.invoice_metadata.invoice_type.value, "Sales")
        self.assertEqual(canonical.tax_summary.grand_total.value, 1180.0)
        self.assertEqual(len(canonical.line_items), 1)
        self.assertEqual(canonical.line_items[0].description.value, "Consulting Services")
        self.assertEqual(canonical.classification.gstr1_category, "B2B")

    def test_sql_bidirectional_mapping(self):
        # Create SalesLineItem
        sql_item = SalesLineItem(
            task_id="task_abc",
            voucher_date="2026-06-27",
            voucher_type="Sales",
            invoice_no="S-002",
            party_ledger_name="Beta Corp",
            party_gstin="27BBBBB2222B2Z2",
            place_of_supply="Maharashtra",
            particulars="Laptop",
            hsn="8471",
            qty=2.0,
            rate=50000.0,
            taxable_value=100000.0,
            discount=0.0,
            cgst_amount=9000.0,
            sgst_amount=9000.0,
            igst_amount=0.0,
            total_invoice_value=118000.0,
            gstr1_category="B2B"
        )
        
        canonical = map_sql_items_to_canonical([sql_item])
        self.assertIsNotNone(canonical)
        self.assertEqual(canonical.buyer.name.value, "Beta Corp")
        self.assertEqual(canonical.buyer.gstin.value, "27BBBBB2222B2Z2")
        self.assertEqual(canonical.invoice_metadata.invoice_number.value, "S-002")
        self.assertEqual(canonical.tax_summary.taxable_value.value, 100000.0)

        # Convert back to SQL
        sql_items_back = map_canonical_to_sales_items(canonical, task_id="task_abc")
        self.assertEqual(len(sql_items_back), 1)
        back_item = sql_items_back[0]
        self.assertEqual(back_item.invoice_no, "S-002")
        self.assertEqual(back_item.party_ledger_name, "Beta Corp")
        self.assertEqual(back_item.qty, 2.0)
        self.assertEqual(back_item.rate, 50000.0)
        self.assertEqual(back_item.taxable_value, 100000.0)
        self.assertEqual(back_item.gstr1_category, "B2B")

if __name__ == "__main__":
    unittest.main()
