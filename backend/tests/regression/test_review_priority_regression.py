"""
Regression tests for Bootstrap Task 4: Correction Capture & Intelligent
Review Queue.

Two things are tested:

1. services/review_priority.py's compute_priority_score / sort_tasks_by_priority
   -- pure functions, no DB, no mocking needed. Confirms the weighted
   ordering (reconciliation-blocked and low-confidence tasks surface first,
   duplicates and high-value invoices bump priority, missing signals never
   crash the scorer) matches the documented weights.

2. The new structured-correction-event path: UserAnnotation's Bootstrap
   Task 4 columns (confidence_before, validation_status,
   reconciliation_status) and InvoiceTask.validation_status persist and
   round-trip correctly through a real in-memory SQLite DB -- proving the
   additive schema change is actually additive (existing columns/rows
   unaffected) and that a correction event captures the full field list
   Bootstrap Task 4 requires (original value, corrected value, field name,
   reviewer, timestamp, confidence, validation status, reconciliation
   status, reason).
"""
import sys
import os
import unittest

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../backend"))
sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Tenant, User, BatchJob, InvoiceTask, TaskStatus, UserAnnotation
from services.review_priority import compute_priority_score, sort_tasks_by_priority


class TestComputePriorityScore(unittest.TestCase):

    def test_low_confidence_scores_higher_than_high_confidence(self):
        low = compute_priority_score(0.2, None, None, False, 0, 0.0)
        high = compute_priority_score(0.95, None, None, False, 0, 0.0)
        self.assertGreater(low, high)

    def test_missing_confidence_does_not_crash_and_uses_neutral_value(self):
        # Should not raise, and should sit between a very-low and very-high
        # confidence score (neutral, not treated as either extreme).
        score = compute_priority_score(None, None, None, False, 0, 0.0)
        low = compute_priority_score(0.0, None, None, False, 0, 0.0)
        high = compute_priority_score(1.0, None, None, False, 0, 0.0)
        self.assertLess(score, low)
        self.assertGreater(score, high)

    def test_reconciliation_blocked_outranks_needs_review(self):
        blocked = compute_priority_score(0.9, "BLOCKED", None, False, 0, 0.0)
        needs_review = compute_priority_score(0.9, "NEEDS_REVIEW", None, False, 0, 0.0)
        erp_ready = compute_priority_score(0.9, "ERP_READY", None, False, 0, 0.0)
        self.assertGreater(blocked, needs_review)
        self.assertGreater(needs_review, erp_ready)

    def test_validation_failed_increases_score(self):
        failed = compute_priority_score(0.9, None, "FAILED", False, 0, 0.0)
        passed = compute_priority_score(0.9, None, "PASSED", False, 0, 0.0)
        self.assertGreater(failed, passed)

    def test_duplicate_increases_score(self):
        dup = compute_priority_score(0.9, None, None, True, 0, 0.0)
        not_dup = compute_priority_score(0.9, None, None, False, 0, 0.0)
        self.assertGreater(dup, not_dup)

    def test_manual_flag_count_is_capped(self):
        # 3 and 10 flags should score identically -- the cap must actually cap.
        three = compute_priority_score(0.9, None, None, False, 3, 0.0)
        ten = compute_priority_score(0.9, None, None, False, 10, 0.0)
        self.assertEqual(three, ten)

    def test_high_value_invoice_increases_score(self):
        high_value = compute_priority_score(0.9, None, None, False, 0, 500_000.0)
        low_value = compute_priority_score(0.9, None, None, False, 0, 100.0)
        self.assertGreater(high_value, low_value)

    def test_score_never_negative(self):
        best_case = compute_priority_score(1.0, "ERP_READY", "PASSED", False, 0, 0.0)
        self.assertGreaterEqual(best_case, 0.0)


class TestSortTasksByPriority(unittest.TestCase):

    def test_worst_task_sorts_first(self):
        tasks = [
            {"task_id": "good", "composite_score": 0.95, "recon_status": "ERP_READY"},
            {"task_id": "bad", "composite_score": 0.1, "recon_status": "BLOCKED", "is_duplicate": True},
            {"task_id": "mid", "composite_score": 0.6, "recon_status": "NEEDS_REVIEW"},
        ]
        result = sort_tasks_by_priority(tasks)
        self.assertEqual([t["task_id"] for t in result], ["bad", "mid", "good"])

    def test_every_task_gets_a_priority_score_attached(self):
        tasks = [{"task_id": "a"}, {"task_id": "b"}]
        result = sort_tasks_by_priority(tasks)
        for t in result:
            self.assertIn("priority_score", t)

    def test_missing_optional_fields_do_not_crash(self):
        # Simulates a caller that hasn't populated the newer Task 4 fields
        # (validation_status, is_duplicate, manual_flag_count) at all.
        tasks = [{"task_id": "a", "composite_score": 0.5, "recon_status": "NEEDS_REVIEW"}]
        result = sort_tasks_by_priority(tasks)
        self.assertEqual(len(result), 1)

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(sort_tasks_by_priority([]), [])


class TestCorrectionEventPersistence(unittest.TestCase):
    """Proves the additive schema changes actually persist and round-trip."""

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id="t1", name="OneStack", slug="onestack"))
        self.db.add(User(id="u1", email="reviewer@example.com", hashed_password="x", tenant_id="t1"))
        self.db.add(BatchJob(id="b1", tenant_id="t1", status=TaskStatus.COMPLETED))
        self.db.add(InvoiceTask(
            id="task1", batch_id="b1", file_name="invoice.pdf", status=TaskStatus.COMPLETED,
            recon_status="NEEDS_REVIEW", validation_status="FAILED",
        ))
        self.db.commit()

    def test_invoice_task_validation_status_persists(self):
        task = self.db.query(InvoiceTask).filter(InvoiceTask.id == "task1").first()
        self.assertEqual(task.validation_status, "FAILED")
        self.assertEqual(task.recon_status, "NEEDS_REVIEW")

    def test_correction_event_captures_the_full_required_field_set(self):
        annotation = UserAnnotation(
            user_id="u1",
            task_id="task1",
            field_name="taxable_value",
            note="Vendor invoice shows net-of-discount, extractor read gross.",
            original_value="1000.0",
            corrected_value="900.0",
            confidence_before=0.62,
            validation_status="FAILED",
            reconciliation_status="NEEDS_REVIEW",
        )
        self.db.add(annotation)
        self.db.commit()

        row = self.db.query(UserAnnotation).filter(UserAnnotation.task_id == "task1").first()
        self.assertEqual(row.field_name, "taxable_value")
        self.assertEqual(row.original_value, "1000.0")
        self.assertEqual(row.corrected_value, "900.0")
        self.assertEqual(row.user_id, "u1")
        self.assertIsNotNone(row.created_at)
        self.assertAlmostEqual(row.confidence_before, 0.62)
        self.assertEqual(row.validation_status, "FAILED")
        self.assertEqual(row.reconciliation_status, "NEEDS_REVIEW")
        self.assertEqual(row.note, "Vendor invoice shows net-of-discount, extractor read gross.")

    def test_correction_events_are_append_only_across_multiple_edits(self):
        """Two corrections to the same field must produce two rows, never
        an update to the first -- the immutability requirement."""
        for corrected in ("900.0", "950.0"):
            self.db.add(UserAnnotation(
                user_id="u1", task_id="task1", field_name="taxable_value",
                original_value="1000.0", corrected_value=corrected,
            ))
            self.db.commit()

        rows = self.db.query(UserAnnotation).filter(
            UserAnnotation.task_id == "task1", UserAnnotation.field_name == "taxable_value"
        ).order_by(UserAnnotation.created_at.asc()).all()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].corrected_value, "900.0")
        self.assertEqual(rows[1].corrected_value, "950.0")

    def test_new_columns_are_nullable_for_backward_compatibility(self):
        """Existing-shape inserts (pre-Task-4, no new fields) must still work."""
        annotation = UserAnnotation(
            user_id="u1", task_id="task1", field_name="hsn",
            note="typo fix", original_value="1234", corrected_value="1235",
        )
        self.db.add(annotation)
        self.db.commit()
        row = self.db.query(UserAnnotation).filter(UserAnnotation.field_name == "hsn").first()
        self.assertIsNone(row.confidence_before)
        self.assertIsNone(row.validation_status)
        self.assertIsNone(row.reconciliation_status)


if __name__ == "__main__":
    unittest.main()
