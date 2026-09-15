"""
Setup script for the self-resolving GSTR-2B ingestion schedule
(tasks.gstr2b_ingestion_task in celery_app.py) - Phase A automation.

Simpler than setup_sales_ingestion_schedule.py: no excel_output_path, no
invoice_type - a GSTR-2B sync just needs a tenant and a
gstr2b_root_folder_id already present in data/drive_paths/<slug>.json.

Usage:
  python setup_gstr2b_ingestion_schedule.py \
    --tenant-id <tenant-uuid> \
    --tenant-slug onestack \
    --schedule "0 3 * * *"   # daily at 03:00 UTC by default - a GSTR-2B
                              # is only issued once a month (14th of the
                              # following month), but checking daily costs
                              # nothing and catches it the moment someone
                              # drops the file, matching the trickle-in
                              # reasoning already used for Sales/Purchase.

Requires:
  - data/drive_paths/<tenant-slug>.json has a "gstr2b_root_folder_id" set
    (create the Drive folder and share it with the service account first -
    no such folder exists yet for OneStack as of this writing)
  - GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON env var set
  - A running celery beat process + a worker consuming the drive_sync
    queue (same requirement as Sales/Purchase - see render.yaml)
"""

import os
import sys
import argparse
import json
import logging
from datetime import date, datetime

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import SessionLocal, engine, Base
from models import Tenant

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def init_database():
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)


def verify_tenant(tenant_id: str) -> bool:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant:
            logger.info(f"Tenant found: {tenant.name}")
            return True
        logger.error(f"Tenant not found: {tenant_id}")
        return False
    finally:
        db.close()


def verify_gstr2b_config_and_access(tenant_slug: str) -> bool:
    """Verifies gstr2b_root_folder_id is configured and reachable - a
    real connection check, not just "the JSON file parses"."""
    from services.drive_path_resolver import load_tenant_path_config, resolve_month_folder_id
    from services.google_drive import GoogleDriveConnector

    try:
        cfg = load_tenant_path_config(tenant_slug)
    except FileNotFoundError:
        logger.error(f"data/drive_paths/{tenant_slug}.json not found - create it before scheduling.")
        return False
    except Exception as e:
        logger.error(f"Could not load drive path config for '{tenant_slug}': {e}")
        return False

    if not cfg.gstr2b_root_folder_id:
        logger.error(
            f"No gstr2b_root_folder_id configured for '{tenant_slug}' - create the Drive "
            f"folder, share it with the service account, and add its ID to "
            f"data/drive_paths/{tenant_slug}.json before scheduling."
        )
        return False

    try:
        connector = GoogleDriveConnector(cfg.gstr2b_root_folder_id)

        def lister(folder_id):
            return connector.list_files(file_types=None, folder_id=folder_id)

        folder_id = resolve_month_folder_id(lister, cfg, date.today(), root_folder_id=cfg.gstr2b_root_folder_id)
        if folder_id:
            logger.info(f"Resolved current month's GSTR-2B folder for '{tenant_slug}': {folder_id}")
        else:
            logger.warning(
                f"Current month's GSTR-2B folder doesn't exist yet for '{tenant_slug}' - that's "
                f"fine, the scheduled task will pick it up automatically once it's created."
            )
        return True
    except Exception as e:
        logger.error(f"Drive access failed for '{tenant_slug}': {e}")
        return False


def setup_celery_beat(tenant_id: str, tenant_slug: str, cron_expression: str) -> bool:
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        logger.error(f"Invalid cron expression (expected 5 fields): {cron_expression}")
        return False

    schedule_name = f"gstr2b_ingestion_{tenant_slug}"
    entry = {
        "task": "tasks.gstr2b_ingestion_task",
        "cron": cron_expression,
        "kwargs": {"tenant_id": tenant_id, "tenant_slug": tenant_slug},
        "options": {"queue": "drive_sync", "priority": 10},
        "registered_at": datetime.utcnow().isoformat(),
    }

    registry_path = os.path.join(backend_dir, "data", "beat_schedules.json")
    try:
        registry = {}
        if os.path.exists(registry_path):
            with open(registry_path, encoding="utf-8") as f:
                registry = json.load(f)
        registry[schedule_name] = entry
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

        logger.info(f"Schedule '{schedule_name}' written to {registry_path}")
        logger.info(f"  Cron: {cron_expression}")
        logger.info("Restart celery beat for the schedule to take effect:")
        logger.info("  celery -A celery_app beat --loglevel=info")
        logger.info("(and make sure a worker is running with -Q ...,drive_sync - see render.yaml)")
        return True
    except Exception as e:
        logger.error(f"Error writing beat schedule to registry: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Set up self-resolving GSTR-2B ingestion schedule")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--tenant-slug", required=True, help="Matches data/drive_paths/<slug>.json")
    parser.add_argument("--schedule", default="0 3 * * *",
                         help="Cron expression - default daily at 03:00 UTC")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("GSTR-2B Ingestion Schedule Setup (Phase A: Drive-drop automation)")
    logger.info("=" * 60)

    init_database()

    if not verify_tenant(args.tenant_id):
        return 1
    if not verify_gstr2b_config_and_access(args.tenant_slug):
        return 1

    if args.test_only:
        logger.info("All checks passed! Setup is ready.")
        return 0

    if not setup_celery_beat(args.tenant_id, args.tenant_slug, args.schedule):
        return 1

    logger.info("=" * 60)
    logger.info("Setup completed successfully!")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
