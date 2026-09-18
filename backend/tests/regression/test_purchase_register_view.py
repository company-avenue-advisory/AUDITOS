"""
Regression test for services.output_schema.PURCHASE_REGISTER_VIEW — locks in
the new 13-column OneStack Template layout (replacing the prior 19-column
Tally-style layout), so a future edit can't silently drift from
Vendor Invoices/Vendor_Invoice_OneStack_Template.xlsx (the confirmed
reference; not committed to the repo, so this test hardcodes its exact
header row instead of reading the file).
"""
import os
import sys
import unittest
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.output_schema import PURCHASE_REGISTER_VIEW, labels, row_for

# Exact header row from Vendor_Invoice_OneStack_Template.xlsx, row 1.
TEMPLATE_HEADERS = [
    "SUPPLIER INV NO", "INVOICE DATE", "GST NO", "PARTY A/C NAME", "PLACE OF SUPPLY",
    "PARTICULARS", "AMOUNT", "SGST", "CGST", "IGST", "TOTAL AMOUNT", "Narration", "HSN",
]


@dataclass
class FakePurchaseItem:
    invoice_no: str
    voucher_date: str
    party_gstin: str
    party_ledger_name: str
    place_of_supply: str
    particulars: str
    taxable_value: float
    sgst_amount: float
    cgst_amount: float
    igst_amount: float
    total_invoice_value: float
    narration: str
    hsn: str


class TestPurchaseRegisterView(unittest.TestCase):
    def test_headers_match_onestack_template_exactly(self):
        self.assertEqual(labels(PURCHASE_REGISTER_VIEW), TEMPLATE_HEADERS)

    def test_row_values_align_with_headers(self):
        item = FakePurchaseItem(
            invoice_no="TEST-INV-001", voucher_date="27-02-2026", party_gstin="27AAAAA1111A1Z1",
            party_ledger_name="Test Vendor Pvt. Ltd.", place_of_supply="Maharashtra",
            particulars="Warehouse Rent Expense", taxable_value=3800.0, sgst_amount=0.0,
            cgst_amount=0.0, igst_amount=684.0, total_invoice_value=4484.0,
            narration="Warehouse rent, operations & order-processing charges for Feb-2026 (200 sqft).",
            hsn="997213",
        )
        row = dict(zip(labels(PURCHASE_REGISTER_VIEW), row_for(PURCHASE_REGISTER_VIEW, item)))
        self.assertEqual(row["SUPPLIER INV NO"], "TEST-INV-001")
        self.assertEqual(row["GST NO"], "27AAAAA1111A1Z1")
        self.assertEqual(row["AMOUNT"], 3800.0)
        self.assertEqual(row["IGST"], 684.0)
        self.assertEqual(row["HSN"], "997213")
        self.assertIn("Warehouse rent", row["Narration"])


if __name__ == "__main__":
    unittest.main()
