"""
Migration: Add gstin column to tenants table.

Run once on the DigitalOcean server after deploying the code update:
    python scripts/migrate_add_tenant_gstin.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from database import engine

SQL = text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS gstin VARCHAR")

if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(SQL)
        conn.commit()
        print("Migration complete: gstin column added to tenants.")
