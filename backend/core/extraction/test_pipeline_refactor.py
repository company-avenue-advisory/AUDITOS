import unittest
from unittest.mock import MagicMock, patch
import os
from backend.core.schema.processing import ProcessingContext
from backend.core.extraction.loader import load_document
from backend.core.extraction.ocr import extract_ocr_document
from backend.core.extraction.layout import analyze_layout
from backend.core.extraction.candidate_detector import run_all_detectors
from backend.core.resolver import resolve_all_candidates
from backend.core.extraction.pipeline import process_document

class TestExtractionPipelineRefactor(unittest.TestCase):

    def setUp(self):
        # We can use the mock PDFs available in the workspace root
        self.test_pdf = os.path.abspath("mock_sales_b2b.pdf")
        if not os.path.exists(self.test_pdf):
            # Create a dummy file if not exists
            with open(self.test_pdf, "wb") as f:
                f.write(b"%PDF-1.4 dummy contents")

    def test_document_loader(self):
        doc = load_document(self.test_pdf)
        self.assertEqual(doc.metadata.filename, "mock_sales_b2b.pdf")
        self.assertIsNotNone(doc.metadata.checksum)

    def test_ocr_and_layout(self):
        ocr_doc = extract_ocr_document(self.test_pdf)
        self.assertIsNotNone(ocr_doc.pages)
        self.assertTrue(len(ocr_doc.pages) >= 1)
        
        layout = analyze_layout(ocr_doc)
        self.assertIsNotNone(layout.get_region_text("metadata_region"))

    def test_candidate_detection_and_resolvers(self):
        ocr_doc = extract_ocr_document(self.test_pdf)
        # Inject mock text to force candidate matches
        ocr_doc.pages[0].raw_text = (
            "Invoice No: INV-9999\n"
            "Date: 27-Jun-2026\n"
            "Supplier GSTIN: 27AAAAA1111A1Z1\n"
            "Total Amount: 1180.00\n"
            "Subtotal: 1000.00\n"
        )
        
        candidates = run_all_detectors(ocr_doc)
        self.assertTrue(any(c.field == "invoice_number" for c in candidates))
        self.assertTrue(any(c.field == "gstin" for c in candidates))
        
        resolved = resolve_all_candidates(candidates)
        self.assertEqual(resolved["invoice_number"].value, "INV-9999")
        self.assertEqual(resolved["supplier_gstin"].value, "27AAAAA1111A1Z1")
        self.assertEqual(resolved["grand_total"].value, 1180.00)

    @patch("backend.core.extraction.pipeline.OpenAI")
    def test_pipeline_orchestrator(self, mock_openai):
        # Mock client responses
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        mock_choice = MagicMock()
        mock_choice.message.content = '{"invoice_no": "INV-9999", "voucher_date": "27-Jun-2026", "party_ledger_name": "Test Client", "party_gstin": "27AAAAA1111A1Z1", "overall_total_invoice_value": 1180.0, "items": []}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]
        
        context = ProcessingContext(
            run_id="run_test_001",
            batch_id="batch_test",
            task_id="task_test_001",
            tenant_id="tenant_default",
            firm_id="firm_default",
            provider="google_native",
            model="gemini-2.5-flash",
            temperature=0.0,
            prompt_version="1.0.0",
            feature_flags={},
            configuration={"invoice_type": "Sales"}
        )
        
        bundle = process_document(self.test_pdf, context)
        self.assertEqual(bundle.invoice.invoice_metadata.invoice_number.value, "INV-9999")
        self.assertEqual(bundle.invoice.buyer.name.value, "Test Client")
        self.assertEqual(bundle.invoice.buyer.gstin.value, "27AAAAA1111A1Z1")

if __name__ == "__main__":
    unittest.main()
