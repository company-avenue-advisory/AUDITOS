# Google Drive Auto-Sync Pipeline

Automatically monitor a client's Google Drive folder for invoices, extract data, and append results to a continuously-updated Excel file.

## Architecture Overview

```
Google Drive (Client Folder)
    ↓ (monthly via Celery Beat)
Google Drive API (service account)
    ↓
File Metadata Check (id + md5Checksum)
    ↓
PDF Filter (application/pdf only)
    ↓
Download Files
    ↓
Existing Invoice Extraction Pipeline
    ↓
Append to Excel (sales & purchase)
    ↓
Excel File (in your system)
```

## Prerequisites

1. **Google Cloud Project** with Google Drive API enabled
2. **Service Account** with access to client's Google Drive folder
3. **Service Account JSON Key** (from Google Cloud Console)
4. **Celery + Redis** (for scheduling)
5. **Database** (PostgreSQL/SQLite) with tables created

## Setup Steps

### Step 1: Create Google Cloud Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable Google Drive API:
   - Search for "Google Drive API"
   - Click "Enable"
4. Create a service account:
   - Go to "Service Accounts"
   - Click "Create Service Account"
   - Name: `audit-os-google-drive-sync`
   - Click "Create and Continue"
5. Create a key:
   - Go to the service account you created
   - Click "Keys" tab
   - Click "Add Key" → "Create new key"
   - Choose "JSON"
   - Download the JSON key file
   - **Save this securely** — you'll need it in Step 3

### Step 2: Share Google Drive Folder with Service Account

1. Copy the service account email (looks like `audit-os@project-id.iam.gserviceaccount.com`)
2. Go to the Google Drive folder containing client invoices
3. Right-click → "Share"
4. Paste the service account email
5. Give "Editor" or "Viewer" access (Viewer is sufficient for read-only)
6. Click "Share"
7. Copy the **folder ID** from the URL:
   - URL format: `https://drive.google.com/drive/folders/FOLDER_ID_HERE`

### Step 3: Configure Environment Variables

Add to your `.env` file:

```bash
# Path to Google Drive service account JSON key (absolute path)
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/your/service-account-key.json

# Or provide the JSON directly as environment variable (useful in Docker)
# GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"...","...":"..."}'
```

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `google-api-python-client>=2.0.0`
- `google-auth>=2.0.0`
- `google-auth-oauthlib>=1.0.0`
- `google-auth-httplib2>=0.2.0`
- `openpyxl` (already in requirements)

### Step 5: Initialize Database

```bash
cd backend
python -c "from database import engine, Base; Base.metadata.create_all(bind=engine)"
```

Or if using migrations:

```bash
alembic upgrade head
```

### Step 6: Test Google Drive Connection

```bash
cd backend
python scripts/setup_google_drive_sync.py \
  --tenant-id <TENANT_UUID> \
  --google-drive-folder-id <FOLDER_ID> \
  --excel-output-path /data/invoices_output.xlsx \
  --invoice-type both \
  --test-only
```

Example output:
```
✓ Tenant found: Sharma Associates
✓ Google Drive access verified. Found 15 PDF files.
✓ All checks passed! Setup is ready.
```

### Step 7: Configure Celery Beat Schedule

#### Option A: File-Based Schedule (Development)

Create/edit `celerybeat-schedule.json`:

```json
{
  "google_drive_sync_tenant_abc123": {
    "task": "tasks.google_drive_sync_task",
    "schedule": {
      "minute": "0",
      "hour": "0",
      "day_of_week": "*",
      "day_of_month": "1",
      "month_of_year": "*"
    },
    "args": [],
    "kwargs": {
      "tenant_id": "abc123",
      "google_drive_folder_id": "1Hk5L9mPqRsT2U",
      "excel_output_path": "/data/invoices_output.xlsx",
      "invoice_type": "both",
      "model_config": null
    }
  }
}
```

Then start Celery Beat:

```bash
celery -A celery_app beat --loglevel=info
```

#### Option B: Programmatic Schedule (Production)

Use a database-backed schedule (django-celery-beat or similar):

```python
from celery_app import celery_app
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'google_drive_sync_tenant_abc123': {
        'task': 'tasks.google_drive_sync_task',
        'schedule': crontab(minute=0, hour=0, day_of_month=1),  # Monthly on 1st at 00:00 UTC
        'args': (),
        'kwargs': {
            'tenant_id': 'abc123',
            'google_drive_folder_id': '1Hk5L9mPqRsT2U',
            'excel_output_path': '/data/invoices_output.xlsx',
            'invoice_type': 'both',
            'model_config': None
        }
    }
}
```

#### Option C: Manual Trigger (Testing)

```bash
cd backend
python -c "
from celery_app import google_drive_sync_task
result = google_drive_sync_task.delay(
    tenant_id='abc123',
    google_drive_folder_id='1Hk5L9mPqRsT2U',
    excel_output_path='/data/invoices_output.xlsx',
    invoice_type='both',
    model_config=None
)
print('Task started:', result.id)
"
```

## File Deduplication Logic

The system uses Google Drive's immutable file metadata to prevent re-processing:

```
For each file in Google Drive:
  1. Check if google_drive_id exists in database
  2. If NEW:
     - Download & process
     - Store in database: id, md5Checksum, modifiedTime
  3. If EXISTS but md5Checksum changed:
     - File was updated in Drive
     - Re-download & re-process
  4. If EXISTS and md5Checksum same:
     - Skip (already processed)
```

This is **more reliable than filename checking** because:
- Clients can rename files
- Files can be updated without renaming
- Google Drive IDs are immutable

## Output Files

The sync pipeline creates two Excel files (or one combined, depending on settings):

```
/data/invoices_output_sales.xlsx
  ├─ Headers: Voucher Date, Invoice No, Party GSTIN, HSN, Taxable Value, CGST, SGST, IGST, Total, ...
  ├─ Row 2: First extracted invoice
  ├─ Row 3: Second extracted invoice
  └─ Row N: Continuously appended as new invoices arrive

/data/invoices_output_purchase.xlsx
  ├─ Headers: [same structure for purchases]
  └─ [appended rows]
```

Each row includes:
- **Processed Date**: When the file was extracted
- **Source File**: Original filename from Google Drive

## Monitoring & Auditing

Check sync history in the database:

```sql
-- Last 10 sync jobs
SELECT id, tenant_id, sync_timestamp, total_files_found, processed_files, failed_files, status
FROM google_drive_sync_jobs
ORDER BY sync_timestamp DESC
LIMIT 10;

-- File processing history
SELECT google_drive_id, filename, processing_status, processed_at, task_id
FROM google_drive_file_tracker
WHERE tenant_id = 'abc123'
ORDER BY processed_at DESC;

-- Failed files
SELECT google_drive_id, filename, error_message
FROM google_drive_file_tracker
WHERE processing_status = 'failed'
AND tenant_id = 'abc123';
```

## Troubleshooting

### "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON environment variable not set"

**Solution**: Set the environment variable before starting the worker:

```bash
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json
celery -A celery_app worker --loglevel=info
```

### "Failed to authenticate with Google Drive"

**Possible causes**:
- JSON key file is invalid or corrupted
- Service account doesn't have access to the folder
- Google Drive API is not enabled in the project

**Solution**:
1. Re-download the JSON key from Google Cloud Console
2. Verify the service account email is shared on the folder
3. Verify Google Drive API is enabled: https://console.cloud.google.com/apis/api/drive.googleapis.com

### "No PDF files found in Google Drive folder"

**Solution**:
1. Verify the folder ID is correct
2. Verify the folder contains PDF files
3. Verify the service account has read access to the folder
4. Manually check: `https://drive.google.com/drive/folders/FOLDER_ID`

### Sync runs but files not appearing in Excel

**Possible causes**:
- Extraction failed (check `invoice_tasks` table for errors)
- PDF not recognized as invoice (check file format)
- Excel file path is incorrect

**Solution**:
```sql
-- Check for failed extractions
SELECT id, file_name, status, error_message
FROM invoice_tasks
WHERE status = 'FAILED'
ORDER BY created_at DESC
LIMIT 10;
```

## Performance Considerations

- **Monthly sync**: Processes only new/changed files
- **Extraction**: Uses existing pipeline (respects rate limits)
- **Excel append**: Efficient batch operation (~1 row per second)
- **Deduplication**: O(1) database lookup per file

For 100 new files per month:
- Expected duration: ~5-10 minutes (limited by LLM extraction rate)
- Excel size growth: ~100KB per file (with all fields)

## Security Notes

1. **Service Account JSON**: Keep the key file secure
   - Don't commit to git
   - Use environment variables in production
   - Rotate keys periodically

2. **Folder Sharing**: Only share with the service account, not humans
   - Use folder permissions, not file permissions
   - Audit who has access regularly

3. **Excel Output**: Ensure the output path is secure
   - Use restricted file permissions
   - Consider encryption at rest

## API Reference

### GoogleDriveSyncPipeline

```python
from services.google_drive_sync import GoogleDriveSyncPipeline

pipeline = GoogleDriveSyncPipeline(
    tenant_id="abc123",
    google_drive_folder_id="1Hk5L9mPqRsT2U",
    excel_output_path="/data/output.xlsx",
    invoice_type="both"  # "sales", "purchase", or "both"
)

result = pipeline.run(model_config={"provider": "gemini-2.5-flash"})
print(result)
# {
#   "sync_job_id": "...",
#   "status": "completed",
#   "total_files_found": 20,
#   "new_files": 5,
#   "updated_files": 2,
#   "processed_files": 7,
#   "failed_files": 0,
#   "excel_output_path": "/data/output.xlsx",
#   "duration_seconds": 127.45
# }
```

### Celery Task

```python
from celery_app import google_drive_sync_task

# Async execution
task = google_drive_sync_task.delay(
    tenant_id="abc123",
    google_drive_folder_id="1Hk5L9mPqRsT2U",
    excel_output_path="/data/output.xlsx",
    invoice_type="both"
)

# Check status
print(task.status)  # "PENDING", "PROGRESS", "SUCCESS", "FAILURE"
result = task.get()  # Wait for result
```

## Next Steps

1. Set up the service account (Steps 1-2)
2. Configure environment (Step 3)
3. Test the connection (Step 6)
4. Schedule the task (Step 7)
5. Monitor via database (Monitoring section)

For help: Check logs with `celery -A celery_app events` or database `google_drive_sync_jobs` table.
