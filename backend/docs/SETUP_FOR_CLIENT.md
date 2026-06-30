# Setup Guide: Client Invoice Folder

**Client Folder:** https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq  
**Folder ID:** `1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq`

This guide walks you through setting up auto-sync for this specific client folder.

---

## Prerequisites

- ✅ Google Cloud Project created
- ✅ Service Account created with Google Drive API access
- ✅ Service Account JSON key downloaded
- ✅ Service account **shared on the folder** (with Viewer access)
- ✅ Python 3.9+ installed
- ✅ Git clone of this repo
- ✅ Redis running (for Celery)

---

## Step 1: Set Environment Variables

**Windows (PowerShell):**

```powershell
# Set environment variable
$env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\service-account-key.json"

# Or add to .env file in backend directory
# GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=C:\path\to\service-account-key.json
```

**macOS/Linux (Bash):**

```bash
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/service-account-key.json

# Or add to .env file
# GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/service-account-key.json
```

**Verify it's set:**

```bash
# Windows
echo $env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON

# macOS/Linux
echo $GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
```

---

## Step 2: Run Quick Setup Script

Navigate to the `backend` directory:

```bash
cd backend
```

### On Windows:

```powershell
.\scripts\quick_setup.ps1 my_tenant_id
```

### On macOS/Linux:

```bash
bash scripts/quick_setup.sh my_tenant_id
```

**What the script does:**
1. ✅ Checks environment variables
2. ✅ Installs Python dependencies
3. ✅ Initializes database tables
4. ✅ Tests Google Drive connection
5. ✅ Initializes file tracking

**Expected output:**
```
✅ GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is set
✅ Dependencies installed
✅ Database tables created
✅ Google Drive connected - found 12 PDF files
✅ File tracker initialized

✅ Setup Complete!
```

If you see ❌ errors, check:
- Service account JSON path is correct
- Service account has access to the folder
- Redis is running (for Celery)

---

## Step 3: Test the Sync

### Quick Test (Manual Trigger)

```bash
python -c "
from celery_app import google_drive_sync_task
from database import SessionLocal

# Folder ID: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
result = google_drive_sync_task.delay(
    tenant_id='my_tenant_id',
    google_drive_folder_id='1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq',
    excel_output_path='/data/client_invoices.xlsx',
    invoice_type='both'
)
print(f'✅ Sync started: {result.id}')
"
```

### Check Status

```bash
# Get task ID from above output, then:
curl -s http://localhost:8000/api/google-drive-sync/status/TASK_ID | python -m json.tool
```

Expected response:
```json
{
  "task_id": "abc-123",
  "status": "SUCCESS",
  "result": {
    "sync_job_id": "...",
    "status": "completed",
    "total_files_found": 12,
    "new_files": 3,
    "updated_files": 0,
    "processed_files": 3,
    "failed_files": 0,
    "excel_output_path": "/data/client_invoices.xlsx",
    "duration_seconds": 127.45
  }
}
```

### View Output Excel

```bash
# Check if file exists
ls -lh /data/client_invoices.xlsx

# Open in Excel/Sheets to view extracted invoices
```

---

## Step 4: Schedule Monthly Sync (Production)

### Option A: CRON (Polls monthly)

**File:** `celerybeat-schedule.json`

```json
{
  "google_drive_sync_client": {
    "task": "tasks.google_drive_sync_task",
    "schedule": {
      "minute": "0",
      "hour": "0",
      "day_of_month": "1",
      "month_of_year": "*"
    },
    "args": [],
    "kwargs": {
      "tenant_id": "my_tenant_id",
      "google_drive_folder_id": "1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq",
      "excel_output_path": "/data/client_invoices.xlsx",
      "invoice_type": "both",
      "model_config": null
    }
  }
}
```

**Start Celery Beat:**

```bash
celery -A celery_app beat --loglevel=info
```

Sync will run automatically on the 1st of each month at 00:00 UTC.

### Option B: Webhooks (Real-time)

See [GOOGLE_DRIVE_ADVANCED.md](GOOGLE_DRIVE_ADVANCED.md#2-real-time-webhooks) for webhook setup.

---

## Step 5: Monitor Sync

### View Sync History

```bash
# Check database for sync history
sqlite3 audit.db "
SELECT 
  id, 
  sync_timestamp, 
  total_files_found,
  new_files,
  processed_files,
  failed_files,
  status
FROM google_drive_sync_jobs
WHERE tenant_id = 'my_tenant_id'
ORDER BY sync_timestamp DESC
LIMIT 10;
"
```

### Check Failed Files

```bash
sqlite3 audit.db "
SELECT 
  google_drive_id,
  filename,
  error_message,
  updated_at
FROM google_drive_file_tracker
WHERE processing_status = 'failed'
AND tenant_id = 'my_tenant_id';
"
```

### API Endpoint: Sync History

```bash
curl -s -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/google-drive-sync/history | python -m json.tool
```

---

## Configuration Reference

### Environment Variables

```bash
# Required
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json

# Optional (defaults shown)
GOOGLE_DRIVE_INVOICE_TYPE=both              # sales | purchase | both
GOOGLE_DRIVE_EXCEL_OUTPUT_PATH=/data/output.xlsx
GOOGLE_DRIVE_WEBHOOK_URL=                   # For webhooks (optional)
```

### Database Tables

```sql
-- File processing history
SELECT * FROM google_drive_file_tracker 
WHERE tenant_id = 'my_tenant_id';

-- Sync job audit log
SELECT * FROM google_drive_sync_jobs 
WHERE tenant_id = 'my_tenant_id'
ORDER BY sync_timestamp DESC;

-- Webhook channels (if using webhooks)
SELECT * FROM google_drive_webhook_channels 
WHERE tenant_id = 'my_tenant_id';
```

---

## Troubleshooting

### "Google Drive connection failed"

```
Error: Credentials are not available
```

**Solution:**
1. Check file path: `echo $GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
2. Verify file exists: `ls -la /path/to/key.json`
3. Verify JSON is valid: `python -m json.tool /path/to/key.json`
4. Verify service account is shared on folder (see Prerequisites)

### "No PDF files found"

```
✅ Google Drive connected - found 0 PDF files
```

**Possible causes:**
- Folder ID is incorrect
- Folder contains no PDFs
- Service account doesn't have read access

**Solution:**
- Verify folder ID: https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
- Upload a test PDF to the folder
- Re-share folder with service account (Viewer role)

### "Extraction failed"

```
processing_status = 'failed'
error_message = '...'
```

**Possible causes:**
- PDF is not a valid invoice
- File is corrupted
- LLM extraction timeout
- Model not available

**Solution:**
1. Check the original PDF (may not be an invoice)
2. Check model availability: `echo $OLLAMA_MODEL_NAME`
3. Check logs: `celery -A celery_app worker --loglevel=debug`

### "Excel file locked/inaccessible"

```
Error: Could not acquire lock after 30s
```

**Solution:**
- Check if another process is using it: `lsof /data/client_invoices.xlsx`
- Remove stale lock: `rm /data/client_invoices.xlsx.lock`
- Increase timeout in code: `ExcelFileLock(path, timeout=60)`

---

## Next Steps

1. ✅ Setup complete — sync is running
2. ✅ Monitor via database or API
3. ✅ Configure webhook (optional, for real-time sync)
4. ✅ Set up alerts (optional, via Sentry/monitoring)

---

## Support

**Issues?** Check:
- [GOOGLE_DRIVE_SYNC_QUICKSTART.md](GOOGLE_DRIVE_SYNC_QUICKSTART.md)
- [GOOGLE_DRIVE_SYNC_SETUP.md](GOOGLE_DRIVE_SYNC_SETUP.md)
- [GOOGLE_DRIVE_ADVANCED.md](GOOGLE_DRIVE_ADVANCED.md)

**Code reference:**
- `services/google_drive.py` — Drive connector
- `services/google_drive_sync.py` — Main pipeline
- `services/excel_sync.py` — Excel output
- `celery_app.py` — Task definition
- `main.py` — API endpoints (lines 1400+)

---

## Folder Details

```
Folder ID: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
Folder URL: https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
Access: Service account (read-only)
Sync: Monthly (1st at 00:00 UTC) or on-demand via API
Output: /data/client_invoices.xlsx
```

---

**Ready to sync!** 🚀
