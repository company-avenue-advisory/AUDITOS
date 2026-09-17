import unittest
from unittest.mock import MagicMock, patch


class TestTryVisionExtraction(unittest.TestCase):
    """
    Unit tests for invoice_processor._try_vision_extraction's mapping of
    vision_extractor's raw dict schema into SuvitPurchaseItem +
    InvoiceExtractionResponse. Mocks the DB session and the vision call
    itself, no real DB or network needed.
    """

    def _make_fake_tenant(self, gstin="27AAAAA1111A1Z1", name="Test Buyer Pvt Ltd"):
        tenant = MagicMock()
        tenant.gstin = gstin
        tenant.name = name
        return tenant

    def test_maps_vision_output_into_purchase_items_and_overall_totals(self):
        from invoice_processor import _try_vision_extraction

        fake_invoices = [{
            "invoice_no": "2026101",
            "invoice_date": "15-Apr-26",
            "party_gstin": "07BBBBB2222B1Z2",
            "party_ledger_name": "Rajiv Jain",
            "place_of_supply": "Haryana",
            "items": [
                {"name_of_item": "AC AMC Service", "hsn": "9987", "quantity": 1, "rate": 42763.0,
                 "amount": 42763.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_amount": 42763.0},
            ],
        }]

        with patch("database.SessionLocal") as mock_session_cls, \
             patch("models.Tenant") as mock_tenant_cls, \
             patch("vision_scan_extraction.extract_scan_via_vision", return_value=fake_invoices) as mock_extract:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = self._make_fake_tenant()

            result = _try_vision_extraction("/tmp/fake_scan.pdf", tenant_id="tenant-123")

        mock_extract.assert_called_once_with("/tmp/fake_scan.pdf", "Test Buyer Pvt Ltd", "27AAAAA1111A1Z1")
        self.assertIsNotNone(result)
        self.assertEqual(len(result.purchase_items), 1)
        item = result.purchase_items[0]
        self.assertEqual(item.invoice_no, "2026101")
        self.assertEqual(item.party_gstin, "07BBBBB2222B1Z2")
        self.assertEqual(item.taxable_value, 42763.0)
        self.assertEqual(result.overall_taxable_value, 42763.0)
        self.assertEqual(result.overall_total_invoice_value, 42763.0)

    def test_no_tenant_gstin_falls_through(self):
        from invoice_processor import _try_vision_extraction

        with patch("database.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = self._make_fake_tenant(gstin=None)

            result = _try_vision_extraction("/tmp/fake_scan.pdf", tenant_id="tenant-123")

        self.assertIsNone(result)

    def test_vision_call_failure_falls_through(self):
        from invoice_processor import _try_vision_extraction

        with patch("database.SessionLocal") as mock_session_cls, \
             patch("vision_scan_extraction.extract_scan_via_vision", side_effect=RuntimeError("API down")):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = self._make_fake_tenant()

            result = _try_vision_extraction("/tmp/fake_scan.pdf", tenant_id="tenant-123")

        self.assertIsNone(result)

    def test_no_items_extracted_falls_through(self):
        from invoice_processor import _try_vision_extraction

        with patch("database.SessionLocal") as mock_session_cls, \
             patch("vision_scan_extraction.extract_scan_via_vision", return_value=[]):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = self._make_fake_tenant()

            result = _try_vision_extraction("/tmp/fake_scan.pdf", tenant_id="tenant-123")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
