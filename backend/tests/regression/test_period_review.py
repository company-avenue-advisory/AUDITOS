"""
Regression tests for services.period_review - the human review gate
between reconciliation/filing generation and anything reaching a GST
portal. Uses a real in-memory SQLite DB (not mocked) to prove the state
machine and persistence actually work, matching the pattern already
used for credit_note_ingest.py's wiring tests this session.
"""
import sys
import os
import tempfile
import shutil
import unittest

# models.py (bare "from database import Base") and period_review.py
# (bare "from models import ...") both need backend/ itself on sys.path -
# imported consistently via the bare convention below (not "backend.X")
# so models.py is never loaded twice under two different module names,
# which would otherwise redefine the same SQLAlchemy tables and crash.
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../backend"))
sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Tenant, User, SalesLineItem, InvoiceTask, BatchJob, TaskStatus, SalesPeriodReview
from services.period_review import (
    build_recon_summary, build_filings_summary, create_period_review,
    approve_period_review, reject_period_review, get_review_detail, ReviewStateError,
    generate_period_review_for_tenant, month_matches_period, get_latest_review,
)
from services.sales_reconciliation import ReconEntry, ReconStatus, reconcile_period_totals


def _entry(doc_no, status, note=""):
    return ReconEntry(doc_no=doc_no, doc_type="Invoice", status=status, note=note)


class TestBuildSummaries(unittest.TestCase):

    def test_recon_summary_counts_and_flags_non_pass(self):
        entries = [
            _entry("MH1", ReconStatus.PASS),
            _entry("MH2", ReconStatus.PASS),
            _entry("MH3", ReconStatus.CLIENT_SHEET_ERROR, "tax-type contradiction"),
            _entry("CR1", ReconStatus.UNRESOLVED_CONFLICT, "amounts differ"),
        ]
        summary = build_recon_summary(entries)
        self.assertEqual(summary["counts"]["PASS"], 2)
        self.assertEqual(summary["counts"]["CLIENT_SHEET_ERROR"], 1)
        self.assertEqual(len(summary["needs_attention"]), 2)
        self.assertNotIn("MH1", [n["doc_no"] for n in summary["needs_attention"]])

    def test_recon_summary_includes_totals_match_when_given(self):
        entries = [_entry("MH1", ReconStatus.PASS)]
        os_rows = [{"doc_type": "Invoice", "taxable": 5000.0}, {"doc_type": "Credit Note", "taxable": 1000.0}]
        client_rows = [{"doc_type": "Invoice", "taxable": 5000.0}, {"doc_type": "Credit Note", "taxable": 1000.0}]
        totals_match = reconcile_period_totals(os_rows, client_rows, {"total_taxable": 6000.0})

        summary = build_recon_summary(entries, totals_match)
        self.assertIn("totals_match", summary)
        self.assertFalse(summary["totals_match"]["matches"])
        self.assertEqual(summary["totals_match"]["os_net_taxable"], 4000.0)
        self.assertEqual(summary["totals_match"]["gstr1_net_taxable"], 6000.0)

    def test_recon_summary_omits_totals_match_when_not_given(self):
        summary = build_recon_summary([_entry("MH1", ReconStatus.PASS)])
        self.assertNotIn("totals_match", summary)

    def test_filings_summary_shape(self):
        filings = {
            "27AADCO0061H1ZQ": {
                "gstr1_json": {
                    "_summary": {"total_taxable": 100.0, "total_tax": 18.0,
                                 "total_invoices": 1, "sections_with_data": ["b2b"]},
                },
                "flagged_unresolved": ["MH1"],
                "skipped": [],
            },
        }
        summary = build_filings_summary(filings)
        self.assertTrue(summary["27AADCO0061H1ZQ"]["has_data"])
        self.assertEqual(summary["27AADCO0061H1ZQ"]["total_taxable"], 100.0)
        self.assertEqual(summary["27AADCO0061H1ZQ"]["flagged_unresolved"], ["MH1"])


class TestPeriodReviewLifecycle(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id="t1", name="OneStack", slug="onestack"))
        self.db.add(User(id="u1", email="reviewer@example.com", hashed_password="x", tenant_id="t1"))
        self.db.commit()

        self.entries = [
            _entry("MH1", ReconStatus.PASS),
            _entry("MH2", ReconStatus.CLIENT_SHEET_ERROR, "tax-type contradiction"),
        ]
        self.filings = {
            "27AADCO0061H1ZQ": {
                "gstr1_json": {"_summary": {"total_taxable": 100.0, "total_tax": 18.0,
                                            "total_invoices": 2, "sections_with_data": ["b2b"]}},
                "flagged_unresolved": [], "skipped": [],
            }
        }

    def test_create_persists_pending_review(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        self.assertEqual(review.status, "PENDING_REVIEW")
        self.assertIsNotNone(review.id)

        fetched = self.db.query(SalesPeriodReview).filter(SalesPeriodReview.id == review.id).first()
        self.assertEqual(fetched.tenant_id, "t1")
        self.assertEqual(fetched.period, "2026-06")

    def test_approve_transitions_and_records_reviewer(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        approved = approve_period_review(self.db, review.id, "u1", notes="looks good")
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.reviewed_by, "u1")
        self.assertIsNotNone(approved.reviewed_at)
        self.assertEqual(approved.review_notes, "looks good")

    def test_cannot_approve_an_already_decided_review(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        approve_period_review(self.db, review.id, "u1")
        with self.assertRaises(ReviewStateError):
            approve_period_review(self.db, review.id, "u1")

    def test_reject_requires_a_reason(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        with self.assertRaises(ValueError):
            reject_period_review(self.db, review.id, "u1", notes="")

    def test_reject_transitions_correctly(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        rejected = reject_period_review(self.db, review.id, "u1", notes="client sheet needs fixing first")
        self.assertEqual(rejected.status, "REJECTED")
        self.assertEqual(rejected.review_notes, "client sheet needs fixing first")

    def test_cannot_reject_an_already_approved_review(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        approve_period_review(self.db, review.id, "u1")
        with self.assertRaises(ReviewStateError):
            reject_period_review(self.db, review.id, "u1", notes="changed my mind")

    def test_get_review_detail_deserializes_json_fields(self):
        review = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        detail = get_review_detail(review)
        self.assertEqual(detail["status"], "PENDING_REVIEW")
        self.assertEqual(detail["recon_summary"]["counts"]["PASS"], 1)
        self.assertIn("27AADCO0061H1ZQ", detail["filings_summary"])

    def test_new_review_created_instead_of_mutating_history(self):
        # re-running reconciliation for the same period must create a
        # SEPARATE review, not silently overwrite a decided one
        review1 = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        approve_period_review(self.db, review1.id, "u1")
        review2 = create_period_review(self.db, "t1", "2026-06", self.entries, self.filings)
        self.assertNotEqual(review1.id, review2.id)
        self.assertEqual(review2.status, "PENDING_REVIEW")
        # the original decision must still be intact
        self.db.refresh(review1)
        self.assertEqual(review1.status, "APPROVED")


def _build_client_sheet(path, rows):
    """Minimal Sales_masterdata(Input)-shaped fixture - same column
    layout as test_client_sheet_parser.py's fixture, trimmed to just the
    columns generate_period_review_for_tenant's reconciliation needs."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales_masterdata(Input)"
    ws.append(["Input"] * 14)
    ws.append([
        "S.no", "Document Type Code( Invoice/Credit note /Debit note)", "Document  no",
        "Document  Date", "Recipient Billing Name", "Recipient Billing GSTIN",
        "B2B or B2C", "State  of Supply  \n(Code _Two Digit )",
        "Interstate or Intrastate \n(Drop Down only)",
        "Net Basic Amt", "IGST", "SGST", "CGST", "Invoice Value",
    ])
    for r in rows:
        ws.append(r)
    wb.save(path)


class TestGeneratePeriodReviewForTenant(unittest.TestCase):
    """
    Covers the shared code path main.py's manual endpoint and
    celery_app.py's scheduled sales_ingestion_task both call through
    (services/google_drive_sync.py's _maybe_generate_period_review) -
    proves the skip_if_pending semantics that make the automatic daily
    chain safe (no duplicate PENDING_REVIEW pile-up) without changing
    the manual endpoint's always-fresh behavior.
    """

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id="t1", name="OneStack", slug="onestack"))
        self.db.add(User(id="u1", email="reviewer@example.com", hashed_password="x", tenant_id="t1"))
        self.db.add(BatchJob(id="b1", tenant_id="t1", status=TaskStatus.COMPLETED))
        self.db.add(InvoiceTask(id="task1", batch_id="b1", file_name="KRUSHISEVA.pdf", status=TaskStatus.COMPLETED))
        self.db.add(SalesLineItem(
            task_id="task1", voucher_date="15-06-2026", voucher_type="Sales",
            invoice_no="MH1", party_ledger_name="Krushiseva", party_gstin="27AAAAA0000A1Z5",
            taxable_value=76.61, cgst_amount=6.89, sgst_amount=6.89, igst_amount=0.0,
            total_invoice_value=90.39,
        ))
        self.db.commit()

        self.tmp_dir = tempfile.mkdtemp(prefix="period_review_chain_test_")
        self.sheet_path = os.path.join(self.tmp_dir, "sheet.xlsx")
        _build_client_sheet(self.sheet_path, [[
            1, "Invoice", "MH1", "15-06-2026", "Krushiseva", "27AAAAA0000A1Z5",
            "B2B", "27", "Intrastate", 76.61, 0.0, 6.89, 6.89, 90.39,
        ]])

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_month_matches_period(self):
        self.assertTrue(month_matches_period("15-06-2026", "2026-06"))
        self.assertFalse(month_matches_period("15-05-2026", "2026-06"))
        self.assertFalse(month_matches_period(None, "2026-06"))
        self.assertFalse(month_matches_period("not-a-date", "2026-06"))

    def test_creates_pending_review_from_real_query_and_sheet(self):
        review, created = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=False
        )
        self.assertTrue(created)
        self.assertEqual(review.status, "PENDING_REVIEW")
        self.assertEqual(get_latest_review(self.db, "t1", "2026-06").id, review.id)

    def test_skip_if_pending_returns_existing_review_without_duplicating(self):
        review1, created1 = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=True
        )
        review2, created2 = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=True
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(review1.id, review2.id)

    def test_skip_if_pending_still_creates_fresh_review_after_a_decision(self):
        review1, _ = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=True
        )
        approve_period_review(self.db, review1.id, "u1")

        review2, created2 = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=True
        )
        self.assertTrue(created2)
        self.assertNotEqual(review1.id, review2.id)

    def test_persisted_review_includes_matching_totals_match_sheet(self):
        # single clean invoice, no credit notes - OS/client/GSTR1 net
        # taxable totals should all agree (the "3-way total match" the
        # user asked to see reflected in the review a human actually reads).
        review, _ = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=False
        )
        detail = get_review_detail(review)
        totals_match = detail["recon_summary"]["totals_match"]
        self.assertTrue(totals_match["matches"])
        self.assertEqual(totals_match["os_net_taxable"], 76.61)
        self.assertEqual(totals_match["gstr1_net_taxable"], 76.61)

    def test_persisted_review_flags_totals_mismatch_from_uncategorized_credit_note(self):
        # reproduces the real MH bug end-to-end: a credit note ingested
        # the way credit_note_ingest.py actually does it (gstr1_category
        # left unset) must no longer corrupt the filed net taxable total -
        # net should be 76.61 - 20.00 = 56.61, not 76.61 + 20.00 = 96.61.
        self.db.add(InvoiceTask(id="task2", batch_id="b1", file_name="CR1.pdf", status=TaskStatus.COMPLETED))
        self.db.add(SalesLineItem(
            task_id="task2", voucher_date="20-06-2026", voucher_type="Credit Note",
            invoice_no="CR1", party_ledger_name="Krushiseva", party_gstin="27AAAAA0000A1Z5",
            taxable_value=20.00, cgst_amount=1.80, sgst_amount=1.80, igst_amount=0.0,
            total_invoice_value=23.60, gstr1_category=None,
            particulars="Credit Note - Sales Return (against MH1)",
        ))
        self.db.commit()

        # client sheet also carries the credit note, so OS/client/GSTR1
        # should all agree at 56.61 once the filing math is netted correctly.
        sheet_with_cn = os.path.join(self.tmp_dir, "sheet_with_cn.xlsx")
        _build_client_sheet(sheet_with_cn, [
            [1, "Invoice", "MH1", "15-06-2026", "Krushiseva", "27AAAAA0000A1Z5",
             "B2B", "27", "Intrastate", 76.61, 0.0, 6.89, 6.89, 90.39],
            [2, "Credit Note", "CR1", "20-06-2026", "Krushiseva", "27AAAAA0000A1Z5",
             "B2B", "27", "Intrastate", 20.00, 0.0, 1.80, 1.80, 23.60],
        ])

        review, _ = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", sheet_with_cn, skip_if_pending=False
        )
        detail = get_review_detail(review)
        totals_match = detail["recon_summary"]["totals_match"]
        self.assertEqual(totals_match["os_net_taxable"], 56.61)
        self.assertEqual(totals_match["client_net_taxable"], 56.61)
        self.assertEqual(totals_match["gstr1_net_taxable"], 56.61)
        self.assertTrue(totals_match["matches"])

    def test_manual_endpoint_style_call_always_creates_fresh_review(self):
        # skip_if_pending=False (what main.py's endpoint uses) must always
        # make a new review even if the latest one is still PENDING_REVIEW -
        # a human explicitly re-generating wants the current state now.
        review1, created1 = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=False
        )
        review2, created2 = generate_period_review_for_tenant(
            self.db, "t1", "2026-06", self.sheet_path, skip_if_pending=False
        )
        self.assertTrue(created1)
        self.assertTrue(created2)
        self.assertNotEqual(review1.id, review2.id)


if __name__ == "__main__":
    unittest.main()
