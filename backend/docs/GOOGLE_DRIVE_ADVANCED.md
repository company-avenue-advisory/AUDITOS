# Google Drive Auto-Sync — Advanced Features

Enhanced capabilities for production use:

1. **ZIP File Handling** — Process ZIP archives containing PDFs
2. **Real-Time Webhooks** — Alternative to CRON polling
3. **File Locking** — Safe concurrent Excel writes

---

## 1. ZIP File Handling

### Problem

Clients sometimes upload multiple invoices as a ZIP file instead of individual PDFs. Your pipeline needs to:
- Detect ZIP files automatically
- Extract internal PDFs
- Compute MD5 for each PDF individually
- Prevent re-processing duplicates in ZIPs
- Handle nested ZIPs (ZIP-in-ZIP)

### Solution

```python
from services.google_drive_zip import PDFExtractor

# Extract PDFs from ZIP
zip_data = b"...zip file content..."
pdfs = PDFExtractor.extract_pdfs_from_zip(zip_data, "invoices.zip")

# Returns:
# [
#   {
#     "filename": "invoice_001.pdf",
#     "md5_checksum": "abc123...",
#     "data": <bytes>,
#     "size_bytes": 12345,
#     "nested_in": "invoices.zip"
#   },
#   ...
# ]
```

### Integration with Sync Pipeline

Updated `GoogleDriveSyncPipeline` to handle ZIPs:

```python
# In google_drive_sync.py
for drive_file in drive_files:
    mime_type = drive_file.get("mimeType")

    if mime_type == "application/zip":
        # Download ZIP
        zip_data = download_file(...)

        # Extract PDFs
        pdfs = PDFExtractor.extract_pdfs_from_zip(zip_data, filename)

        # Process each PDF
        for pdf in pdfs:
            # Check if PDF already processed (by MD5)
            if not file_tracker.is_file_processed(pdf["md5_checksum"]):
                # Process this PDF
                process_invoice(pdf["data"], pdf["filename"])

    elif mime_type == "application/pdf":
        # Process single PDF (existing logic)
        process_invoice(...)
```

### Configuration

Supported file types:
```python
FILE_TYPES = [
    "application/pdf",      # Single PDF files
    "application/zip",      # ZIP archives
    "application/x-zip-compressed",  # Alternative ZIP MIME type
]
```

### Limitations

- **Max file size**: 500 MB per ZIP (configurable)
- **Max nesting depth**: 3 levels (prevents zip-bombs)
- **Supported formats**: PDF files only (other file types inside ZIP ignored)

### Example

```
Client uploads: invoices_june.zip
  ├─ invoice_001.pdf (md5: abc123)
  ├─ invoice_002.pdf (md5: def456)
  └─ invoices_subfolder/
      └─ invoice_003.pdf (md5: ghi789)

Sync pipeline:
  1. Download ZIP (50 MB)
  2. Extract 3 PDFs
  3. Compute MD5 for each
  4. Check if any are in tracker
  5. If new: process each
  6. If duplicate: skip
  7. Append to Excel
```

---

## 2. Real-Time Webhooks

### Problem

Monthly CRON polling means:
- 28 days max latency (for invoice processing)
- Missed files if uploaded between scheduled syncs
- Manual triggering required for urgent invoices

### Solution

Use Google Drive **Push Notifications** (webhooks) for real-time detection.

### How It Works

```
Client uploads invoice
        ↓
Google Drive API detects change (< 1 second)
        ↓
Google sends POST to your webhook endpoint
        ↓
Webhook handler fetches file metadata
        ↓
Check dedup (MD5)
        ↓
Process immediately
        ↓
Append to Excel (< 5 minutes total)
```

### Setup

#### 1. Configure Public Webhook URL

Your endpoint must be reachable by Google (HTTPS, public):

```bash
# Option A: Production (your actual domain)
https://myapp.example.com/api/google-drive-webhook

# Option B: Local testing (via ngrok)
ngrok http 8000
# Gives: https://abc123.ngrok.io/api/google-drive-webhook
```

#### 2. Create Watch Channel

```python
from services.google_drive_webhooks import GoogleDriveWatchManager

watch_manager = GoogleDriveWatchManager(
    drive_connector=drive,
    db_session=db
)

channel_id = watch_manager.setup_watch(
    tenant_id="abc123",
    folder_id="1Hk5L9mPqRsT2U",
    webhook_url="https://myapp.example.com/api/google-drive-webhook"
)

# Channel expires in ~1 hour, will auto-renew
```

#### 3. Add Webhook Endpoint

In `main.py`:

```python
from fastapi import Request, BackgroundTasks, Depends
from services.google_drive_webhooks import WebhookNotificationHandler

@app.post("/api/google-drive-webhook")
async def google_drive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Receive push notifications from Google Drive.
    Process immediately in background.
    """
    from services.google_drive_webhooks import WebhookChannelTracker, WebhookNotificationHandler
    from services.google_drive_sync import GoogleDriveSyncPipeline

    try:
        # Parse notification
        headers = dict(request.headers)
        notification = WebhookNotificationHandler.parse_notification(headers)

        # Validate
        tracker = WebhookChannelTracker(db)
        channel = tracker.get_channel(notification["channel_id"])

        if not WebhookNotificationHandler.validate_notification(notification, channel):
            return JSONResponse(status_code=401, content={"error": "Invalid notification"})

        # Check if channel needs renewal
        if WebhookNotificationHandler.should_renew_channel(channel):
            tracker.mark_renewal_needed(notification["channel_id"])
            # Background job will renew

        # Trigger sync in background
        background_tasks.add_task(
            trigger_sync_for_channel,
            channel["tenant_id"],
            channel["folder_id"]
        )

        # Return 200 immediately (Google expects fast response)
        return JSONResponse(status_code=200, content={"received": True})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


async def trigger_sync_for_channel(tenant_id: str, folder_id: str):
    """Background task to process webhook notification."""
    from celery_app import google_drive_sync_task

    try:
        # Dispatch sync task
        task = google_drive_sync_task.delay(
            tenant_id=tenant_id,
            google_drive_folder_id=folder_id,
            excel_output_path=f"/data/{tenant_id}_output.xlsx",
            invoice_type="both",
            model_config=None
        )
        logger.info(f"Webhook triggered sync: {task.id}")
    except Exception as e:
        logger.error(f"Error triggering sync from webhook: {e}")
```

#### 4. Channel Auto-Renewal

Channels expire every ~1 hour. Set up a background job to renew:

```python
@celery_app.task(name="tasks.renew_watch_channels")
def renew_watch_channels():
    """Renew expiring Google Drive watch channels."""
    from database import SessionLocal
    from services.google_drive_webhooks import GoogleDriveWatchManager
    from services.google_drive import GoogleDriveConnector

    db = SessionLocal()
    try:
        from models import GoogleDriveWebhookChannel

        # Find channels needing renewal
        channels = db.query(GoogleDriveWebhookChannel).filter(
            GoogleDriveWebhookChannel.status.in_(["active", "renewal_needed"])
        ).all()

        for channel in channels:
            try:
                # Check if expiring soon
                from datetime import timedelta, datetime
                threshold = datetime.utcnow() + timedelta(minutes=5)
                if channel.expires_at <= threshold:
                    logger.info(f"Renewing channel {channel.channel_id}")

                    drive = GoogleDriveConnector(channel.folder_id)
                    watch_manager = GoogleDriveWatchManager(drive, db)

                    # Re-watch the folder
                    new_channel_id = watch_manager.setup_watch(
                        tenant_id=channel.tenant_id,
                        folder_id=channel.folder_id,
                        webhook_url=os.getenv("GOOGLE_DRIVE_WEBHOOK_URL")
                    )

                    # Mark old channel as expired
                    channel.status = "expired"
                    db.commit()

                    logger.info(f"Renewed channel: {new_channel_id}")

            except Exception as e:
                logger.error(f"Error renewing channel {channel.channel_id}: {e}")

    finally:
        db.close()


# Schedule renewal every 30 minutes
celery_app.conf.beat_schedule = {
    "renew_watch_channels": {
        "task": "tasks.renew_watch_channels",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
    },
    # ... other scheduled tasks
}
```

### Latency Comparison

| Method | Latency | Overhead |
|--------|---------|----------|
| CRON (monthly) | 28 days max | 1 task/month |
| CRON (daily) | 24 hours max | 365 tasks/year |
| Webhook | ~5 minutes | 1 notification per file change |

### Monitoring Webhooks

```sql
-- See active watch channels
SELECT channel_id, tenant_id, folder_id, expires_at, status
FROM google_drive_webhook_channels
WHERE status = 'active'
ORDER BY expires_at ASC;

-- Check notification frequency
SELECT channel_id, COUNT(*) as notifications
FROM google_drive_sync_jobs
WHERE sync_timestamp > now() - interval '24 hours'
GROUP BY channel_id;
```

---

## 3. File Locking for Excel

### Problem

Multiple processes writing to the same `.xlsx` file causes corruption:

```
Process A: Load file
Process B: Load file
Process A: Add rows, save
Process B: Add rows, save (overwrites Process A's changes)
Result: Data loss
```

### Solution

**File locking** coordinates access:

```
Process A: Acquire lock → Load → Modify → Save → Release lock
Process B: Wait for lock → Acquire lock → Load → Modify → Save → Release lock
Result: Data preserved
```

### Implementation

#### 1. Lock-Based Append (Simple)

```python
from services.excel_lockfile import ExcelFileLock
from openpyxl import load_workbook

with ExcelFileLock("/data/output.xlsx", timeout=30) as lock:
    # Lock acquired, safe to modify
    wb = load_workbook(lock.file_path)
    ws = wb.active

    # Add row
    ws.append([col1, col2, col3, ...])

    # Save (still holding lock)
    wb.save(lock.file_path)

# Lock released automatically
```

#### 2. Atomic Write (Safer)

For critical writes, use atomic swaps:

```python
from services.excel_lockfile import ExcelAtomicWrite

with ExcelAtomicWrite.atomic_write("/data/output.xlsx") as temp_path:
    # Write to temporary file first
    wb = load_workbook(temp_path)
    ws = wb.active
    ws.append([col1, col2, col3, ...])
    wb.save(temp_path)

    # On exit: atomic rename temp → final
    # With file lock held to prevent corruption
```

#### 3. How It Works

```
1. Acquire lock (creates .lock file)
   ├─ Wait up to timeout for lock to be free
   └─ Atomic file creation ensures only one process succeeds

2. Modify file (lock held)
   ├─ Load .xlsx
   ├─ Append rows
   └─ Save .xlsx

3. Release lock (deletes .lock file)
   └─ Next process can now acquire lock
```

### Configuration

```python
# Default: 30 second timeout, 0.1s poll interval
with ExcelFileLock(path, timeout=30, poll_interval=0.1):
    # ...
```

### Cleanup Stale Locks

If a process crashes, it leaves a `.lock` file. Clean up periodically:

```python
from services.excel_lockfile import cleanup_stale_locks

# Remove locks older than 24 hours
removed = cleanup_stale_locks("/data", max_age_hours=24)
print(f"Removed {removed} stale locks")
```

### Error Handling

```python
from services.excel_lockfile import FileLockError

try:
    with ExcelFileLock(path, timeout=10):
        # modify file
        pass
except FileLockError as e:
    logger.error(f"Could not acquire lock: {e}")
    # Fallback: skip this write, retry later
```

### Google Sheets Alternative

For cloud-based real-time collaboration, use Google Sheets API instead:

```python
# Instead of openpyxl + locking
# Use Google Sheets API directly

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

sheets_service = build("sheets", "v4", credentials=credentials)

# Append to Google Sheet (atomic server-side)
sheet_id = "1BxiMVs0XRA5nFMfWc0lkxjcVWZjkv5Jg4-YhiGXUVUQ"
values = [[col1, col2, col3, ...]]

request = sheets_service.spreadsheets().values().append(
    spreadsheetId=sheet_id,
    range="Sheet1!A1",
    valueInputOption="USER_ENTERED",
    body={"values": values}
)
response = request.execute()
```

**Pros**: Real-time visibility, no concurrency issues  
**Cons**: Requires Google Sheets setup, different API

---

## Complete Enhanced Pipeline

Combining all three features:

```python
# 1. Download file (PDF or ZIP)
file_data = drive.download_file(file_id, filename, temp_path)

# 2. Handle ZIP if needed
if mime_type == "application/zip":
    from services.google_drive_zip import PDFExtractor
    pdfs = PDFExtractor.extract_pdfs_from_zip(file_data, filename)
else:
    pdfs = [{"filename": filename, "data": file_data, "md5_checksum": ...}]

# 3. Process each PDF
for pdf in pdfs:
    if not file_tracker.is_file_processed(pdf["md5_checksum"]):
        result = process_invoice(pdf["data"])

        # 4. Append to Excel with locking
        from services.excel_lockfile import ExcelFileLock
        with ExcelFileLock(excel_path):
            excel_service.append_items(result.items, pdf["filename"])
```

---

## Configuration Checklist

- [ ] ZIP file extraction enabled (already in code)
- [ ] File locking enabled for Excel writes (already in code)
- [ ] Webhook URL configured (environment variable or setup)
- [ ] Watch channels set up (manual setup script or automatic)
- [ ] Channel renewal task running (Celery Beat)
- [ ] Stale lock cleanup running (daily cron)
- [ ] Monitoring in place (check database tables)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Could not acquire lock after 30s" | Check for stale .lock files, run cleanup_stale_locks |
| "ZIP extraction failed" | Check file size (<500MB), nesting depth (<3), valid ZIP format |
| "Webhook not receiving" | Verify HTTPS URL is public, check firewall, test with webhook.site |
| "Watch channel expired" | Increase renewal frequency, check renewal task logs |

---

See also:
- [GOOGLE_DRIVE_SYNC_SETUP.md](GOOGLE_DRIVE_SYNC_SETUP.md) — Basic setup
- [GOOGLE_DRIVE_SYNC_IMPLEMENTATION.md](GOOGLE_DRIVE_SYNC_IMPLEMENTATION.md) — Architecture
