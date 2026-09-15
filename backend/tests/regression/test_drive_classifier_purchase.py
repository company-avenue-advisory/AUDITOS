"""
Regression tests for the Purchase-mode Drive classification added this
session (services/drive_classifier.py's classify_purchase_file,
walk_and_classify_purchase, classify_local_directory_purchase).

Fixture tree below reproduces OneStack's REAL Purchase Drive folder
(purchase_root_folder_id -> "3. June 2026", fetched and confirmed via
Drive MCP search 2026-07-08) - not a synthetic guess:
  - 4 loose PDFs at the month-folder root (one of which, "Yes Bank
    Invoice.pdf", is actually a bank one-touch certificate, not a real
    tax invoice - confirmed by its content snippet; the classifier can't
    and shouldn't try to filter that out by filename, only the extractor
    reading the actual document can)
  - 6 vendor expense-category subfolders (HR, Telecom, Shipping,
    Professional Fees, Data & Network, Rental) - these are the vendor's
    OWN organizational labels, never a document-type signal the way
    Sales' "Credit Note"/"Sales Invoice" folders are
  - "Professional Fees" contains 3 PDFs and one real zip
    ("Authbridge.zip") - confirming archives genuinely appear in this
    tree and must be handled, not just theorized about

Locks in the exact bug this was built to fix: passing this same tree
through the SALES walker (walk_and_classify) would classify every file
inside a category subfolder as UNKNOWN (since none of "HR"/"Telecom"/
etc. match Sales' _INVOICE_FOLDER_NAMES) - meaning the vast majority of
real Purchase invoices would have been silently dropped, never reaching
extraction. walk_and_classify_purchase fixes this by classifying every
file by extension alone, regardless of which folder it's nested in.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.services.drive_classifier import (
    walk_and_classify, walk_and_classify_purchase, classify_purchase_file, DocumentType,
    FOLDER_MIME,
)

PDF_MIME = "application/pdf"
ZIP_MIME = "application/zip"

# id -> (name, mimeType, parent_id)
_TREE = {
    "root": None,  # not a real node, just the starting point
    "f_cdsl":       ("CDSL Invoice 028179_AIBILL_2026.pdf", PDF_MIME, "root"),
    "f_yesbank_ot": ("YEsbank Onetouch ONE STACK SOLUTION PVT LTD -12062026.pdf", PDF_MIME, "root"),
    "d_hr":         ("HR", FOLDER_MIME, "root"),
    "f_naukri":     ("Naukri NK09I0627004154.pdf", PDF_MIME, "root"),
    "d_telecom":    ("Telecom", FOLDER_MIME, "root"),
    "d_shipping":   ("Shipping", FOLDER_MIME, "root"),
    "d_profees":    ("Professional Fees", FOLDER_MIME, "root"),
    "f_yesbank":    ("Yes Bank Invoice.pdf", PDF_MIME, "root"),  # a bank certificate, not a real invoice
    "d_datanet":    ("Data & Network", FOLDER_MIME, "root"),
    "d_rental":     ("Rental", FOLDER_MIME, "root"),

    "f_pf_invoice": ("Invoice1261005553 One Stack  Solution Private Limited (TRU-206).pdf", PDF_MIME, "d_profees"),
    "f_pf_zip":     ("Authbridge.zip", ZIP_MIME, "d_profees"),
    "f_pf_nilesh":  ("Nilesh Shah One Stack_02-SC-26-27.pdf", PDF_MIME, "d_profees"),
    "f_pf_system":  ("219_System Support.pdf", PDF_MIME, "d_profees"),
}


def _make_lister():
    def lister(folder_id):
        children = []
        for file_id, entry in _TREE.items():
            if entry is None:
                continue
            name, mime, parent = entry
            if parent == folder_id:
                children.append({"id": file_id, "name": name, "mimeType": mime})
        return children
    return lister


class TestClassifyPurchaseFile(unittest.TestCase):

    def test_pdf_is_invoice(self):
        self.assertEqual(classify_purchase_file("anything.pdf", PDF_MIME), DocumentType.INVOICE)

    def test_zip_is_archive(self):
        self.assertEqual(classify_purchase_file("Authbridge.zip", ZIP_MIME), DocumentType.ARCHIVE)

    def test_folder_is_unknown(self):
        self.assertEqual(classify_purchase_file("HR", FOLDER_MIME), DocumentType.UNKNOWN)

    def test_unrecognized_extension_is_unknown(self):
        self.assertEqual(classify_purchase_file("notes.txt", "text/plain"), DocumentType.UNKNOWN)


class TestWalkAndClassifyPurchaseOnRealTree(unittest.TestCase):

    def setUp(self):
        self.files = walk_and_classify_purchase(_make_lister(), "root")

    def test_every_pdf_classified_as_invoice_regardless_of_nesting(self):
        # 4 loose at root + 4 nested inside "Professional Fees" = 7 PDFs total
        invoices = [f for f in self.files if f.document_type == DocumentType.INVOICE]
        self.assertEqual(len(invoices), 7)

    def test_zip_classified_as_archive_not_dropped(self):
        archives = [f for f in self.files if f.document_type == DocumentType.ARCHIVE]
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].name, "Authbridge.zip")

    def test_no_file_silently_marked_unknown(self):
        # every real file in this tree is either a genuine PDF or the one
        # zip - nothing should fall through to UNKNOWN
        unknown = [f for f in self.files if f.document_type == DocumentType.UNKNOWN]
        self.assertEqual(unknown, [])

    def test_category_folder_name_is_preserved_as_path_not_used_for_typing(self):
        nested = next(f for f in self.files if f.name == "219_System Support.pdf")
        self.assertEqual(nested.path, ["Professional Fees"])
        self.assertEqual(nested.document_type, DocumentType.INVOICE)

    def test_a_non_invoice_pdf_still_gets_classified_as_invoice_candidate(self):
        # the classifier can't tell "Yes Bank Invoice.pdf" is actually a
        # bank certificate without reading it - that's the extractor's
        # job (recognize + skip/flag), not the classifier's
        bank_cert = next(f for f in self.files if f.name == "Yes Bank Invoice.pdf")
        self.assertEqual(bank_cert.document_type, DocumentType.INVOICE)


class TestSalesWalkerWouldHaveDroppedMostOfThisTree(unittest.TestCase):
    """
    Proves the actual bug being fixed: running the SAME real Purchase
    tree through the Sales-only walker (the only one that existed before
    this change) silently drops everything inside a category subfolder.
    """

    def test_sales_walker_marks_category_subfolder_contents_unknown(self):
        files = walk_and_classify(_make_lister(), "root")
        professional_fees_files = [f for f in files if "Professional Fees" in f.path]
        self.assertTrue(all(f.document_type == DocumentType.UNKNOWN for f in professional_fees_files))
        self.assertEqual(len(professional_fees_files), 4)

    def test_sales_walker_still_correctly_classifies_root_pdfs(self):
        # loose root PDFs happen to still classify fine under Sales' own
        # root-file rule (any .pdf -> INVOICE) - it's specifically the
        # nested, category-foldered majority that the Sales walker loses.
        files = walk_and_classify(_make_lister(), "root")
        root_pdfs = [f for f in files if not f.path and f.name.endswith(".pdf")]
        self.assertTrue(all(f.document_type == DocumentType.INVOICE for f in root_pdfs))
        self.assertEqual(len(root_pdfs), 4)


if __name__ == "__main__":
    unittest.main()
