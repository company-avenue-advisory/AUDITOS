import unittest
from backend.core.extraction.extractor import sum_line_item_taxes


class TestSumLineItemTaxes(unittest.TestCase):
    def test_matches_real_invoice_with_no_summary_tax_row(self):
        # Real production case: "We work_GGN_INV_262700001038" -- a 7-line
        # invoice where CGST/SGST are only ever printed per-line, with no
        # separate "Total CGST"/"Total SGST" summary row anywhere on the
        # page. The totals-region LLM call returned 0 for both, producing a
        # ₹1,29,211.84 total variance (exactly the missing tax) even though
        # every line item was extracted correctly.
        items = [
            {"taxable_value": 57843.58, "cgst_amount": 5205.92, "sgst_amount": 5205.92, "igst_amount": 0},
            {"taxable_value": 152000.0, "cgst_amount": 13680.0, "sgst_amount": 13680.0, "igst_amount": 0},
            {"taxable_value": 152000.0, "cgst_amount": 13680.0, "sgst_amount": 13680.0, "igst_amount": 0},
            {"taxable_value": 152000.0, "cgst_amount": 13680.0, "sgst_amount": 13680.0, "igst_amount": 0},
            {"taxable_value": 14000.0, "cgst_amount": 1260.0, "sgst_amount": 1260.0, "igst_amount": 0},
            {"taxable_value": 76000.0, "cgst_amount": 6840.0, "sgst_amount": 6840.0, "igst_amount": 0},
            {"taxable_value": 114000.0, "cgst_amount": 10260.0, "sgst_amount": 10260.0, "igst_amount": 0},
        ]
        result = sum_line_item_taxes(items)
        self.assertAlmostEqual(result["overall_taxable_value"], 717843.58, places=2)
        self.assertAlmostEqual(result["overall_cgst_amount"], 64605.92, places=2)
        self.assertAlmostEqual(result["overall_sgst_amount"], 64605.92, places=2)
        self.assertAlmostEqual(result["overall_igst_amount"], 0.0, places=2)

        grand_total = result["overall_taxable_value"] + result["overall_cgst_amount"] + result["overall_sgst_amount"]
        self.assertAlmostEqual(grand_total, 847055.42, places=2)

    def test_empty_items_sums_to_zero(self):
        result = sum_line_item_taxes([])
        self.assertEqual(result, {
            "overall_taxable_value": 0.0,
            "overall_cgst_amount": 0.0,
            "overall_sgst_amount": 0.0,
            "overall_igst_amount": 0.0,
        })

    def test_missing_or_none_fields_treated_as_zero(self):
        items = [{"taxable_value": 100.0}, {"cgst_amount": None, "sgst_amount": 5.0}]
        result = sum_line_item_taxes(items)
        self.assertEqual(result["overall_taxable_value"], 100.0)
        self.assertEqual(result["overall_sgst_amount"], 5.0)
        self.assertEqual(result["overall_cgst_amount"], 0.0)


if __name__ == "__main__":
    unittest.main()
