"""
Regression check for the duplicate-detection bug found in code review:
GoogleDriveSyncService._check_duplicate() was comparing raw invoice_no
(not normalized) and never filtered on voucher_date despite documenting
it as part of the match key.

Run: python backend/tests/test_drive_sync_duplicate_check.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import BatchJob, InvoiceTask, SalesLineItem, TaskStatus
from services.google_drive_sync import GoogleDriveSyncPipeline as GoogleDriveSyncService


class _FakeSyncService:
    """Duck-typed stand-in: _check_duplicate only touches self.db / self.tenant_id."""
    def __init__(self, db, tenant_id):
        self.db = db
        self.tenant_id = tenant_id


def _seed(db, tenant_id, invoice_no, party_gstin, voucher_date, task_id):
    batch = BatchJob(id=f"batch-{task_id}", tenant_id=tenant_id, status=TaskStatus.COMPLETED)
    task = InvoiceTask(id=task_id, batch_id=batch.id, file_name=f"{task_id}.pdf", status=TaskStatus.COMPLETED)
    item = SalesLineItem(
        task_id=task_id, invoice_no=invoice_no, party_gstin=party_gstin, voucher_date=voucher_date,
    )
    db.add_all([batch, task, item])
    db.commit()


class TestDuplicateCheck(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.tenant_id = "tenant-1"
        _seed(self.db, self.tenant_id, "INV-2024-001", "27AAAAA1111A1Z1", "2024-06-15", "task-existing")
        self.svc = _FakeSyncService(self.db, self.tenant_id)

    def test_case_and_whitespace_variant_is_caught(self):
        result = GoogleDriveSyncService._check_duplicate(
            self.svc, "inv-2024-001 ", "27aaaaa1111a1z1", "2024-06-15", "task-new"
        )
        self.assertIsNotNone(result, "normalized-equal invoice_no/gstin must be caught as a duplicate")

    def test_different_voucher_date_is_not_a_duplicate(self):
        result = GoogleDriveSyncService._check_duplicate(
            self.svc, "INV-2024-001", "27AAAAA1111A1Z1", "2024-07-15", "task-new"
        )
        self.assertIsNone(result, "a different voucher_date must NOT be treated as the same invoice")

    def test_same_task_excluded(self):
        result = GoogleDriveSyncService._check_duplicate(
            self.svc, "INV-2024-001", "27AAAAA1111A1Z1", "2024-06-15", "task-existing"
        )
        self.assertIsNone(result, "a task must not be flagged as a duplicate of itself")


if __name__ == "__main__":
    unittest.main()
