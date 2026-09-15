"""
Migration: Add celery_task_id column to google_drive_sync_jobs table.

Run once on the DigitalOcean server after deploying the code update:
    python scripts/migrate_add_celery_task_id.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from database import engine

SQL = text("ALTER TABLE google_drive_sync_jobs ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR")

if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(SQL)
        conn.commit()
        print("Migration complete: celery_task_id column added to google_drive_sync_jobs.")
