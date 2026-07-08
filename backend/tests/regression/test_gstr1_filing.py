"""
Regression tests for services.gstr1_filing - wires sales_reconciliation's
output into the existing gstr1_generator.py, gated by the reconciliation
status policy confirmed with the user 2026-07-08:
  - PASS / CLIENT_SHEET_ERROR / CLIENT_MISSING -> included normally
  - UNRESOLVED_CONFLICT -> included, but flagged
  - MISSING_SOURCE_PDF / UNVERIFIABLE_NO_GSTIN -> excluded, surfaced as skipped

Uses real invoice numbers/prefixes from this session's June 2026 batch
(MH/OMH -> Maharashtra registration, HR/OHR -> Haryana registration).
"""
import sys
import os
import unittest
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.gstr1_filing import (
    filter_items_for_filing, split_items_by_registration, generate_gstr1_filings,
    ONESTACK_REGISTRATION_MAP,
)
from backend.services.sales_reconciliation import ReconEntry, ReconStatus


@dataclass
class FakeLineItem:
    """Mimics the ORM SalesLineItem's attribute shape without a DB."""
    invoice_no: str
    party_gstin: Optional[str]
    gstr1_category: str
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


def _entry(doc_no, status, note=""):
    return ReconEntry(doc_no=doc_no, doc_type="Invoice", status=status, note=note)


class TestFilterItemsForFiling(unittest.TestCase):

    def test_pass_client_error_and_client_missing_are_included(self):
        items = [
            FakeLineItem("MH26061040", "27AAAAK0891Q2Z3", "B2B", 76.61, cgst_amount=6.89, sgst_amount=6.89, total_invoice_value=90.40),
            FakeLineItem("MH26071001", "09AAAAT0091R1ZW", "B2B", 235.51, igst_amount=42.39, total_invoice_value=277.90),
        ]
        entries = [
            _entry("MH26061040", ReconStatus.CLIENT_SHEET_ERROR),
            _entry("MH26071001", ReconStatus.CLIENT_MISSING),
        ]
        result = filter_items_for_filing(items, entries)
        self.assertEqual(len(result.included), 2)
        self.assertEqual(result.flagged_doc_nos, set())
        self.assertEqual(result.skipped, [])

    def test_unresolved_conflict_included_but_flagged(self):
        items = [FakeLineItem("CR26061011", "24AABFT9753E2Z3", "CDNR", 2500.0, igst_amount=450.0, total_invoice_value=2950.0)]
        entries = [_entry("CR26061011", ReconStatus.UNRESOLVED_CONFLICT, "amounts differ, no signal")]
        result = filter_items_for_filing(items, entries)
        self.assertEqual(len(result.included), 1)
        self.assertEqual(result.flagged_doc_nos, {"CR26061011"})

    def test_missing_source_pdf_and_no_gstin_excluded_and_surfaced(self):
        items = [
            FakeLineItem("OHR26061001", "09AAAAT1031B1Z6", "B2B", 15984.0, igst_amount=2877.12, total_invoice_value=18861.12),
            FakeLineItem("CR26061004", None, "CDNUR", 4884.84, igst_amount=879.27, total_invoice_value=5764.11),
        ]
        entries = [
            _entry("OHR26061001", ReconStatus.MISSING_SOURCE_PDF, "client has it, we don't"),
            _entry("CR26061004", ReconStatus.UNVERIFIABLE_NO_GSTIN, "no resolved GSTIN"),
        ]
        result = filter_items_for_filing(items, entries)
        self.assertEqual(result.included, [])
        self.assertEqual(len(result.skipped), 2)
        skipped_docs = {s["doc_no"] for s in result.skipped}
        self.assertEqual(skipped_docs, {"OHR26061001", "CR26061004"})

    def test_item_with_no_reconciliation_entry_is_included_by_default(self):
        # reconciliation not having run / not covering this doc is NOT the
        # same as reconciliation flagging a problem - must not block filing
        items = [FakeLineItem("MH26061999", "27AAAAA0000A1Z1", "B2B", 1000.0, cgst_amount=90, sgst_amount=90, total_invoice_value=1180.0)]
        result = filter_items_for_filing(items, [])
        self.assertEqual(len(result.included), 1)
        self.assertEqual(result.skipped, [])


class TestSplitByRegistration(unittest.TestCase):

    def test_splits_mh_and_hr_series_correctly(self):
        items = [
            FakeLineItem("MH26061040", "X", "B2B", 100.0),
            FakeLineItem("OMH26061005", "X", "B2B", 200.0),
            FakeLineItem("HR26061001", "X", "B2B", 300.0),
            FakeLineItem("OHR26061001", "X", "B2B", 400.0),
        ]
        by_reg = split_items_by_registration(items, ONESTACK_REGISTRATION_MAP)
        self.assertEqual(len(by_reg["27AADCO0061H1ZQ"]), 2)
        self.assertEqual(len(by_reg["06AADCO0061H1ZU"]), 2)

    def test_credit_note_routes_by_original_invoice_prefix_not_own_cr_prefix(self):
        # credit notes are always "CR"-prefixed regardless of which
        # registration their ORIGINAL invoice was under - "CR" itself
        # never maps to a registration. Must route via the original
        # invoice number credit_note_ingest.py embeds in particulars.
        items = [
            FakeLineItem("CR26061011", "24AABFT9753E2Z3", "CDNR", 2500.0,
                         particulars="Credit Note - Charges Reversed (against MH26041088)"),
            FakeLineItem("CR26061009", "09AAAAL8739N1ZW", "CDNR", 257.57,
                         particulars="Credit Note - Charges Reversed (against HR26041003)"),
        ]
        by_reg = split_items_by_registration(items, ONESTACK_REGISTRATION_MAP)
        self.assertEqual(len(by_reg["27AADCO0061H1ZQ"]), 1)
        self.assertEqual(len(by_reg["06AADCO0061H1ZU"]), 1)
        self.assertNotIn(None, by_reg)

    def test_credit_note_with_unparseable_particulars_falls_back_to_unknown(self):
        items = [FakeLineItem("CR26061099", "X", "CDNR", 100.0, particulars="Credit Note - no reference embedded")]
        by_reg = split_items_by_registration(items, ONESTACK_REGISTRATION_MAP)
        self.assertIn(None, by_reg)

    def test_unknown_prefix_surfaced_not_silently_dropped(self):
        items = [FakeLineItem("XYZ26061001", "X", "B2B", 100.0)]
        by_reg = split_items_by_registration(items, ONESTACK_REGISTRATION_MAP)
        self.assertIn(None, by_reg)
        self.assertEqual(len(by_reg[None]), 1)


class TestGenerateGstr1Filings(unittest.TestCase):

    def test_full_pipeline_real_shape(self):
        items = [
            FakeLineItem("MH26061040", "27AAAAK0891Q2Z3", "B2B", 76.61, cgst_amount=6.89, sgst_amount=6.89, total_invoice_value=90.40),
            FakeLineItem("HR26061001", "09AAAJA1597Q1ZO", "B2B", 1500.0, igst_amount=270.0, total_invoice_value=1770.0),
            FakeLineItem("OHR26061001", "09AAAAT1031B1Z6", "B2B", 15984.0, igst_amount=2877.12, total_invoice_value=18861.12),
        ]
        entries = [
            _entry("MH26061040", ReconStatus.CLIENT_SHEET_ERROR),
            _entry("HR26061001", ReconStatus.PASS),
            _entry("OHR26061001", ReconStatus.MISSING_SOURCE_PDF, "client has it, we don't"),
        ]
        results = generate_gstr1_filings(items, entries, ONESTACK_REGISTRATION_MAP)

        self.assertIn("27AADCO0061H1ZQ", results)
        self.assertIn("06AADCO0061H1ZU", results)
        mh_result = results["27AADCO0061H1ZQ"]
        self.assertIsNotNone(mh_result["gstr1_json"])
        self.assertEqual(mh_result["gstr1_json"]["gstin"], "27AADCO0061H1ZQ")

        hr_result = results["06AADCO0061H1ZU"]
        # OHR26061001 was excluded (MISSING_SOURCE_PDF) - only HR26061001's
        # invoice should have made it into the HR registration's filing
        self.assertEqual(len(hr_result["gstr1_json"]["b2b"]), 1)
        self.assertEqual(len(hr_result["all_skipped_this_period"]), 1)
        self.assertEqual(hr_result["all_skipped_this_period"][0]["doc_no"], "OHR26061001")


if __name__ == "__main__":
    unittest.main()
