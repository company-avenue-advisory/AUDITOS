"""
Regression tests for services.gstr1_generator - specifically the
credit-note categorization + net-taxable-total bug found against a real
MH (Maharashtra, 27AADCO0061H1ZQ) filing this session:

  Summary For B2CS(7): Type OE, POS 36-Telangana, Rate 18.00,
  Taxable Value -7246.77

B2CS taxable value can never legitimately be negative on the GST portal.
Root cause: _group_by_invoice keyed unclassified rows by
"item.gstr1_category or 'B2CS'" - a credit note ingested via
credit_note_ingest.py never gets gstr1_category set (only regular
invoices go through classify_gstr1_item), so it silently fell into the
B2CS bucket instead of CDNR/CDNUR, and _build_b2cs summed its (positive-
stored, per extract_credit_note's docstring) taxable value alongside
regular B2CS invoices for the same (state, rate) - and separately, the
envelope's total_taxable summed every row including credit notes as if
they were more sales instead of a deduction, so the filed total never
matched the source PDFs either.

Fixed via _resolve_category (voucher_type is now authoritative for
credit/debit notes, regardless of what gstr1_category was or wasn't
set to) and by netting credit/debit notes out of the summary totals.
"""
import sys
import os
import unittest
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.gstr1_generator import generate_gstr1_json, _resolve_category, _build_hsn


@dataclass
class FakeLineItem:
    invoice_no: str
    party_gstin: Optional[str]
    gstr1_category: Optional[str]
    taxable_value: float
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    total_invoice_value: float = 0.0
    voucher_date: str = "30-06-2026"
    voucher_type: str = "Sales"
    place_of_supply: Optional[str] = None
    hsn: Optional[str] = "9971"
    particulars: str = "SaaS/UPI Platform Charges"
    qty: float = 1.0


class TestResolveCategory(unittest.TestCase):

    def test_credit_note_with_no_gstr1_category_routes_to_cdnr_not_b2cs(self):
        # exactly the real-world shape: credit_note_ingest.py never sets
        # gstr1_category, so it's None here - the bug defaulted this to B2CS.
        item = FakeLineItem("CR26061099", "27AAAAK0891Q2Z3", None, 7246.77,
                            igst_amount=1304.42, total_invoice_value=8551.19,
                            voucher_type="Credit Note")
        self.assertEqual(_resolve_category(item), "CDNR")

    def test_credit_note_without_gstin_routes_to_cdnur_not_b2cs(self):
        item = FakeLineItem("CR26061100", None, None, 7246.77,
                             igst_amount=1304.42, voucher_type="Credit Note")
        self.assertEqual(_resolve_category(item), "CDNUR")

    def test_debit_note_also_routes_correctly(self):
        item = FakeLineItem("DR26061001", "27AAAAK0891Q2Z3", None, 500.0, voucher_type="Debit Note")
        self.assertEqual(_resolve_category(item), "CDNR")

    def test_regular_invoice_unaffected(self):
        item = FakeLineItem("MH26061040", "27AAAAK0891Q2Z3", "B2B", 76.61)
        self.assertEqual(_resolve_category(item), "B2B")

    def test_unclassified_regular_item_still_defaults_to_b2cs(self):
        # only credit/debit notes get the voucher_type override - a
        # regular invoice that was never classified still falls back to
        # the existing B2CS default (unrelated to this bug).
        item = FakeLineItem("MH26061999", None, None, 100.0)
        self.assertEqual(_resolve_category(item), "B2CS")


class TestB2CSNeverGoesNegativeFromCreditNotes(unittest.TestCase):

    def test_credit_note_no_longer_corrupts_b2cs_bucket(self):
        # Reproduces the real MH bug: a Telangana, 18% B2CS invoice plus a
        # same-state-and-rate credit note that was never classified.
        items = [
            FakeLineItem("MH26061041", None, "B2CS", 5000.0, igst_amount=900.0,
                         total_invoice_value=5900.0, place_of_supply="36-Telangana"),
            FakeLineItem("CR26061099", None, None, 7246.77, igst_amount=1304.42,
                         total_invoice_value=8551.19, place_of_supply="36-Telangana",
                         voucher_type="Credit Note"),
        ]
        result = generate_gstr1_json(items, firm_gstin="27AADCO0061H1ZQ")

        # B2CS must only contain the actual B2CS invoice - never negative,
        # never including the credit note's amount.
        b2cs_total_txval = sum(e["txval"] for e in result["b2cs"])
        self.assertEqual(b2cs_total_txval, 5000.0)
        self.assertTrue(all(e["txval"] >= 0 for e in result["b2cs"]))

        # the credit note must appear in cdnur instead (no GSTIN resolved)
        self.assertEqual(len(result["cdnur"]), 1)
        self.assertEqual(result["cdnur"][0]["itms"][0]["itm_det"]["txval"], 7246.77)

    def test_summary_total_taxable_nets_credit_notes_not_sums_them(self):
        items = [
            FakeLineItem("MH26061041", "27AAAAK0891Q2Z3", "B2B", 5000.0,
                         cgst_amount=450.0, sgst_amount=450.0, total_invoice_value=5900.0),
            FakeLineItem("CR26061099", "27AAAAK0891Q2Z3", None, 1000.0,
                         cgst_amount=90.0, sgst_amount=90.0, total_invoice_value=1180.0,
                         voucher_type="Credit Note"),
        ]
        result = generate_gstr1_json(items, firm_gstin="27AADCO0061H1ZQ")

        # net = 5000 - 1000 = 4000, NOT 6000 (which is what a plain sum -
        # the pre-fix bug - would have produced)
        self.assertEqual(result["_summary"]["total_taxable"], 4000.0)
        self.assertEqual(result["_summary"]["total_cgst"], 360.0)
        self.assertEqual(result["_summary"]["total_sgst"], 360.0)


class TestHSNSummaryNetsCreditNotes(unittest.TestCase):
    """
    Reproduces the exact real MH data an accountant flagged this session:
    HSN 997319 previously showed 1,694,121 taxable (invoice-only) with no
    credit notes deducted at all - the pre-fix behavior silently omitted
    credit notes from the HSN sheet entirely rather than netting them,
    overstating every HSN bucket a credit note touched.
    """

    def test_credit_note_reduces_its_hsn_bucket_not_omitted(self):
        # both at a clean 18% (9% CGST + 9% SGST) so they land in the same
        # (hsn, rate) bucket - real invoice/credit-note pairs at mismatched
        # blended rates would land in separate buckets, which is correct
        # behavior, not this test's concern.
        items = [
            FakeLineItem("MH26061999", "27AAAAK0891Q2Z3", "B2B", 1694121.0,
                         cgst_amount=152570.89, sgst_amount=152570.89, igst_amount=0.0,
                         total_invoice_value=1999262.78, hsn="997319"),
            # Pandharpur-shaped: intrastate CGST+SGST credit note, same HSN
            FakeLineItem("CR26061001", "27AAAAT3361L1ZA", None, 47952.0,
                         cgst_amount=4315.68, sgst_amount=4315.68, igst_amount=0.0,
                         total_invoice_value=56583.36, hsn="997319", voucher_type="Credit Note"),
        ]
        hsn = _build_hsn(items)
        row = hsn["data"][0]
        self.assertAlmostEqual(row["txval"], 1694121.0 - 47952.0, places=2)
        self.assertAlmostEqual(row["camt"], 152570.89 - 4315.68, places=2)
        self.assertAlmostEqual(row["samt"], 152570.89 - 4315.68, places=2)

    def test_hsn_bucket_with_only_a_credit_note_goes_negative_not_missing(self):
        # Pochampally-shaped: an HSN bucket where the only line item this
        # period is a credit note (no offsetting invoice) - it must still
        # appear (negative), not be silently dropped.
        items = [
            FakeLineItem("CR26061004", None, None, 4884.84, igst_amount=879.27,
                         total_invoice_value=5764.11, hsn="0", voucher_type="Credit Note"),
        ]
        hsn = _build_hsn(items)
        self.assertEqual(len(hsn["data"]), 1)
        self.assertEqual(hsn["data"][0]["txval"], -4884.84)


if __name__ == "__main__":
    unittest.main()
