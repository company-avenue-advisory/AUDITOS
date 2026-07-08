"""
Regression tests for services.sales_reconciliation - the OS-vs-client-
sheet 3-way audit engine, generalizing the manual reconciliation done by
hand this session into reusable logic.

Every case below is a REAL situation hit this session, not a hypothetical:
  - Krushiseva (MH26061040): client sheet wrongly tagged it Interstate/
    IGST; source PDF confirmed intrastate CGST+SGST. A genuine tax-type
    contradiction -> CLIENT_SHEET_ERROR.
  - Muslim Co-op (MH26061076): same pattern, much larger amount - client
    sheet showed IGST, source PDF confirmed CGST+SGST.
  - CR26061011 (Becharaji credit note): OS said Rs.2,950 total, client
    sheet said Rs.1,180 - same tax type (both IGST) on both sides, no
    contradiction signal, so this was correctly left UNRESOLVED until a
    human found and checked the actual credit-note document (which
    confirmed OS was right - but the engine can't know that without the
    document, so it must not guess).
  - Bijnor (OHR26061001): was in the client's sheet but genuinely missing
    from our own extraction until the source PDF was later found in
    Drive's "Other Invoices" folder - MISSING_SOURCE_PDF.
  - Unava (MH26071001): present in our extraction, absent from the
    client's sheet entirely - CLIENT_MISSING (their lag, not ours).
  - Pochampally's two credit notes originally had no resolved GSTIN on
    our side until their credit-note documents were found -
    UNVERIFIABLE_NO_GSTIN.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.sales_reconciliation import (
    reconcile_document, reconcile_period, ReconStatus, summarize,
    compute_net_taxable_total, reconcile_period_totals,
)


class TestReconcileDocument(unittest.TestCase):

    def test_krushiseva_tax_type_contradiction_is_client_sheet_error(self):
        # real client-sheet row for MH26061040: Supplier Location "MH"
        # (state code 27), State of Supply "27" -> should be Intrastate,
        # but the client's own manually-typed flag says "Interstate" -
        # the exact inversion, matching the confirmed 76/196 pattern
        os_data = {"taxable": 76.61, "igst": 0.0, "cgst": 6.89, "sgst": 6.89,
                   "total": 90.40, "party_gstin": "27AAAAK0891Q2Z3", "doc_type": "Invoice"}
        client_data = {"taxable": 76.61, "igst": 13.79, "cgst": 0.0, "sgst": 0.0,
                        "total": 90.40, "doc_type": "Invoice",
                        "supplier_location": "MH", "state_of_supply": "27",
                        "interstate_or_intrastate": "Interstate"}
        entry = reconcile_document(os_data, client_data, "MH26061040", "Invoice")
        self.assertEqual(entry.status, ReconStatus.CLIENT_SHEET_ERROR)
        self.assertIn("tax-type contradiction", entry.note)
        self.assertIn("known client-side pattern", entry.note)

    def test_tax_type_contradiction_without_pattern_evidence_gets_plain_note(self):
        # same contradiction, but client_data doesn't carry the
        # supplier_location/state_of_supply fields needed to check the
        # pattern - must NOT claim a match without evidence
        os_data = {"taxable": 76.61, "igst": 0.0, "cgst": 6.89, "sgst": 6.89,
                   "total": 90.40, "party_gstin": "27AAAAK0891Q2Z3", "doc_type": "Invoice"}
        client_data = {"taxable": 76.61, "igst": 13.79, "cgst": 0.0, "sgst": 0.0,
                        "total": 90.40, "doc_type": "Invoice"}
        entry = reconcile_document(os_data, client_data, "MH26061040", "Invoice")
        self.assertEqual(entry.status, ReconStatus.CLIENT_SHEET_ERROR)
        self.assertNotIn("known client-side pattern", entry.note)

    def test_tax_type_contradiction_that_is_not_an_inversion_does_not_claim_pattern_match(self):
        # client's flag actually agrees with their own Supplier
        # Location/State of Supply data (Intrastate, correctly) - so even
        # though OS and client still disagree with EACH OTHER on tax type,
        # this is NOT the known inversion bug and must not claim it is
        os_data = {"taxable": 76.61, "igst": 0.0, "cgst": 6.89, "sgst": 6.89,
                   "total": 90.40, "party_gstin": "27AAAAK0891Q2Z3", "doc_type": "Invoice"}
        client_data = {"taxable": 76.61, "igst": 13.79, "cgst": 0.0, "sgst": 0.0,
                        "total": 90.40, "doc_type": "Invoice",
                        "supplier_location": "MH", "state_of_supply": "29",
                        "interstate_or_intrastate": "Interstate"}
        entry = reconcile_document(os_data, client_data, "MH26061040", "Invoice")
        self.assertEqual(entry.status, ReconStatus.CLIENT_SHEET_ERROR)
        self.assertNotIn("known client-side pattern", entry.note)

    def test_muslim_coop_tax_type_contradiction_is_client_sheet_error(self):
        os_data = {"taxable": 1681071.22, "igst": 0.0, "cgst": 151296.41, "sgst": 151296.41,
                   "total": 1983664.0, "party_gstin": "27AAAAT0746P2Z2", "doc_type": "Invoice"}
        client_data = {"taxable": 1732015.45, "igst": 311762.78, "cgst": 0.0, "sgst": 0.0,
                        "total": 2043778.23, "doc_type": "Invoice"}
        entry = reconcile_document(os_data, client_data, "MH26061076", "Invoice")
        self.assertEqual(entry.status, ReconStatus.CLIENT_SHEET_ERROR)

    def test_cr26061011_same_tax_type_amount_mismatch_is_unresolved_not_guessed(self):
        # both sides say IGST (no contradiction) but the magnitude genuinely
        # differs - must NOT be auto-labeled CLIENT_SHEET_ERROR just because
        # it differs from our side
        os_data = {"taxable": 2500.0, "igst": 450.0, "cgst": 0.0, "sgst": 0.0,
                   "total": 2950.0, "party_gstin": "24AABFT9753E2Z3", "doc_type": "Credit Note"}
        client_data = {"taxable": 1000.0, "igst": 180.0, "cgst": 0.0, "sgst": 0.0,
                        "total": 1180.0, "doc_type": "Credit Note"}
        entry = reconcile_document(os_data, client_data, "CR26061011", "Credit Note")
        self.assertEqual(entry.status, ReconStatus.UNRESOLVED_CONFLICT)
        self.assertNotEqual(entry.status, ReconStatus.CLIENT_SHEET_ERROR)

    def test_bijnor_missing_from_os_before_source_pdf_was_found(self):
        client_data = {"taxable": 15984.0, "igst": 2877.12, "cgst": 0.0, "sgst": 0.0,
                        "total": 18861.12, "doc_type": "Invoice"}
        entry = reconcile_document(None, client_data, "OHR26061001", "Invoice")
        self.assertEqual(entry.status, ReconStatus.MISSING_SOURCE_PDF)

    def test_unava_present_in_os_absent_from_client_sheet(self):
        os_data = {"taxable": 235.51, "igst": 42.39, "cgst": 0.0, "sgst": 0.0,
                   "total": 277.90, "party_gstin": "09AAAAT0091R1ZW", "doc_type": "Invoice"}
        entry = reconcile_document(os_data, None, "MH26071001", "Invoice")
        self.assertEqual(entry.status, ReconStatus.CLIENT_MISSING)

    def test_pochampally_credit_note_no_gstin_is_unverifiable(self):
        os_data = {"taxable": 4884.84, "igst": 879.27, "cgst": 0.0, "sgst": 0.0,
                   "total": 5764.11, "party_gstin": None, "doc_type": "Credit Note"}
        client_data = {"taxable": 4884.84, "igst": 879.27, "cgst": 0.0, "sgst": 0.0,
                        "total": 5764.11, "doc_type": "Credit Note"}
        entry = reconcile_document(os_data, client_data, "CR26061004", "Credit Note")
        self.assertEqual(entry.status, ReconStatus.UNVERIFIABLE_NO_GSTIN)

    def test_clean_pass_within_tolerance(self):
        os_data = {"taxable": 30000.0, "igst": 5400.0, "cgst": 0.0, "sgst": 0.0,
                   "total": 35400.0, "party_gstin": "24AABFT9753E2Z3", "doc_type": "Invoice"}
        client_data = {"taxable": 30000.0, "igst": 5400.01, "cgst": 0.0, "sgst": 0.0,
                        "total": 35400.01, "doc_type": "Invoice"}
        entry = reconcile_document(os_data, client_data, "OMH26061003", "Invoice")
        self.assertEqual(entry.status, ReconStatus.PASS)

    def test_nil_invoice_both_sides_zero_tax_is_pass_not_contradiction(self):
        # NIL invoices (advance fully covered the period) have zero tax on
        # both sides - _tax_type returns None for both, must not be treated
        # as a contradiction
        os_data = {"taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0,
                   "total": 0.0, "party_gstin": "24AAAAT2886Q1ZU", "doc_type": "Invoice"}
        client_data = {"taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0,
                        "total": 0.0, "doc_type": "Invoice"}
        entry = reconcile_document(os_data, client_data, "MH26061036", "Invoice")
        self.assertEqual(entry.status, ReconStatus.PASS)

    def test_both_sides_none_raises(self):
        with self.assertRaises(ValueError):
            reconcile_document(None, None, "X", "Invoice")


class TestReconcilePeriod(unittest.TestCase):

    def test_reconciles_a_full_period_and_summarizes(self):
        os_rows = [
            {"doc_no": "MH26061040", "doc_type": "Invoice", "taxable": 76.61, "igst": 0.0,
             "cgst": 6.89, "sgst": 6.89, "total": 90.40, "party_gstin": "27AAAAK0891Q2Z3"},
            {"doc_no": "MH26071001", "doc_type": "Invoice", "taxable": 235.51, "igst": 42.39,
             "cgst": 0.0, "sgst": 0.0, "total": 277.90, "party_gstin": "09AAAAT0091R1ZW"},
        ]
        client_rows = [
            {"doc_no": "MH26061040", "doc_type": "Invoice", "taxable": 76.61, "igst": 13.79,
             "cgst": 0.0, "sgst": 0.0, "total": 90.40},
            {"doc_no": "OHR26061001", "doc_type": "Invoice", "taxable": 15984.0, "igst": 2877.12,
             "cgst": 0.0, "sgst": 0.0, "total": 18861.12},
        ]
        entries = reconcile_period(os_rows, client_rows)
        by_doc = {e.doc_no: e for e in entries}
        self.assertEqual(by_doc["MH26061040"].status, ReconStatus.CLIENT_SHEET_ERROR)
        self.assertEqual(by_doc["MH26071001"].status, ReconStatus.CLIENT_MISSING)
        self.assertEqual(by_doc["OHR26061001"].status, ReconStatus.MISSING_SOURCE_PDF)

        counts = summarize(entries)
        self.assertEqual(counts["CLIENT_SHEET_ERROR"], 1)
        self.assertEqual(counts["CLIENT_MISSING"], 1)
        self.assertEqual(counts["MISSING_SOURCE_PDF"], 1)


class TestNetTaxableTotal(unittest.TestCase):

    def test_credit_notes_subtract_not_add(self):
        rows = [
            {"doc_type": "Invoice", "taxable": 5000.0},
            {"doc_type": "Credit Note", "taxable": 1000.0},
        ]
        self.assertEqual(compute_net_taxable_total(rows), 4000.0)

    def test_debit_notes_also_subtract(self):
        rows = [
            {"doc_type": "Invoice", "taxable": 5000.0},
            {"doc_type": "Debit Note", "taxable": 200.0},
        ]
        self.assertEqual(compute_net_taxable_total(rows), 4800.0)

    def test_missing_doc_type_defaults_to_invoice(self):
        rows = [{"taxable": 100.0}]
        self.assertEqual(compute_net_taxable_total(rows), 100.0)


class TestReconcilePeriodTotals(unittest.TestCase):
    """
    The 3-way total-match check found against a real MH filing this
    session: a clean per-document PASS on every row doesn't guarantee the
    aggregate GSTR-1 total is right - a credit note miscategorized during
    filing generation (gstr1_generator.py's B2CS-default bug) produced a
    negative B2CS bucket even though every individual document reconciled
    fine. This is the check that catches that class of bug.
    """

    def test_matches_when_all_three_agree(self):
        os_rows = [{"doc_type": "Invoice", "taxable": 5000.0},
                   {"doc_type": "Credit Note", "taxable": 1000.0}]
        client_rows = [{"doc_type": "Invoice", "taxable": 5000.0},
                       {"doc_type": "Credit Note", "taxable": 1000.0}]
        result = reconcile_period_totals(os_rows, client_rows, {"total_taxable": 4000.0})
        self.assertTrue(result.matches)
        self.assertEqual(result.os_net_taxable, 4000.0)
        self.assertEqual(result.gstr1_net_taxable, 4000.0)

    def test_flags_mismatch_when_gstr1_total_wasnt_netted(self):
        # reproduces the real pre-fix bug: gstr1_generator summed the
        # credit note instead of subtracting it (6000 instead of 4000)
        os_rows = [{"doc_type": "Invoice", "taxable": 5000.0},
                   {"doc_type": "Credit Note", "taxable": 1000.0}]
        client_rows = [{"doc_type": "Invoice", "taxable": 5000.0},
                       {"doc_type": "Credit Note", "taxable": 1000.0}]
        result = reconcile_period_totals(os_rows, client_rows, {"total_taxable": 6000.0})
        self.assertFalse(result.matches)
        self.assertEqual(result.deltas["os_vs_gstr1"], -2000.0)
        self.assertIn("mismatch", result.note.lower())

    def test_flags_mismatch_between_os_and_client_even_without_gstr1(self):
        os_rows = [{"doc_type": "Invoice", "taxable": 5000.0}]
        client_rows = [{"doc_type": "Invoice", "taxable": 4800.0}]
        result = reconcile_period_totals(os_rows, client_rows, None)
        self.assertFalse(result.matches)
        self.assertIsNone(result.gstr1_net_taxable)
        self.assertEqual(result.deltas["os_vs_client"], 200.0)

    def test_within_tolerance_still_matches(self):
        os_rows = [{"doc_type": "Invoice", "taxable": 5000.0}]
        client_rows = [{"doc_type": "Invoice", "taxable": 5001.0}]
        result = reconcile_period_totals(os_rows, client_rows, {"total_taxable": 5000.5})
        self.assertTrue(result.matches)


if __name__ == "__main__":
    unittest.main()
