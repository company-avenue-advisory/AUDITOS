"""
Setup script for the self-resolving Sales ingestion schedule
(tasks.sales_ingestion_task in celery_app.py).

Unlike setup_google_drive_sync.py (which bakes one fixed
google_drive_folder_id into the schedule forever), this registers a
tenant_slug - the actual month folder is resolved at RUN TIME via
drive_path_resolver.py + data/drive_paths/{tenant_slug}.json, so the
schedule never needs re-registering when a new month's Drive folder
appears.

Usage:
  python setup_sales_ingestion_schedule.py \
    --tenant-id <tenant-uuid> \
    --tenant-slug onestack \
    --excel-output-path /path/to/output.xlsx \
    --schedule "0 2 * * *"   # daily at 02:00 UTC (default) - invoices
                              # trickle in throughout the month, not just
                              # on day one, confirmed against real Drive
                              # timestamps this session

Requires:
  - data/drive_paths/<tenant-slug>.json already exists (see
    drive_path_resolver.py's TenantDrivePath schema)
  - GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON env var set
  - A running celery beat process actually dispatching this schedule -
    beat_schedules.json entries do nothing on their own (confirmed this
    session: render.yaml/START_ALL_WINDOWS.bat had no beat service at
    all before this same change - the worker only runs tasks it's
    handed, it doesn't invent its own schedule).
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


def verify_drive_path_config_and_access(tenant_slug: str, invoice_type: str = "sales") -> bool:
    """
    Verifies data/drive_paths/{tenant_slug}.json exists and that the
    current month's folder can actually be resolved (or, if not created
    yet, that the config and Drive access are at least valid) - a real
    connection check, not just "the JSON file parses". Checks against
    purchase_root_folder_id instead of sales_root_folder_id when
    invoice_type="purchase" - they're different Drive trees.
    """
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

    root_folder_id = cfg.purchase_root_folder_id if invoice_type == "purchase" else cfg.sales_root_folder_id
    if not root_folder_id:
        logger.error(f"No {'purchase' if invoice_type == 'purchase' else 'sales'}_root_folder_id configured for '{tenant_slug}'.")
        return False

    try:
        connector = GoogleDriveConnector(root_folder_id)

        def lister(folder_id):
            return connector.list_files(file_types=None, folder_id=folder_id)

        folder_id = resolve_month_folder_id(lister, cfg, date.today(), root_folder_id=root_folder_id)
        if folder_id:
            logger.info(f"Resolved current month's folder for '{tenant_slug}': {folder_id}")
        else:
            logger.warning(
                f"Current month's folder doesn't exist yet for '{tenant_slug}' - that's fine, "
                f"the scheduled task will pick it up automatically once it's created."
            )
        return True
    except Exception as e:
        logger.error(f"Drive access failed for '{tenant_slug}': {e}")
        return False


def setup_celery_beat(tenant_id: str, tenant_slug: str, excel_output_path: str,
                       invoice_type: str, cron_expression: str) -> bool:
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        logger.error(f"Invalid cron expression (expected 5 fields): {cron_expression}")
        return False

    # invoice_type="purchase" must register celery_app.purchase_ingestion_task,
    # not sales_ingestion_task - they resolve against different Drive
    # roots (purchase_root_folder_id vs sales_root_folder_id) and
    # purchase_ingestion_task's signature has no invoice_type kwarg at
    # all (it's hardcoded "purchase" internally, since a Purchase sync
    # only ever walks the Purchase tree). Previously this always
    # registered sales_ingestion_task regardless of invoice_type, which
    # would have silently scheduled a Sales-tree sync even when Purchase
    # was requested.
    if invoice_type == "purchase":
        schedule_name = f"purchase_ingestion_{tenant_slug}"
        entry = {
            "task": "tasks.purchase_ingestion_task",
            "cron": cron_expression,
            "kwargs": {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "excel_output_path": excel_output_path,
                "model_config": None,
            },
            "options": {"queue": "drive_sync", "priority": 10},
            "registered_at": datetime.utcnow().isoformat(),
        }
    else:
        schedule_name = f"sales_ingestion_{tenant_slug}"
        entry = {
            "task": "tasks.sales_ingestion_task",
            "cron": cron_expression,
            "kwargs": {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "excel_output_path": excel_output_path,
                "invoice_type": invoice_type,
                "model_config": None,
            },
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
        logger.info(f"  Cron: {cron_expression}  |  Invoice type: {invoice_type}")
        logger.info("Restart celery beat for the schedule to take effect:")
        logger.info("  celery -A celery_app beat --loglevel=info")
        logger.info("(and make sure a worker is running with -Q ...,drive_sync - see render.yaml)")
        return True
    except Exception as e:
        logger.error(f"Error writing beat schedule to registry: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Set up self-resolving Sales ingestion schedule")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--tenant-slug", required=True, help="Matches data/drive_paths/<slug>.json")
    parser.add_argument("--excel-output-path", required=True)
    parser.add_argument("--invoice-type", default="sales", choices=["sales", "purchase", "both"])
    parser.add_argument("--schedule", default="0 2 * * *",
                         help="Cron expression - default daily at 02:00 UTC, since invoices "
                              "trickle in throughout the month, not just on day one")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Sales Ingestion Schedule Setup (self-resolving month folder)")
    logger.info("=" * 60)

    init_database()

    if not verify_tenant(args.tenant_id):
        return 1
    if not verify_drive_path_config_and_access(args.tenant_slug, args.invoice_type):
        return 1

    if args.test_only:
        logger.info("All checks passed! Setup is ready.")
        return 0

    if not setup_celery_beat(args.tenant_id, args.tenant_slug, args.excel_output_path,
                              args.invoice_type, args.schedule):
        return 1

    logger.info("=" * 60)
    logger.info("Setup completed successfully!")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
