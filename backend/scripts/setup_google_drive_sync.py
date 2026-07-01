"""
Setup script for Google Drive auto-sync.

Usage:
  python setup_google_drive_sync.py \
    --tenant-id <tenant-uuid> \
    --google-drive-folder-id <folder-id> \
    --excel-output-path /path/to/output.xlsx \
    --invoice-type both \
    --schedule "0 0 1 * *"  # Monthly on 1st at 00:00 UTC

Requires:
  - GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON env var (path to JSON key file)
  - Celery broker running (Redis/RabbitMQ)
"""

import os
import sys
import argparse
import json
import logging
from datetime import datetime

# Add backend to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import SessionLocal, engine, Base
from models import Tenant, GoogleDriveSyncJob, GoogleDriveFileTracker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database():
    """Create all tables."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def verify_tenant(tenant_id: str) -> bool:
    """Verify tenant exists."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant:
            logger.info(f"✓ Tenant found: {tenant.name}")
            return True
        else:
            logger.error(f"✗ Tenant not found: {tenant_id}")
            return False
    finally:
        db.close()


def verify_google_drive_access(folder_id: str) -> bool:
    """Verify Google Drive credentials and folder access."""
    try:
        from services.google_drive import GoogleDriveConnector

        logger.info(f"Testing Google Drive access to folder {folder_id}...")
        connector = GoogleDriveConnector(folder_id)

        # Try to list files
        files = connector.list_files(file_types=["application/pdf"])
        logger.info(f"✓ Google Drive access verified. Found {len(files)} PDF files.")
        return True

    except Exception as e:
        logger.error(f"✗ Google Drive access failed: {e}")
        logger.error("Make sure GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is set correctly")
        return False


def setup_celery_beat(tenant_id: str, google_drive_folder_id: str,
                      excel_output_path: str, invoice_type: str,
                      cron_expression: str = "0 0 1 * *"):
    """
    Register a Celery Beat schedule for periodic sync.

    Writes to backend/data/beat_schedules.json — celery_app.py reads this file
    on startup and registers all entries as live crontab schedules.

    Args:
        cron_expression: Standard 5-field cron expression.
                        Default: "0 0 1 * *" (monthly on 1st at 00:00 UTC)
    """
    logger.info("Registering Celery Beat schedule...")

    # Validate cron expression (5 space-separated fields)
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        logger.error(f"Invalid cron expression (expected 5 fields): {cron_expression}")
        return False

    schedule_name = f"google_drive_sync_{tenant_id}"
    entry = {
        "task": "tasks.google_drive_sync_task",
        "cron": cron_expression,
        "kwargs": {
            "tenant_id": tenant_id,
            "google_drive_folder_id": google_drive_folder_id,
            "excel_output_path": excel_output_path,
            "invoice_type": invoice_type,
            "model_config": None,
        },
        "options": {
            "queue": "default",
            "priority": 10,
        },
        "registered_at": datetime.utcnow().isoformat(),
    }

    registry_path = os.path.join(backend_dir, "data", "beat_schedules.json")
    try:
        if os.path.exists(registry_path):
            with open(registry_path, encoding="utf-8") as f:
                registry = json.load(f)
        else:
            registry = {}

        registry[schedule_name] = entry

        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Schedule '{schedule_name}' written to {registry_path}")
        logger.info(f"  Cron: {cron_expression}  |  Invoice type: {invoice_type}")
        logger.info("")
        logger.info("Restart celery beat for the schedule to take effect:")
        logger.info("  celery -A celery_app beat --loglevel=info")
        logger.info("")
        logger.info("To trigger an immediate on-demand sync:")
        logger.info(
            f"  python -c \"from celery_app import google_drive_sync_task; "
            f"google_drive_sync_task.delay('{tenant_id}', '{google_drive_folder_id}', "
            f"'{excel_output_path}', '{invoice_type}')\""
        )
        return True

    except Exception as e:
        logger.error(f"Error writing beat schedule to registry: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Set up Google Drive auto-sync for a tenant")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--google-drive-folder-id", required=True, help="Google Drive folder ID")
    parser.add_argument("--excel-output-path", required=True, help="Path for output Excel file")
    parser.add_argument("--invoice-type", default="both", choices=["sales", "purchase", "both"])
    parser.add_argument("--schedule", default="0 0 1 * *", help="Cron expression for schedule")
    parser.add_argument("--test-only", action="store_true", help="Only verify setup, don't configure schedule")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Google Drive Auto-Sync Setup")
    logger.info("=" * 60)

    # Initialize database
    init_database()

    # Verify tenant
    if not verify_tenant(args.tenant_id):
        logger.error("Setup failed: Tenant not found")
        return 1

    # Verify Google Drive access
    if not verify_google_drive_access(args.google_drive_folder_id):
        logger.error("Setup failed: Cannot access Google Drive folder")
        return 1

    if args.test_only:
        logger.info("✓ All checks passed! Setup is ready.")
        return 0

    # Set up Celery Beat
    if not setup_celery_beat(
        args.tenant_id,
        args.google_drive_folder_id,
        args.excel_output_path,
        args.invoice_type,
        args.schedule
    ):
        logger.error("Setup failed: Could not configure Celery Beat")
        return 1

    logger.info("=" * 60)
    logger.info("✓ Setup completed successfully!")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
