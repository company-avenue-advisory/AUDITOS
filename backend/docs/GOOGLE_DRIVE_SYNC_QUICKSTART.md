# Google Drive Auto-Sync — Quick Start (5 min)

## TL;DR

Auto-sync invoices from Google Drive → Extract → Update Excel monthly.

## Setup (one-time)

### 1. Create Google Service Account (3 min)

```bash
# Go to: https://console.cloud.google.com/
# Create new project or select existing

# Enable Google Drive API
# Search for "Google Drive API" → Click "Enable"

# Create Service Account
# Go to Service Accounts → Create → Name: "audit-os-sync"
# Grant roles (none needed, will add folder permissions manually)

# Create JSON Key
# Go to Keys tab → Add Key → JSON → Download key.json
```

### 2. Share Folder with Service Account (1 min)

```bash
# Copy service account email from key.json
# (looks like: audit-os-sync@my-project.iam.gserviceaccount.com)

# Open Google Drive folder → Share → Paste email → "Viewer" → Share

# Copy folder ID from URL
# https://drive.google.com/drive/folders/FOLDER_ID_HERE ← this part
```

### 3. Set Environment Variable (1 min)

```bash
# Add to .env file:
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json

# Or inline (for Docker):
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"...","..."}'
```

## Test It (1 min)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Initialize database (if not done)
python -c "from database import engine, Base; Base.metadata.create_all(bind=engine)"

# Test connection
python scripts/setup_google_drive_sync.py \
  --tenant-id YOUR_TENANT_ID \
  --google-drive-folder-id FOLDER_ID \
  --excel-output-path /data/output.xlsx \
  --invoice-type both \
  --test-only

# Should print:
# ✓ Tenant found: ...
# ✓ Google Drive access verified. Found X PDF files.
# ✓ All checks passed! Setup is ready.
```

## Run Sync

### Option A: Manual (for testing)

```bash
# API endpoint (if server running)
curl -X POST http://localhost:8000/api/google-drive-sync/trigger \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "google_drive_folder_id": "FOLDER_ID",
    "excel_output_path": "/data/output.xlsx",
    "invoice_type": "both"
  }'

# Or via Python
python -c "
from celery_app import google_drive_sync_task
result = google_drive_sync_task.delay(
    tenant_id='TENANT_ID',
    google_drive_folder_id='FOLDER_ID',
    excel_output_path='/data/output.xlsx',
    invoice_type='both'
)
print('Task:', result.id)
"
```

### Option B: Scheduled (production)

```bash
# Start Celery worker
celery -A celery_app worker --loglevel=info

# In another terminal, start Celery Beat (scheduler)
celery -A celery_app beat --loglevel=info

# Configure schedule in celerybeat-schedule.json:
{
  "google_drive_sync_tenant_ABC": {
    "task": "tasks.google_drive_sync_task",
    "schedule": {
      "minute": "0",
      "hour": "0",
      "day_of_month": "1",
      "month_of_year": "*"
    },
    "args": [],
    "kwargs": {
      "tenant_id": "TENANT_ID",
      "google_drive_folder_id": "FOLDER_ID",
      "excel_output_path": "/data/output.xlsx",
      "invoice_type": "both",
      "model_config": null
    }
  }
}
```

## Monitor

```bash
# Check sync history
sqlite3 audit.db "SELECT id, sync_timestamp, processed_files, failed_files, status FROM google_drive_sync_jobs LIMIT 5;"

# Check failed files
sqlite3 audit.db "SELECT filename, error_message FROM google_drive_file_tracker WHERE processing_status = 'failed';"

# Get task status
curl http://localhost:8000/api/google-drive-sync/status/TASK_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Output

```
/data/output_sales.xlsx
├─ Headers: Voucher Date | Invoice No | ... | Source File
└─ Rows: Continuously appended

/data/output_purchase.xlsx
├─ Headers: Voucher Date | Invoice No | ... | Source File
└─ Rows: Continuously appended
```

## Troubleshooting

```bash
# "Google Drive access failed"
→ Check service account email is shared on folder
→ Re-download JSON key from Google Cloud Console

# "No files found"
→ Verify folder ID in URL: drive.google.com/drive/folders/FOLDER_ID
→ Verify folder contains PDFs
→ Verify service account has read access

# "Extraction failed"
→ Check invoice_tasks table: SELECT * FROM invoice_tasks WHERE status = 'FAILED';
→ May be: invalid PDF, not an invoice, extraction timeout

# Celery not working
→ Check Redis/broker: redis-cli ping
→ Check logs: celery -A celery_app worker --loglevel=debug
```

## Files

| File | Purpose |
|------|---------|
| `services/google_drive.py` | Drive API connector |
| `services/google_drive_sync.py` | Main pipeline orchestrator |
| `services/excel_sync.py` | Excel append service |
| `celery_app.py` | Celery task definition |
| `main.py` | API endpoints |
| `models.py` | Database models (GoogleDriveFileTracker, GoogleDriveSyncJob) |
| `docs/GOOGLE_DRIVE_SYNC_SETUP.md` | Full setup guide |
| `scripts/setup_google_drive_sync.py` | Setup verification script |

## Next

- Full guide: [GOOGLE_DRIVE_SYNC_SETUP.md](GOOGLE_DRIVE_SYNC_SETUP.md)
- Implementation details: [GOOGLE_DRIVE_SYNC_IMPLEMENTATION.md](GOOGLE_DRIVE_SYNC_IMPLEMENTATION.md)

---

**Ready to sync?** Run the test command above. If it passes, you're good to go!
