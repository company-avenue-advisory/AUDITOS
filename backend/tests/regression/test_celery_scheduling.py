"""
Regression tests for the Celery Beat scheduling wiring added this
session (celery_app.py's beat_schedule loader, and
scripts/setup_sales_ingestion_schedule.py's schedule-writing logic).

Does NOT require a running broker/Redis - both pieces under test are
pure file I/O + crontab-object construction, no network calls.

Locks in the two real gaps found and fixed this session:
  1. celery_app._load_beat_schedules() must correctly parse a
     well-formed cron entry into a real crontab schedule, and skip
     (not crash on) a malformed one - confirmed this session that
     scheduled tasks silently never fire if this parsing is wrong.
  2. setup_sales_ingestion_schedule.py must write "tenant_slug" into the
     registered task's kwargs, NOT a fixed "google_drive_folder_id" like
     the older setup_google_drive_sync.py does - that's the whole point
     of the self-resolving task (the folder ID changes every month and
     can never be baked into a schedule).
"""
import sys
import os
import json
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import backend.celery_app as celery_app_module
import backend.scripts.setup_sales_ingestion_schedule as setup_module


class TestLoadBeatSchedules(unittest.TestCase):

    def setUp(self):
        self._orig_backend_dir = celery_app_module.backend_dir
        self.tmp_dir = tempfile.mkdtemp(prefix="beat_schedule_test_")
        os.makedirs(os.path.join(self.tmp_dir, "data"), exist_ok=True)
        celery_app_module.backend_dir = self.tmp_dir

    def tearDown(self):
        celery_app_module.backend_dir = self._orig_backend_dir

    def _write_registry(self, registry: dict):
        path = os.path.join(self.tmp_dir, "data", "beat_schedules.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(registry, f)

    def test_valid_cron_entry_parses_into_real_schedule(self):
        self._write_registry({
            "sales_ingestion_onestack": {
                "task": "tasks.sales_ingestion_task",
                "cron": "0 2 * * *",
                "kwargs": {"tenant_id": "t1", "tenant_slug": "onestack"},
            }
        })
        schedules = celery_app_module._load_beat_schedules()
        self.assertIn("sales_ingestion_onestack", schedules)
        entry = schedules["sales_ingestion_onestack"]
        self.assertEqual(entry["task"], "tasks.sales_ingestion_task")
        self.assertEqual(entry["kwargs"]["tenant_slug"], "onestack")
        # the schedule object itself should be a real crontab, not a string
        self.assertTrue(hasattr(entry["schedule"], "is_due"))

    def test_malformed_cron_is_skipped_not_crashed_on(self):
        self._write_registry({
            "broken": {"task": "tasks.sales_ingestion_task", "cron": "not a cron"},
            "fine": {"task": "tasks.sales_ingestion_task", "cron": "0 2 * * *"},
        })
        schedules = celery_app_module._load_beat_schedules()
        self.assertNotIn("broken", schedules)
        self.assertIn("fine", schedules)

    def test_missing_registry_file_returns_empty_not_crashed_on(self):
        # no file written at all this time
        schedules = celery_app_module._load_beat_schedules()
        self.assertEqual(schedules, {})


class TestSetupSalesIngestionSchedule(unittest.TestCase):

    def setUp(self):
        self._orig_backend_dir = setup_module.backend_dir
        self.tmp_dir = tempfile.mkdtemp(prefix="setup_schedule_test_")
        os.makedirs(os.path.join(self.tmp_dir, "data"), exist_ok=True)
        setup_module.backend_dir = self.tmp_dir

    def tearDown(self):
        setup_module.backend_dir = self._orig_backend_dir

    def test_writes_tenant_slug_not_a_fixed_folder_id(self):
        ok = setup_module.setup_celery_beat(
            tenant_id="t1", tenant_slug="onestack",
            excel_output_path="/tmp/out.xlsx", invoice_type="sales",
            cron_expression="0 2 * * *",
        )
        self.assertTrue(ok)
        registry_path = os.path.join(self.tmp_dir, "data", "beat_schedules.json")
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
        entry = registry["sales_ingestion_onestack"]
        self.assertEqual(entry["task"], "tasks.sales_ingestion_task")
        self.assertEqual(entry["kwargs"]["tenant_slug"], "onestack")
        self.assertNotIn("google_drive_folder_id", entry["kwargs"])
        self.assertEqual(entry["options"]["queue"], "drive_sync")

    def test_rejects_invalid_cron_expression(self):
        ok = setup_module.setup_celery_beat(
            tenant_id="t1", tenant_slug="onestack",
            excel_output_path="/tmp/out.xlsx", invoice_type="sales",
            cron_expression="not five fields",
        )
        self.assertFalse(ok)

    def test_second_tenant_does_not_clobber_first(self):
        setup_module.setup_celery_beat("t1", "onestack", "/tmp/a.xlsx", "sales", "0 2 * * *")
        setup_module.setup_celery_beat("t2", "otherclient", "/tmp/b.xlsx", "sales", "0 3 * * *")
        registry_path = os.path.join(self.tmp_dir, "data", "beat_schedules.json")
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
        self.assertIn("sales_ingestion_onestack", registry)
        self.assertIn("sales_ingestion_otherclient", registry)


if __name__ == "__main__":
    unittest.main()
