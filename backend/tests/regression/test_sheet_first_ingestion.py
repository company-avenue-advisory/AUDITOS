"""
Regression tests for services.sheet_first_ingestion - the sheet-first
reconciliation mode: the client's own sheet is ground truth for HSN/
amounts, PDFs are only pulled in for genuine gaps (a Drive PDF with no
matching sheet row) or for Credit/Debit Note rows (the sheet's own bucket
formulas don't compute for those - see client_sheet_parser.py).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.drive_classifier import ClassifiedFile, DocumentType
from backend.services.sheet_first_ingestion import (
    doc_no_from_pdf_text, find_gap_files, find_credit_note_pdf_for_row,
    build_line_items_from_sheet_row, build_line_items_for_credit_note_pdf,
    plan_sheet_first_ingestion,
)

_INVOICE_TEXT = """Customer Name: Acme Bank Billing Month: June 2026
GSTIN: 27AAAAA1111A1Z1 Invoice Number: MH26061099 PAN: AAAAA1111A
Date of Invoice: 30-06-2026"""

_CN_TEXT = """Credit Note Credit Note Number : CR26061099 Date: 26-06-2026

Bill To:

Some Bank Ltd Original Invoice Number : MH26051099 Original Invoice Date: 31-05-2026

Reason for Credit Note: Charges Reversed

Particulars HSN Code/SAC Number Month INR chargs

Total A Soundbox Charges

997319 1 999 1,000.00

Subtotal: 1,000.00 CGST @9% - SGST @9% - IGST @18% 180.00 Rounding off : - Total Amount Credited:

1,180.00 Amount In words:

Indian Rupees - One Thousand One Hundred Eighty"""


def _file(name, doc_type, id_="f1"):
    return ClassifiedFile(id=id_, name=name, mime_type="application/pdf", document_type=doc_type)


class TestDocNoFromPdfText(unittest.TestCase):
    def test_reads_invoice_number(self):
        self.assertEqual(doc_no_from_pdf_text(_INVOICE_TEXT), "MH26061099")

    def test_reads_credit_note_number(self):
        self.assertEqual(doc_no_from_pdf_text(_CN_TEXT), "CR26061099")

    def test_returns_none_for_unrecognized_text(self):
        self.assertIsNone(doc_no_from_pdf_text("Some unrelated document text"))


class TestFindGapFiles(unittest.TestCase):
    def test_pdf_matching_a_sheet_row_is_not_a_gap(self):
        files = [_file("a.pdf", DocumentType.INVOICE)]
        gaps = find_gap_files(files, {"MH26061099"}, lambda f: _INVOICE_TEXT)
        self.assertEqual(gaps, [])

    def test_pdf_with_no_matching_sheet_row_is_a_gap(self):
        files = [_file("a.pdf", DocumentType.INVOICE)]
        gaps = find_gap_files(files, {"MH99999999"}, lambda f: _INVOICE_TEXT)
        self.assertEqual(len(gaps), 1)

    def test_unreadable_pdf_is_a_gap_not_silently_skipped(self):
        files = [_file("a.pdf", DocumentType.INVOICE)]
        gaps = find_gap_files(files, {"MH26061099"}, lambda f: None)
        self.assertEqual(len(gaps), 1)

    def test_non_invoice_non_credit_note_files_ignored(self):
        files = [_file("sheet.xlsx", DocumentType.CLIENT_SHEET)]
        gaps = find_gap_files(files, set(), lambda f: None)
        self.assertEqual(gaps, [])


class TestFindCreditNotePdfForRow(unittest.TestCase):
    def test_finds_matching_credit_note_pdf(self):
        files = [_file("cn.pdf", DocumentType.CREDIT_NOTE)]
        row = {"doc_no": "CR26061099"}
        found = find_credit_note_pdf_for_row(row, files, lambda f: _CN_TEXT)
        self.assertIsNotNone(found)

    def test_returns_none_when_no_match(self):
        files = [_file("cn.pdf", DocumentType.CREDIT_NOTE)]
        row = {"doc_no": "CR_NOT_FOUND"}
        found = find_credit_note_pdf_for_row(row, files, lambda f: _CN_TEXT)
        self.assertIsNone(found)

    def test_returns_none_when_row_has_no_doc_no(self):
        files = [_file("cn.pdf", DocumentType.CREDIT_NOTE)]
        self.assertIsNone(find_credit_note_pdf_for_row({}, files, lambda f: _CN_TEXT))


class TestBuildLineItemsFromSheetRow(unittest.TestCase):
    def test_uses_sheet_bucket_breakdown_for_invoice(self):
        row = {
            "doc_type": "Invoice", "doc_no": "MH1", "party_gstin": "27X", "party_name": "Acme",
            "doc_date": "30-06-2026", "state_of_supply": "27",
            "taxable": 2000.0, "cgst": 180.0, "sgst": 180.0, "igst": 0.0, "total": 2360.0,
            "sections": {"saas_net": 2000.0, "soundbox_net": 0.0, "transactional_net": 0.0,
                         "kyc_net": 0.0, "promotional_net": 0.0, "late_charges": 0.0},
        }
        items = build_line_items_from_sheet_row(row)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hsn"], "9971")
        self.assertEqual(items[0]["invoice_no"], "MH1")

    def test_falls_back_to_single_line_for_credit_note(self):
        row = {
            "doc_type": "Credit Note", "doc_no": "CR1", "party_gstin": "27X",
            "taxable": 1000.0, "cgst": 90.0, "sgst": 90.0, "igst": 0.0, "total": 1180.0,
        }
        items = build_line_items_from_sheet_row(row)
        self.assertEqual(len(items), 1)
        from backend.services.client_sheet_parser import NOT_SPECIFIED_HSN
        self.assertEqual(items[0]["hsn"], NOT_SPECIFIED_HSN)
        self.assertEqual(items[0]["taxable_value"], 1000.0)


class TestBuildLineItemsForCreditNotePdf(unittest.TestCase):
    def test_reads_hsn_from_pdf_not_sheet(self):
        row = {"doc_type": "Credit Note", "party_gstin": "27X", "state_of_supply": "27"}
        items = build_line_items_for_credit_note_pdf(row, _CN_TEXT)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hsn"], "997319")
        self.assertEqual(items[0]["invoice_no"], "CR26061099")

    def test_returns_none_for_non_credit_note_text(self):
        row = {"doc_type": "Credit Note"}
        self.assertIsNone(build_line_items_for_credit_note_pdf(row, "not a credit note"))


class TestPlanSheetFirstIngestion(unittest.TestCase):
    def test_full_plan_invoice_row_gap_file_and_cn_row(self):
        client_rows = [
            {
                "doc_type": "Invoice", "doc_no": "MH26061099", "party_gstin": "27X",
                "taxable": 2000.0, "cgst": 180.0, "sgst": 180.0, "igst": 0.0, "total": 2360.0,
                "sections": {"saas_net": 2000.0, "soundbox_net": 0.0, "transactional_net": 0.0,
                             "kyc_net": 0.0, "promotional_net": 0.0, "late_charges": 0.0},
            },
            {
                "doc_type": "Credit Note", "doc_no": "CR26061099", "party_gstin": "27X",
                "taxable": 1000.0, "cgst": 90.0, "sgst": 90.0, "igst": 0.0, "total": 1180.0,
            },
        ]
        files = [
            _file("invoice.pdf", DocumentType.INVOICE, "f1"),
            _file("cn.pdf", DocumentType.CREDIT_NOTE, "f2"),
            _file("gap.pdf", DocumentType.INVOICE, "f3"),
        ]

        def text_reader(f):
            return {"f1": _INVOICE_TEXT, "f2": _CN_TEXT, "f3": "some other invoice, no header match"}[f.id]

        plan = plan_sheet_first_ingestion(client_rows, files, text_reader)

        self.assertEqual(len(plan["gap_files"]), 1)
        self.assertEqual(plan["gap_files"][0].id, "f3")

        by_doc = {g["source_doc_no"]: g["items"] for g in plan["line_items"]}
        self.assertEqual(by_doc["MH26061099"][0]["hsn"], "9971")
        # CN row: its matching PDF was found, so HSN comes from the PDF (997319),
        # not the sheet's own (untrusted) bucket columns.
        self.assertEqual(by_doc["CR26061099"][0]["hsn"], "997319")


if __name__ == "__main__":
    unittest.main()
