"""
Regression tests for services.period_review - the human review gate
between reconciliation/filing generation and anything reaching a GST
portal. Uses a real in-memory SQLite DB (not mocked) to prove the state
machine and persistence actually work, matching the pattern already
used for credit_note_ingest.py's wiring tests this session.
"""
import sys
import os
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
from models import Tenant, User, SalesPeriodReview
from services.period_review import (
    build_recon_summary, build_filings_summary, create_period_review,
    approve_period_review, reject_period_review, get_review_detail, ReviewStateError,
)
from services.sales_reconciliation import ReconEntry, ReconStatus


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


if __name__ == "__main__":
    unittest.main()
