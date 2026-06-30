#!/bin/bash
set -e

# Quick Setup Script for Google Drive Auto-Sync
# Usage: bash scripts/quick_setup.sh

echo "=========================================="
echo "Google Drive Auto-Sync Setup"
echo "=========================================="
echo ""

# Folder ID (provided by user)
FOLDER_ID="1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq"
TENANT_ID="${1:-default_tenant}"  # Use arg or default
EXCEL_OUTPUT="/data/invoices_output.xlsx"

echo "📁 Google Drive Folder: $FOLDER_ID"
echo "👤 Tenant ID: $TENANT_ID"
echo "📊 Excel Output: $EXCEL_OUTPUT"
echo ""

# Step 1: Check environment
echo "Step 1: Checking environment..."
if [ -z "$GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON" ]; then
    echo "❌ GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set"
    echo ""
    echo "Set it with:"
    echo "  export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json"
    echo ""
    exit 1
fi
echo "✅ GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is set"

# Step 2: Install dependencies
echo ""
echo "Step 2: Installing dependencies..."
pip install -q google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 openpyxl
echo "✅ Dependencies installed"

# Step 3: Initialize database
echo ""
echo "Step 3: Initializing database..."
cd "$(dirname "$0")/.."
python -c "from database import engine, Base; Base.metadata.create_all(bind=engine); print('✅ Database tables created')"

# Step 4: Test Google Drive connection
echo ""
echo "Step 4: Testing Google Drive connection..."
python -c "
from services.google_drive import GoogleDriveConnector
try:
    drive = GoogleDriveConnector('$FOLDER_ID')
    files = drive.list_files(file_types=['application/pdf'])
    print(f'✅ Google Drive connected - found {len(files)} PDF files')
except Exception as e:
    print(f'❌ Error: {e}')
    exit(1)
"

# Step 5: Test database tracking
echo ""
echo "Step 5: Initializing file tracker..."
python -c "
from database import SessionLocal
from models import GoogleDriveFileTracker
from services.google_drive import GoogleDriveFileTracker as Tracker

db = SessionLocal()
tracker = Tracker(db)
print('✅ File tracker initialized')
db.close()
"

# Step 6: Show next steps
echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1️⃣  Run a test sync:"
echo "    python -c \"from celery_app import google_drive_sync_task; result = google_drive_sync_task.delay('$TENANT_ID', '$FOLDER_ID', '$EXCEL_OUTPUT', 'both'); print(f'Task: {result.id}')\""
echo ""
echo "2️⃣  Check sync status:"
echo "    curl http://localhost:8000/api/google-drive-sync/status/TASK_ID"
echo ""
echo "3️⃣  View sync history:"
echo "    sqlite3 audit.db \"SELECT id, sync_timestamp, processed_files FROM google_drive_sync_jobs LIMIT 5;\""
echo ""
echo "4️⃣  Schedule monthly sync (add to celerybeat-schedule.json):"
echo "    {\"google_drive_sync_$TENANT_ID\": {\"task\": \"tasks.google_drive_sync_task\", \"schedule\": {\"minute\": \"0\", \"hour\": \"0\", \"day_of_month\": \"1\"}, \"kwargs\": {\"tenant_id\": \"$TENANT_ID\", \"google_drive_folder_id\": \"$FOLDER_ID\", \"excel_output_path\": \"$EXCEL_OUTPUT\", \"invoice_type\": \"both\"}}}"
echo ""
echo "5️⃣  Start Celery worker:"
echo "    celery -A celery_app worker --loglevel=info"
echo ""
