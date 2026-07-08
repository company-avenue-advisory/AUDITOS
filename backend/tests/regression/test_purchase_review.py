"""
Regression tests for services.purchase_review + services.gstr2b_ingest -
the Phase A GSTR-2B automation gate (mirrors services/period_review.py's
tests for the Sales side, same in-memory-DB approach).
"""
import sys
import os
import json
import tempfile
import shutil
import unittest

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../backend"))
sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Tenant, User, PurchaseLineItem, InvoiceTask, BatchJob, TaskStatus, PurchaseGstr2bReview
from services.purchase_review import (
    create_review, approve_review, reject_review, get_review_detail, ReviewStateError,
    generate_review_for_tenant, month_matches_period, get_latest_review,
)
from services.gstr2b_ingest import extract_recipient_gstin, list_gstr2b_json_files


def _write_gstr2b_json(path, gstin, inv_no, taxable, igst=0.0, cgst=0.0, sgst=0.0):
    total = taxable + igst + cgst + sgst
    payload = {
        "gstin": gstin,
        "data": {
            "docdata": {
                "b2b": [{
                    "ctin": "27AAAAK0891Q2Z3",
                    "inv": [{
                        "inum": inv_no, "dt": "15-06-2026", "val": total,
                        "itms": [{"itm_det": {"txval": taxable, "igst": igst, "cgst": cgst, "sgst": sgst}}],
                    }],
                }],
            },
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


class TestExtractRecipientGstin(unittest.TestCase):

    def test_top_level_gstin_field(self):
        self.assertEqual(extract_recipient_gstin({"gstin": "27AADCO0061H1ZQ"}), "27AADCO0061H1ZQ")

    def test_nested_under_data(self):
        self.assertEqual(extract_recipient_gstin({"data": {"gstin": "06AADCO0061H1ZU"}}), "06AADCO0061H1ZU")

    def test_missing_returns_none_not_a_guess(self):
        self.assertIsNone(extract_recipient_gstin({"docdata": {"b2b": []}}))

    def test_non_dict_input_returns_none(self):
        self.assertIsNone(extract_recipient_gstin(None))
        self.assertIsNone(extract_recipient_gstin("not a dict"))


class TestListGstr2bJsonFiles(unittest.TestCase):

    def test_only_json_files_returned_folders_and_other_types_excluded(self):
        FOLDER_MIME = "application/vnd.google-apps.folder"

        def lister(folder_id):
            return [
                {"id": "1", "name": "GSTR2B_MH_June2026.json", "mimeType": "application/json"},
                {"id": "2", "name": "notes.txt", "mimeType": "text/plain"},
                {"id": "3", "name": "SomeFolder", "mimeType": FOLDER_MIME},
                {"id": "4", "name": "GSTR2B_HR_June2026.json", "mimeType": "application/json"},
            ]

        files = list_gstr2b_json_files(lister, "root")
        self.assertEqual({f["id"] for f in files}, {"1", "4"})


class TestPurchaseReviewLifecycle(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id="t1", name="OneStack", slug="onestack"))
        self.db.add(User(id="u1", email="reviewer@example.com", hashed_password="x", tenant_id="t1"))
        self.db.commit()

        self.recon_result = {
            "rows": [], "extra": [],
            "summary": {
                "counts": {"matched": 1, "mismatch": 0, "missing_in_2b": 0, "not_in_books": 0},
                "amounts": {"matched": 5000.0, "mismatch": 0.0, "missing_in_2b": 0.0, "not_in_books": 0.0},
                "itc_at_risk": 0.0, "matched_itc": 5000.0, "total_rows": 1,
                "rule_36_4": {"cap": 5250.0, "total_claimed": 5000.0, "excess": 0.0, "breached": False},
            },
        }

    def test_create_persists_pending_review(self):
        review = create_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.recon_result)
        self.assertEqual(review.status, "PENDING_REVIEW")
        self.assertEqual(review.gstin, "27AADCO0061H1ZQ")
        fetched = self.db.query(PurchaseGstr2bReview).filter(PurchaseGstr2bReview.id == review.id).first()
        self.assertEqual(fetched.period, "2026-06")

    def test_approve_transitions_and_records_reviewer(self):
        review = create_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.recon_result)
        approved = approve_review(self.db, review.id, "u1", notes="looks good")
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.reviewed_by, "u1")
        self.assertIsNotNone(approved.reviewed_at)

    def test_cannot_approve_an_already_decided_review(self):
        review = create_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.recon_result)
        approve_review(self.db, review.id, "u1")
        with self.assertRaises(ReviewStateError):
            approve_review(self.db, review.id, "u1")

    def test_reject_requires_a_reason(self):
        review = create_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.recon_result)
        with self.assertRaises(ValueError):
            reject_review(self.db, review.id, "u1", notes="")

    def test_get_review_detail_deserializes_json_fields(self):
        review = create_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.recon_result)
        detail = get_review_detail(review)
        self.assertEqual(detail["gstin"], "27AADCO0061H1ZQ")
        self.assertEqual(detail["recon_summary"]["counts"]["matched"], 1)

    def test_two_gstins_same_period_are_independent_reviews(self):
        # OneStack has two registrations (MH/HR) - each gets its own 2B
        # and its own review, not one combined review for the tenant+period.
        r1 = create_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.recon_result)
        r2 = create_review(self.db, "t1", "2026-06", "06AADCO0061H1ZU", self.recon_result)
        self.assertNotEqual(r1.id, r2.id)
        self.assertEqual(get_latest_review(self.db, "t1", "2026-06", "27AADCO0061H1ZQ").id, r1.id)
        self.assertEqual(get_latest_review(self.db, "t1", "2026-06", "06AADCO0061H1ZU").id, r2.id)


class TestGenerateReviewForTenant(unittest.TestCase):
    """End-to-end: real PurchaseLineItem query + real GSTR-2B JSON parse +
    real gstr2b_reconciler.reconcile() call, not mocked."""

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id="t1", name="OneStack", slug="onestack"))
        self.db.add(User(id="u1", email="reviewer@example.com", hashed_password="x", tenant_id="t1"))
        self.db.add(BatchJob(id="b1", tenant_id="t1", status=TaskStatus.COMPLETED))
        self.db.add(InvoiceTask(id="task1", batch_id="b1", file_name="vendor.pdf", status=TaskStatus.COMPLETED))
        self.db.add(PurchaseLineItem(
            task_id="task1", voucher_date="15-06-2026", invoice_no="INV-001",
            party_gstin="27AAAAK0891Q2Z3", party_ledger_name="Some Vendor",
            taxable_value=5000.0, igst_amount=900.0, cgst_amount=0.0, sgst_amount=0.0,
            total_invoice_value=5900.0,
        ))
        self.db.commit()

        self.tmp_dir = tempfile.mkdtemp(prefix="gstr2b_review_test_")
        self.json_path = os.path.join(self.tmp_dir, "gstr2b.json")
        _write_gstr2b_json(self.json_path, "27AADCO0061H1ZQ", "INV-001", 5000.0, igst=900.0)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_matches_real_purchase_item_against_real_2b_json(self):
        review, created = generate_review_for_tenant(
            self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.json_path, skip_if_pending=False
        )
        self.assertTrue(created)
        detail = get_review_detail(review)
        self.assertEqual(detail["recon_summary"]["counts"]["matched"], 1)
        self.assertEqual(detail["recon_summary"]["counts"]["mismatch"], 0)

    def test_skip_if_pending_avoids_duplicate_daily_reviews(self):
        review1, created1 = generate_review_for_tenant(
            self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.json_path, skip_if_pending=True
        )
        review2, created2 = generate_review_for_tenant(
            self.db, "t1", "2026-06", "27AADCO0061H1ZQ", self.json_path, skip_if_pending=True
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(review1.id, review2.id)

    def test_month_matches_period(self):
        self.assertTrue(month_matches_period("15-06-2026", "2026-06"))
        self.assertFalse(month_matches_period("15-05-2026", "2026-06"))
        self.assertFalse(month_matches_period(None, "2026-06"))


if __name__ == "__main__":
    unittest.main()
