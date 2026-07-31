"""
Regression tests for services.observability — the ObsLogger instrumentation
layer that writes every pipeline event to ObservabilityLog.

Covers the two gaps closed by Bootstrap Task 3 (Metrics & Instrumentation):

1. tenant_id was silently dropped by several classmethod event writers
   (emit_batch_envelope, emit_file_manifest, emit_batch_metrics,
   _check_batch_alerts, emit_ca_flag) even though every real call site
   already resolves the tenant. These tests prove tenant_id now reaches
   the row for each of those event types.

2. evaluate_flags previously had no way to know whether the Financial
   Reconciliation Engine actually succeeded or what confidence it
   reported — callers either omitted this signal or reported a hardcoded
   placeholder. reconciliation_status / reconciliation_confidence are new,
   optional (backward-compatible) parameters; these tests prove the two
   new rules fire correctly and, just as importantly, stay silent when
   the caller doesn't pass reconciliation info at all (existing callers
   are unaffected).

Uses a real in-memory SQLite DB (not mocked), matching the pattern
already used in test_period_review.py / test_purchase_review.py.
"""
import sys
import os
import unittest

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../backend"))
sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import ObservabilityLog
from services.observability import ObsLogger


class TestTenantIdThreading(unittest.TestCase):
    """Every classmethod event writer must persist the tenant_id it's given."""

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def _tenant_id_for(self, event_type: str) -> str:
        row = self.db.query(ObservabilityLog).filter(
            ObservabilityLog.event_type == event_type
        ).first()
        self.assertIsNotNone(row, f"no {event_type} row was written")
        return row.tenant_id

    def test_emit_batch_envelope_persists_tenant_id(self):
        ObsLogger.emit_batch_envelope(
            batch_id="b1", session_id="s1", model_selected="auto",
            model_identifier="gemini-2.5-flash", api_provider="gemini",
            api_endpoint="https://example", total_files=3, batch_type="sales",
            environment="test", db_session=self.db, tenant_id="tenant-abc",
        )
        self.assertEqual(self._tenant_id_for("batch_received"), "tenant-abc")

    def test_emit_file_manifest_persists_tenant_id(self):
        ObsLogger.emit_file_manifest(
            batch_id="b1", files_meta=[{"file_id": "f1", "filename": "x.pdf", "size_bytes": 100}],
            db_session=self.db, tenant_id="tenant-abc",
        )
        self.assertEqual(self._tenant_id_for("file_manifest"), "tenant-abc")

    def test_emit_batch_metrics_and_alerts_persist_tenant_id(self):
        # A high error rate deliberately triggers _check_batch_alerts' internal
        # system_flag write too, so this one call proves tenant_id threads
        # through both emit_batch_metrics AND the alert path it calls into.
        tasks_meta = [
            {"status": "failed", "total_ms": 100, "cost_inr": 1.0, "corrections": 0,
             "unallocated_injected": False, "rates_snapped": 0, "json_ok": True, "composite_score": 0.0},
            {"status": "failed", "total_ms": 100, "cost_inr": 1.0, "corrections": 0,
             "unallocated_injected": False, "rates_snapped": 0, "json_ok": True, "composite_score": 0.0},
        ]
        ObsLogger.emit_batch_metrics(
            batch_id="b1", tasks_meta=tasks_meta, model_identifier="gemini-2.5-flash",
            api_provider="gemini", db_session=self.db, tenant_id="tenant-abc",
        )
        self.assertEqual(self._tenant_id_for("batch_metrics"), "tenant-abc")
        # error_rate_pct is 100% here, which crosses the >10% BATCH_FAILURE_RATE
        # threshold in _check_batch_alerts — confirms that path also got tenant_id.
        self.assertEqual(self._tenant_id_for("system_flag"), "tenant-abc")

    def test_emit_ca_flag_persists_tenant_id(self):
        ObsLogger.emit_ca_flag(
            batch_id="b1", file_id="f1", rejected_field="taxable_value",
            extracted_value=100.0, ca_corrected_value=110.0, composite_score=0.9,
            db_session=self.db, tenant_id="tenant-abc",
        )
        self.assertEqual(self._tenant_id_for("ca_review_flag"), "tenant-abc")

    def test_tenant_id_defaults_to_none_when_not_supplied(self):
        """Backward compatibility: existing callers that don't pass tenant_id
        must not break — the column stays nullable and simply records None."""
        ObsLogger.emit_file_manifest(batch_id="b1", files_meta=[], db_session=self.db)
        self.assertIsNone(self._tenant_id_for("file_manifest"))


class TestReconciliationAwareFlags(unittest.TestCase):
    """evaluate_flags' new reconciliation_status / reconciliation_confidence
    parameters must fire the right rule and stay silent when absent."""

    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.logger = ObsLogger(
            batch_id="b1", file_id="f1", model_identifier="gemini-2.5-flash",
            api_provider="gemini", db_session=self.db, tenant_id="tenant-abc",
        )

    def _base_kwargs(self, **overrides):
        kwargs = dict(
            filename="invoice.pdf", composite_score=0.9, correction_meta={},
            json_parse_ok=True, statutory_math_balanced=True, gstin_format_valid=True,
            no_igst_cgst_conflict=True, total_cost_inr=5.0, batch_avg_cost=5.0,
            raw_items=1,
        )
        kwargs.update(overrides)
        return kwargs

    def test_blocked_reconciliation_status_emits_flag(self):
        flags = self.logger.evaluate_flags(**self._base_kwargs(
            reconciliation_status="BLOCKED", reconciliation_confidence=0.9,
        ))
        self.assertIn("RECONCILIATION_BLOCKED", flags)

    def test_low_reconciliation_confidence_emits_flag(self):
        flags = self.logger.evaluate_flags(**self._base_kwargs(
            reconciliation_status="NEEDS_REVIEW", reconciliation_confidence=0.4,
        ))
        self.assertIn("RECONCILIATION_LOW_CONFIDENCE", flags)

    def test_erp_ready_high_confidence_emits_neither_reconciliation_flag(self):
        flags = self.logger.evaluate_flags(**self._base_kwargs(
            reconciliation_status="ERP_READY", reconciliation_confidence=0.95,
        ))
        self.assertNotIn("RECONCILIATION_BLOCKED", flags)
        self.assertNotIn("RECONCILIATION_LOW_CONFIDENCE", flags)

    def test_absent_reconciliation_info_does_not_fire_either_rule(self):
        """Existing callers (pre-Task-3) that don't pass reconciliation_status /
        reconciliation_confidence at all must see identical behavior to before —
        the two new rules must not fire on missing data."""
        flags = self.logger.evaluate_flags(**self._base_kwargs())
        self.assertNotIn("RECONCILIATION_BLOCKED", flags)
        self.assertNotIn("RECONCILIATION_LOW_CONFIDENCE", flags)


if __name__ == "__main__":
    unittest.main()
