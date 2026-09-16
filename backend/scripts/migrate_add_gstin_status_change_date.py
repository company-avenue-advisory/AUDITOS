"""
Migration: Add status_change_date column to gstin_registry table.

Run once on the server after deploying the code update:
    python scripts/migrate_add_gstin_status_change_date.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from database import engine

SQL = text("ALTER TABLE gstin_registry ADD COLUMN IF NOT EXISTS status_change_date VARCHAR")

if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(SQL)
        conn.commit()
        print("Migration complete: status_change_date column added to gstin_registry.")
