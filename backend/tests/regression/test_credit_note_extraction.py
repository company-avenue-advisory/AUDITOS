"""
Regression tests for invoice_processor.extract_credit_note /
resolve_credit_note_gstin - the deterministic (regex, no LLM) OneStack
credit-note extractor.

Fixtures are real credit note text pulled from OneStack's Drive folder
this session (14 real credit notes processed and reconciled by hand
before this extractor existed):

  - CR26061013 (Ashok): multi-word single-line "Bill To" block with no
    line break before "Original Invoice Number" - the party_name leakage
    bug fixed this session.
  - CR26061011 (Becharaji): clean multi-line layout, one HSN (9971) in
    the particulars table - confirmed against source PDF to match our
    OS Register exactly (the client's sheet had this one wrong).
  - CR26061004 (Pochampally): no per-line HSN at all on this credit note
    (just "0" placeholder tokens) - must fall back to NOT_SPECIFIED_HSN,
    not guess.
  - CR26061002 (Mizoram): filename said "PI26061002" but the document
    itself says "Credit Note Number: CR26061002" - proves the extractor
    reads the document content, not any filename convention.

All expected figures (taxable/tax/total) are the ones already verified
against the real source PDFs and filed in GSTR1_MH_June2026_OneStack.xlsx
this session.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.invoice_processor import extract_credit_note, resolve_credit_note_gstin, NOT_SPECIFIED_HSN


class TestCreditNoteExtraction(unittest.TestCase):

    def test_not_a_credit_note_returns_none(self):
        self.assertIsNone(extract_credit_note("Tax Invoice One Stack Solution Private Limited ..."))

    def test_ashok_single_line_bill_to_no_leakage(self):
        text = """Credit Note Credit Note Number : CR26061013 Date: 26-06-2026

Bill To:

Ashok Sahakari Bank Ltd Ahmednagar AHMEDNAGAR, CHAHATRAPATI SHIVAJI SANKUL, KOTHI ROAD, MARKET YARD, AHMDNAGAR 414001 Original Invoice Number : MH26041028 Original Invoice Date: 30-04-2026

Reason for Credit Note: Charges Reversed

Particulars HSN Code/SAC Number Month INR chargs

Total A Application Charges 9971 1,000 - 5.00

2,500.00

Subtotal: 2,500.00 CGST @9% - SGST @9% - IGST @18% 450.00 Rounding off : - Total Amount Credited: Amount In words:

2,950.00 Indian Rupees - Two Thousand Nine Hundred Fifty"""
        r = extract_credit_note(text)
        self.assertEqual(r["credit_note_no"], "CR26061013")
        self.assertEqual(r["date"], "26-06-2026")
        self.assertEqual(r["original_invoice_no"], "MH26041028")
        self.assertEqual(r["original_invoice_date"], "30-04-2026")
        self.assertEqual(r["reason"], "Charges Reversed")
        self.assertEqual(r["taxable"], 2500.00)
        self.assertEqual(r["igst_rate"], 18.0)
        self.assertEqual(r["igst"], 450.00)
        self.assertEqual(r["cgst"], 0.0)
        self.assertEqual(r["sgst"], 0.0)
        self.assertEqual(r["total"], 2950.00)
        self.assertEqual(r["hsn"], "9971")
        # the party_name leakage bug: must not include the next label's text
        self.assertNotIn("Original Invoice Number", r["party_name"])
        self.assertTrue(r["party_name"].startswith("Ashok Sahakari Bank Ltd Ahmednagar"))

    def test_becharaji_clean_multiline_layout(self):
        text = """Credit Note Number :
CR26061011
Date:
26-06-2026
Bill To:
The Becharaji Nagarik Sahakari Bank Ltd
Original Invoice Number :
MH26041088
Original Invoice Date:
30-04-2026
Reason for Credit Note:
Charges Reversed
HSN Code/SAC
Number
Month
INR chargs
9971
1,000
-
5.00
Subtotal:
2,500.00
CGST @9%
-
SGST @9%
-
IGST @18%
450.00
Rounding off :
-
Total Amount Credited:
Amount In words:
2,950.00
Indian Rupees - Two Thousand Nine Hundred Fifty"""
        r = extract_credit_note(text)
        self.assertEqual(r["credit_note_no"], "CR26061011")
        self.assertEqual(r["party_name"], "The Becharaji Nagarik Sahakari Bank Ltd")
        self.assertEqual(r["original_invoice_no"], "MH26041088")
        self.assertEqual(r["taxable"], 2500.00)
        self.assertEqual(r["igst"], 450.00)
        self.assertEqual(r["total"], 2950.00)
        self.assertEqual(r["hsn"], "9971")

    def test_pochampally_no_line_item_hsn_falls_back_to_not_specified(self):
        text = """Credit Note Number :
CR26061004
Date:
11-06-2026
Bill To:
Pochampally CoOperative Urban Bank Ltd
Original Invoice Number :
MH26041062
Original Invoice Date:
30-04-2026
Reason for Credit Note:
Soundbox Returned
HSN Code/SAC
Number
Month
INR chargs
0
-
-
-
Subtotal:
4,884.84
CGST @9%
-
SGST @9%
-
IGST @18%
879.27
Rounding off :
-
Total Amount Credited:
Amount In words:
Particulars
Total
5,764.11
Indian Rupees - Five Thousand Seven Hundred Eighty Seven"""
        r = extract_credit_note(text)
        self.assertEqual(r["taxable"], 4884.84)
        self.assertEqual(r["igst"], 879.27)
        self.assertEqual(r["total"], 5764.11)
        self.assertEqual(r["hsn"], NOT_SPECIFIED_HSN)

    def test_mizoram_reads_document_content_not_pi_filename(self):
        # filename on disk was "MIZORAM..._PI26061002.pdf" - the document
        # itself says CR26061002. Extractor must read the document, not
        # be given or trust any filename.
        text = """Credit Note Credit Note Number : CR26061002 Date: 11-06-2026

Bill To:

MIZORAM URBAN COOPERATIVE DEVELOPMENT BANK LTD LALSAWMLIANI BUILDING A-14 TOP FLOOR ZARKAWT MAIN STREET 796001 Mizoram Original Invoice Number : MH26051049 Original Invoice Date: 31-05-2026

Reason for Credit Note: Soundbox Returned

Particulars HSN Code/SAC Number Month INR chargs

Total A Soundbox Charges

997319 50 999 49,950.00

Subtotal: 49,950.00 CGST @9% - SGST @9% - IGST @18% 8,991.00 Rounding off : - Total Amount Credited:

58,941.00 Amount In words:

Indian Rupees - Fifty Eight Thousand Nine Hundred Forty One"""
        r = extract_credit_note(text)
        self.assertEqual(r["credit_note_no"], "CR26061002")
        self.assertEqual(r["hsn"], "997319")
        self.assertEqual(r["taxable"], 49950.00)
        self.assertEqual(r["igst"], 8991.00)
        self.assertEqual(r["total"], 58941.00)


class TestResolveCreditNoteGstin(unittest.TestCase):

    def test_resolves_via_lookup_fn(self):
        db = {"MH26041088": "24AABFT9753E2Z3"}
        gstin = resolve_credit_note_gstin("MH26041088", lambda inv: db.get(inv))
        self.assertEqual(gstin, "24AABFT9753E2Z3")

    def test_returns_none_not_a_guess_when_original_invoice_unknown(self):
        # Pochampally's real-world case: the original invoice (a March/April
        # invoice) was never in this tool's own records
        gstin = resolve_credit_note_gstin("MH26031999", lambda inv: None)
        self.assertIsNone(gstin)

    def test_returns_none_when_no_original_invoice_no_at_all(self):
        gstin = resolve_credit_note_gstin(None, lambda inv: "should-not-be-called")
        self.assertIsNone(gstin)


if __name__ == "__main__":
    unittest.main()
