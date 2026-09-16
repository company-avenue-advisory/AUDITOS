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
  - Real known-good rows: Meridian (client sheet says "Interstate"/IGST
    here, though the actual PDF confirms intrastate CGST+SGST - this
    parser must report what the client's sheet says, not correct it) and
    Fairview's credit note (intrastate CGST+SGST, matches source PDF).
"""
import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.client_sheet_parser import parse_client_sheet, sections_to_line_items, NOT_SPECIFIED_HSN


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

    # Meridian - client sheet (wrongly) says Interstate/IGST here
    ws.append([
        49, "Invoice", "MH26061040", datetime(2026, 6, 30),
        "Meridian Urban Coop Bank Ltd.", "27CCCCC3333C3Z3", "B2B", "27",
        "Interstate", 76.61, 13.79, 0.0, 0.0, 90.40,
        999.0, 999.0,  # decoy values in the numbered duplicate columns
    ])

    # Fairview credit note - intrastate CGST+SGST, matches source PDF
    ws.append([
        181, "Credit Note", "CR26061001", datetime(2026, 6, 30),
        "The Fairview Merchant CoOp Bank Ltd", "27DDDDD4444D4Z4", "B2B", "27",
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
        # the client sheet says Interstate/IGST for Meridian - this
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
        self.assertEqual(cn["party_gstin"], "27DDDDD4444D4Z4")
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


class TestSectionsToLineItems(unittest.TestCase):
    """
    sections_to_line_items powers sheet-first ingestion (see
    services/sheet_first_ingestion.py): expanding one client-sheet row
    into per-bucket line items trusting the sheet's own HSN/amounts.
    """

    def _invoice_row(self, **overrides):
        row = {
            "doc_type": "Invoice", "doc_no": "MH1",
            "taxable": 3000.0, "cgst": 270.0, "sgst": 270.0, "igst": 0.0, "total": 3540.0,
            "sections": {
                "saas_net": 2000.0, "soundbox_net": 1000.0,
                "transactional_net": 0.0, "kyc_net": 0.0,
                "promotional_net": 0.0, "late_charges": 0.0,
            },
        }
        row.update(overrides)
        return row

    def test_credit_note_row_returns_none_sheet_not_trusted(self):
        row = self._invoice_row(doc_type="Credit Note")
        self.assertIsNone(sections_to_line_items(row))

    def test_debit_note_row_returns_none_sheet_not_trusted(self):
        row = self._invoice_row(doc_type="Debit Note")
        self.assertIsNone(sections_to_line_items(row))

    def test_invoice_with_all_zero_sections_returns_empty_list(self):
        row = self._invoice_row(sections={k: 0.0 for k in self._invoice_row()["sections"]})
        self.assertEqual(sections_to_line_items(row), [])

    def test_expands_nonzero_buckets_with_correct_hsn(self):
        items = sections_to_line_items(self._invoice_row())
        self.assertEqual(len(items), 2)
        hsns = {i["hsn"] for i in items}
        self.assertEqual(hsns, {"9971", "997319"})

    def test_tax_apportioned_by_bucket_share_and_sums_to_total(self):
        items = sections_to_line_items(self._invoice_row())
        saas = next(i for i in items if i["hsn"] == "9971")
        soundbox = next(i for i in items if i["hsn"] == "997319")
        # 2000/3000 share of 270 cgst = 180.0, 1000/3000 share = 90.0
        self.assertEqual(saas["cgst"], 180.0)
        self.assertEqual(soundbox["cgst"], 90.0)
        self.assertEqual(round(sum(i["taxable"] for i in items), 2), 3000.0)
        self.assertEqual(round(sum(i["total"] for i in items), 2), 3540.0)

    def test_bucket_with_no_known_hsn_gets_not_specified(self):
        row = self._invoice_row(sections={
            "saas_net": 0.0, "soundbox_net": 0.0, "transactional_net": 0.0,
            "kyc_net": 0.0, "promotional_net": 0.0, "late_charges": 500.0,
        }, taxable=500.0, cgst=45.0, sgst=45.0, total=590.0)
        items = sections_to_line_items(row)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hsn"], NOT_SPECIFIED_HSN)


if __name__ == "__main__":
    unittest.main()
