"""
Regression tests for services.client_sheet_parser.parse_client_sheet.

Builds a small synthetic .xlsx fixture in-memory (via openpyxl) that
mirrors the REAL structure confirmed against OneStack's actual
Sales_PQB_June 2026_Vandana.xlsx this session - not the real file itself,
since client data must never be committed to this repo (matches the
existing backend/data/ gitignore convention for vendor_profiles etc).

Locks in:
  - Row 1 (type annotations like "Input"/"Formula based") is correctly
    skipped, row 2 is the real header, data starts row 3.
  - Both invoices AND credit notes are read from the ONE masterdata sheet,
    split by "Document Type Code" - not from a separately-named credit-note
    tab (confirmed this session that such a tab can be a stale prior-period
    batch, unrelated to the current month).
  - Numbered duplicate IGST/SGST/CGST columns further right in the real
    sheet (IGST3, IGST9, IGST13, IGST17 etc - a formula cross-check
    section) must NOT be picked up instead of the real IGST/SGST/CGST
    columns - only an exact header match should bind.
  - Real known-good rows: Krushiseva (client sheet says "Interstate"/IGST
    here, though the actual PDF confirms intrastate CGST+SGST - this
    parser must report what the client's sheet says, not correct it) and
    Pandharpur's credit note (intrastate CGST+SGST, matches source PDF).
"""
import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.client_sheet_parser import parse_client_sheet


def _build_fixture_workbook(path):
    import openpyxl
    from datetime import datetime

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales_masterdata(Input)"

    type_row = ["Input"] * 14 + ["Formula based"] * 2
    ws.append(type_row)

    headers = [
        "S.no", "Document Type Code( Invoice/Credit note /Debit note)", "Document  no",
        "Document  Date", "Recipient Billing Name", "Recipient Billing GSTIN",
        "B2B or B2C", "State  of Supply  \n(Code _Two Digit )",
        "Interstate or Intrastate \n(Drop Down only)",
        "Net Basic Amt", "IGST", "SGST", "CGST", "Invoice Value",
        "IGST3", "IGST9",  # the numbered duplicate columns that must NOT be matched
    ]
    ws.append(headers)

    # Krushiseva - client sheet (wrongly) says Interstate/IGST here
    ws.append([
        49, "Invoice", "MH26061040", datetime(2026, 6, 30),
        "Krushiseva Urban Coop Bank Ltd.", "27AAAAK0891Q2Z3", "B2B", "27",
        "Interstate", 76.61, 13.79, 0.0, 0.0, 90.40,
        999.0, 999.0,  # decoy values in the numbered duplicate columns
    ])

    # Pandharpur credit note - intrastate CGST+SGST, matches source PDF
    ws.append([
        181, "Credit Note", "CR26061001", datetime(2026, 6, 30),
        "The Pandharpur Merchant CoOp Bank Ltd", "27AAAAT3361L1ZA", "B2B", "27",
        "Intrastate", 47952.0, 0.0, 4315.68, 4315.68, 56583.36,
        999.0, 999.0,
    ])

    # a stray blank row (client sheets often have these) - must be skipped
    ws.append([None] * len(headers))

    wb.save(path)


class TestClientSheetParser(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="client_sheet_test_")
        self.xlsx_path = os.path.join(self.tmp_dir, "Sales_PQB_test.xlsx")
        _build_fixture_workbook(self.xlsx_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_finds_masterdata_sheet_and_skips_type_row(self):
        rows = parse_client_sheet(self.xlsx_path)
        self.assertEqual(len(rows), 2)  # blank row must be skipped

    def test_splits_invoices_and_credit_notes_from_one_sheet(self):
        rows = parse_client_sheet(self.xlsx_path)
        invoices = [r for r in rows if r["doc_type"] == "Invoice"]
        credit_notes = [r for r in rows if r["doc_type"] == "Credit Note"]
        self.assertEqual(len(invoices), 1)
        self.assertEqual(len(credit_notes), 1)

    def test_numbered_duplicate_columns_not_picked_up(self):
        # IGST3/IGST9 (decoy value 999.0) must never leak into "igst"
        rows = parse_client_sheet(self.xlsx_path)
        krushiseva = [r for r in rows if r["doc_no"] == "MH26061040"][0]
        self.assertEqual(krushiseva["igst"], 13.79)
        self.assertNotEqual(krushiseva["igst"], 999.0)

    def test_reports_client_data_as_is_does_not_correct_it(self):
        # the client sheet says Interstate/IGST for Krushiseva - this
        # parser must report that verbatim, even though the real source
        # PDF confirms it's actually intrastate CGST+SGST. Correcting it
        # is the reconciliation engine's job, not this parser's.
        rows = parse_client_sheet(self.xlsx_path)
        krushiseva = [r for r in rows if r["doc_no"] == "MH26061040"][0]
        self.assertEqual(krushiseva["interstate_or_intrastate"], "Interstate")
        self.assertEqual(krushiseva["igst"], 13.79)
        self.assertEqual(krushiseva["cgst"], 0.0)

    def test_pandharpur_credit_note_fields(self):
        rows = parse_client_sheet(self.xlsx_path)
        cn = [r for r in rows if r["doc_no"] == "CR26061001"][0]
        self.assertEqual(cn["party_gstin"], "27AAAAT3361L1ZA")
        self.assertEqual(cn["taxable"], 47952.0)
        self.assertEqual(cn["cgst"], 4315.68)
        self.assertEqual(cn["sgst"], 4315.68)
        self.assertEqual(cn["total"], 56583.36)

    def test_missing_masterdata_sheet_raises_not_silently_empty(self):
        import openpyxl
        path = os.path.join(self.tmp_dir, "no_masterdata.xlsx")
        wb = openpyxl.Workbook()
        wb.active.title = "SomeOtherSheet"
        wb.save(path)
        with self.assertRaises(ValueError):
            parse_client_sheet(path)


if __name__ == "__main__":
    unittest.main()
