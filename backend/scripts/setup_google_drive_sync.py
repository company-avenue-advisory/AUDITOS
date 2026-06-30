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
    Set up Celery Beat schedule for periodic sync.

    Args:
        cron_expression: Standard 5-field cron expression
                        Default: "0 0 1 * *" (monthly on 1st at 00:00 UTC)
    """
    logger.info("Setting up Celery Beat schedule...")

    try:
        # Import Celery and beat scheduler
        from celery import schedule
        from celery_app import celery_app

        # Parse cron expression
        from croniter import croniter
        if not croniter.is_valid(cron_expression):
            logger.error(f"Invalid cron expression: {cron_expression}")
            return False

        task_name = f"google_drive_sync_{tenant_id}"

        # Add to Celery beat schedule
        # This requires modifying celerybeat schedule (file or database)
        # For now, we'll log the configuration

        schedule_config = {
            "task": "tasks.google_drive_sync_task",
            "schedule": cron_expression,
            "args": [],
            "kwargs": {
                "tenant_id": tenant_id,
                "google_drive_folder_id": google_drive_folder_id,
                "excel_output_path": excel_output_path,
                "invoice_type": invoice_type,
                "model_config": None
            },
            "options": {
                "queue": "default",
                "priority": 10
            }
        }

        logger.info("Celery Beat schedule configuration:")
        logger.info(json.dumps(schedule_config, indent=2))

        logger.info("""
To enable this schedule, add to your celerybeat configuration file or database:

Option 1: Add to celerybeat-schedule (file-based):
  {
    "google_drive_sync_tenant_%s": %s
  }

Option 2: Use celery-beat-scheduler or similar tool to register the schedule.

Option 3: For development, manually trigger with:
  python -c "from celery_app import google_drive_sync_task; google_drive_sync_task.delay('%s', '%s', '%s', '%s')"
        """ % (tenant_id, json.dumps(schedule_config, indent=2), tenant_id, google_drive_folder_id, excel_output_path, invoice_type))

        return True

    except Exception as e:
        logger.error(f"Error setting up Celery Beat: {e}")
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
