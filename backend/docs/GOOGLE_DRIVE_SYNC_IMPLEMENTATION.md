# Google Drive Auto-Sync Implementation Summary

## Overview

A complete **Google Drive → Extraction Pipeline → Excel** auto-sync system that continuously monitors a client's Google Drive folder, processes new/updated invoices, and maintains a live Excel workbook with all extracted data.

**Key Features:**
- ✅ Monthly scheduled sync (configurable cron)
- ✅ Smart deduplication using Google Drive file ID + MD5 checksum
- ✅ PDF-only filtering (ignores other file types)
- ✅ Reuses existing extraction pipeline (LLM-powered)
- ✅ Continuous Excel append (no overwrites, preserves history)
- ✅ Audit trail in database (GoogleDriveSyncJob + GoogleDriveFileTracker)
- ✅ API endpoints for manual triggering and monitoring
- ✅ Service account based (no OAuth flow needed)

## Architecture

```
Client's Google Drive Folder
        ↓
Google Drive API (service account)
        ↓
List Files (PDF only)
        ↓
Dedup Check (id + md5Checksum)
        ├─ Already processed → Skip
        ├─ New file → Process
        └─ Updated (md5 changed) → Re-process
        ↓
Download File
        ↓
Existing Invoice Extraction Pipeline
        ├─ process_pdf()
        ├─ LLM extraction (Gemini/Claude/Groq)
        ├─ Save to DB (SalesLineItem + PurchaseLineItem)
        └─ Observability logging
        ↓
Append to Excel (per invoice type)
        ├─ _sales.xlsx (if invoice_type includes sales)
        └─ _purchase.xlsx (if invoice_type includes purchase)
        ↓
Update Tracker (mark as completed)
        ↓
Update Sync Job (statistics)
```

## Files Created

### 1. **Database Models** (`backend/models.py`)

```python
class GoogleDriveFileTracker:
    """Track processed files to prevent re-processing."""
    google_drive_id       # Immutable Drive file ID
    md5_checksum          # File content hash
    modified_time         # When file was last modified in Drive
    processing_status     # pending | processing | completed | failed
    task_id               # Link to extraction result
    excel_row_id          # Which row in Excel

class GoogleDriveSyncJob:
    """Audit log for each monthly sync."""
    sync_timestamp        # When the sync ran
    total_files_found     # Total PDFs in folder
    new_files             # New files since last sync
    updated_files         # Files with changed content
    processed_files       # Successfully processed
    failed_files          # Extraction failed
    status                # in_progress | completed | failed
```

### 2. **Google Drive Connector** (`backend/services/google_drive.py`)

Service account based connector with two classes:

```python
class GoogleDriveConnector:
    """
    Authenticate and interact with Google Drive.
    
    Methods:
      - list_files()         # Get files from folder
      - download_file()      # Download to disk
      - get_file_metadata()  # Check if file changed
    """

class GoogleDriveFileTracker:
    """
    Database-backed dedup tracker.
    
    Methods:
      - is_file_processed()     # Check if seen before
      - mark_as_processing()    # Mark as in-flight
      - mark_as_completed()     # Save task + row ID
      - mark_as_failed()        # Log error
    """
```

Key logic: **Only process if file is new OR md5Checksum changed**

### 3. **Excel Sync Service** (`backend/services/excel_sync.py`)

```python
class ExcelSyncService:
    """
    Append extraction results to Excel workbook.
    
    Methods:
      - append_sales_item()   # Add one row
      - append_purchase_item() # Add one row
      - append_batch()        # Add multiple rows efficiently
    """
```

Features:
- Auto-creates Excel with headers if doesn't exist
- Appends new rows (never overwrites)
- Tracks "Processed Date" and "Source File"
- Handles both sales and purchase invoices

### 4. **Main Orchestrator** (`backend/services/google_drive_sync.py`)

```python
class GoogleDriveSyncPipeline:
    """
    Full workflow orchestration.
    
    Flow:
      1. List files from Drive
      2. Filter PDFs
      3. Check dedup
      4. Download new/changed files
      5. Process through extraction pipeline
      6. Append to Excel
      7. Update database
    """
```

Returns summary:
```json
{
  "sync_job_id": "...",
  "status": "completed",
  "total_files_found": 20,
  "new_files": 5,
  "updated_files": 2,
  "processed_files": 7,
  "failed_files": 0,
  "excel_output_path": "/data/output.xlsx",
  "duration_seconds": 127.45
}
```

### 5. **Celery Task** (`backend/celery_app.py`)

```python
@celery_app.task(name="tasks.google_drive_sync_task")
def google_drive_sync_task(
    tenant_id: str,
    google_drive_folder_id: str,
    excel_output_path: str,
    invoice_type: str = "both",
    model_config: dict = None
) -> dict:
    """Async task for scheduled monthly sync."""
```

Can be triggered:
- **Scheduled**: Via Celery Beat (cron expression)
- **On-demand**: Via API endpoint
- **Manual**: Via CLI command

### 6. **API Endpoints** (`backend/main.py`)

#### POST `/api/google-drive-sync/trigger`
Manually start a sync job.

```json
{
  "google_drive_folder_id": "1Hk5L9mPqRsT2U",
  "excel_output_path": "/data/invoices_output.xlsx",
  "invoice_type": "both",
  "model_config": null
}
```

Returns:
```json
{
  "status": "sync_started",
  "task_id": "abc-123-def",
  "tenant_id": "xyz",
  "message": "Check status with /api/google-drive-sync/status/{task_id}"
}
```

#### GET `/api/google-drive-sync/status/{task_id}`
Check sync progress.

```json
{
  "task_id": "abc-123-def",
  "status": "SUCCESS",
  "result": {
    "sync_job_id": "...",
    "processed_files": 7,
    "failed_files": 0
  }
}
```

#### GET `/api/google-drive-sync/history`
Get sync history for tenant.

```json
{
  "tenant_id": "xyz",
  "sync_jobs": [
    {
      "id": "sync-job-1",
      "sync_timestamp": "2026-06-30T12:00:00",
      "total_files_found": 20,
      "processed_files": 15,
      "failed_files": 0,
      "status": "completed"
    }
  ]
}
```

### 7. **Setup Script** (`backend/scripts/setup_google_drive_sync.py`)

```bash
python setup_google_drive_sync.py \
  --tenant-id abc123 \
  --google-drive-folder-id 1Hk5L9mPqRsT2U \
  --excel-output-path /data/output.xlsx \
  --invoice-type both \
  --schedule "0 0 1 * *"
```

Verifies:
- Tenant exists
- Google Drive credentials work
- Folder is accessible
- Generates schedule config

### 8. **Documentation** (`backend/docs/GOOGLE_DRIVE_SYNC_SETUP.md`)

Complete setup guide:
1. Create Google Cloud service account
2. Share folder with service account
3. Configure environment variables
4. Install dependencies
5. Test connection
6. Configure Celery Beat
7. Monitor via database

## Deduplication Strategy

**Problem**: Prevent re-processing the same file

**Solution**: Track Google Drive file ID + MD5 checksum

```python
For each file in Drive:
  google_drive_id = file['id']        # Immutable, unique per file
  md5_checksum = file['md5Checksum']  # Hash of file content

  existing = db.query().filter(google_drive_id=...).first()
  
  if not existing:
    # NEW FILE → process
    
  elif existing.md5_checksum != md5_checksum:
    # FILE UPDATED → re-process
    
  else:
    # SAME FILE → skip
```

**Why this works:**
- `google_drive_id` is immutable (even if file is renamed)
- `md5Checksum` changes only if file content changes
- Much more reliable than filename-based dedup

## Data Flow Example

```
Monday, June 30, 2026:
  Client has 20 invoices in Drive
  Monthly sync scheduled at 00:00 UTC
  
  GoogleDriveSyncPipeline.run() executes:
  
  1. Drive API lists 20 files (PDFs)
  2. Check dedup:
     ✓ Files 1-15: already processed in previous months
     ✓ Files 16-18: new (not in tracker)
     ✓ Files 19-20: updated (md5 changed since last month)
  
  3. Download files 16-20 (5 files total)
  
  4. Extract via existing pipeline:
     - File 16 → 3 sales items (successful)
     - File 17 → 0 items (no invoices, extraction error)
     - File 18 → 2 purchase items (successful)
     - File 19 → 5 sales items (re-processed)
     - File 20 → 0 items (extraction error)
  
  5. Append to Excel:
     - sales_output.xlsx: appends rows for files 16, 19
     - purchase_output.xlsx: appends rows for file 18
  
  6. Update database:
     - GoogleDriveFileTracker: 3 completed + 2 failed
     - GoogleDriveSyncJob: total=20, new=3, updated=2, processed=5, failed=2
```

## Output Files

```
/data/invoices_output_sales.xlsx
├─ Headers (row 1): Voucher Date | Invoice No | Party GSTIN | ... | Source File
├─ 2024-01-15 | INV-001 | 05ABCDE... | ... | invoice_january.pdf
├─ 2024-01-20 | INV-002 | 05FGHIJ... | ... | invoice_january.pdf
├─ 2024-02-05 | INV-003 | 05KLMNO... | ... | invoice_february.pdf
├─ ... (existing from previous syncs)
└─ 2024-06-28 | INV-045 | 05PQRST... | ... | invoice_june_updated.pdf  ← NEW from re-process

/data/invoices_output_purchase.xlsx
├─ Headers (row 1): Voucher Date | Invoice No | Party GSTIN | ... | Source File
└─ [rows appended monthly]
```

## Database Audit Trail

```sql
-- See all sync jobs for a tenant
SELECT * FROM google_drive_sync_jobs
WHERE tenant_id = 'abc123'
ORDER BY sync_timestamp DESC;

-- See file processing history
SELECT google_drive_id, filename, processing_status, processed_at, error_message
FROM google_drive_file_tracker
WHERE tenant_id = 'abc123'
ORDER BY processed_at DESC;

-- Find failed files
SELECT google_drive_id, filename, error_message
FROM google_drive_file_tracker
WHERE processing_status = 'failed'
AND tenant_id = 'abc123';
```

## Scheduling Options

### Option 1: Monthly at 00:00 UTC on 1st
```
Cron: 0 0 1 * *
```

### Option 2: Weekly on Monday
```
Cron: 0 0 * * 1
```

### Option 3: Daily
```
Cron: 0 0 * * *
```

### Option 4: On-demand via API
```bash
curl -X POST http://localhost:8000/api/google-drive-sync/trigger \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "google_drive_folder_id": "1Hk5L9mPqRsT2U",
    "excel_output_path": "/data/output.xlsx",
    "invoice_type": "both"
  }'
```

## Performance Metrics

For a typical monthly sync:

```
Scenario: 100 new invoices, 50 updated invoices
        150 total files to process

Timing:
  List Drive files          : ~5 seconds
  Dedup check              : ~2 seconds
  Download 150 files       : ~20 seconds
  Extract via pipeline     : ~3 minutes (limited by LLM rate limit)
  Append to Excel          : ~10 seconds
  Update database          : ~2 seconds
  
  TOTAL                    : ~3.5 minutes

Excel size growth:
  Per file with 5 items    : ~2-3 KB
  Per month (100 files)    : ~200-300 KB
  Annual                   : ~2.4-3.6 MB
```

## Error Handling

**Graceful degradation:**

```python
try:
  process_file(f)
except Exception as e:
  # Mark as failed but continue with next file
  file_tracker.mark_as_failed(file_id, str(e))
  sync_job.failed_files += 1
  continue
```

**Monitoring:**
- Check `GoogleDriveFileTracker.processing_status = 'failed'`
- Check `GoogleDriveSyncJob.error_message` for job-level failures
- Celery task retries after 5 minutes on critical failure

## Integration with Existing System

This implementation seamlessly integrates:

✅ Uses existing `process_pdf()` extraction function
✅ Stores results in existing `SalesLineItem` + `PurchaseLineItem` tables
✅ Links to existing `InvoiceTask` + `BatchJob` models
✅ Respects existing Celery + Redis setup
✅ Follows existing observability logging pattern
✅ Respects existing tenant + user multi-tenancy

## Next Steps

1. **Setup** (20 min)
   - Create Google Cloud service account
   - Share folder with service account
   - Set environment variables

2. **Test** (5 min)
   - Run setup verification script
   - Trigger sync via API endpoint
   - Check Excel output

3. **Schedule** (5 min)
   - Configure Celery Beat cron
   - Start Celery Beat worker
   - Monitor via database

4. **Monitor** (ongoing)
   - Check `GoogleDriveSyncJob` table monthly
   - Review failed files in `GoogleDriveFileTracker`
   - Monitor API endpoints for real-time status

## Security Checklist

- [ ] Service account JSON key is not in git
- [ ] Service account JSON path is in `.env` or environment
- [ ] Only share Drive folder with service account email (not humans)
- [ ] Excel output path has restricted file permissions
- [ ] Celery worker is not exposed to internet
- [ ] Database credentials are secured
- [ ] Audit logs are retained per CGST Act requirements

## Troubleshooting Quick Reference

| Problem | Solution |
|---------|----------|
| "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set" | Export in `.env` or set environment variable |
| "Failed to authenticate" | Verify JSON key is valid, re-download from Google Cloud |
| "No files found in folder" | Verify folder ID, verify service account has read access |
| "Extraction failed" | Check `InvoiceTask.error_message` in database |
| "Excel not updated" | Verify path is writable, check `GoogleDriveSyncJob.status` |
| "Task stuck in PROGRESS" | Check Celery worker logs, verify rate limits |

## Code Examples

### Manual Sync via Python
```python
from services.google_drive_sync import GoogleDriveSyncPipeline

pipeline = GoogleDriveSyncPipeline(
    tenant_id="abc123",
    google_drive_folder_id="1Hk5L9mPqRsT2U",
    excel_output_path="/data/output.xlsx",
    invoice_type="both"
)

result = pipeline.run()
print(f"Processed {result['processed_files']} files")
```

### Via Celery
```python
from celery_app import google_drive_sync_task

task = google_drive_sync_task.delay(
    tenant_id="abc123",
    google_drive_folder_id="1Hk5L9mPqRsT2U",
    excel_output_path="/data/output.xlsx",
    invoice_type="both"
)
print(f"Task ID: {task.id}")
print(f"Status: {task.status}")
result = task.get()  # Wait for completion
```

### Via REST API
```bash
curl -X POST http://localhost:8000/api/google-drive-sync/trigger \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "google_drive_folder_id": "1Hk5L9mPqRsT2U",
    "excel_output_path": "/data/output.xlsx",
    "invoice_type": "both"
  }'
```

---

**Questions?** Check [GOOGLE_DRIVE_SYNC_SETUP.md](GOOGLE_DRIVE_SYNC_SETUP.md) for detailed setup guide.
