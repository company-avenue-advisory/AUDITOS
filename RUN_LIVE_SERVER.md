# 🚀 RUN LIVE SERVER - Complete Setup

Get everything running in 5 minutes for end-to-end testing.

---

## Prerequisites Check

```bash
# 1. Redis installed and running
redis-cli ping
# Should return: PONG

# 2. Node.js installed
node --version
# Should be v16+

# 3. Python installed
python --version
# Should be 3.9+

# 4. Google Drive service account JSON ready
echo $GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
# Should show path to your key.json
```

If anything is missing, install it first before proceeding.

---

## Step 1: Terminal 1 - Celery Worker

```bash
cd C:\Users\yugvk\Downloads\antigravityaudit\backend

# Set environment variable (Windows PowerShell)
$env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\your\service-account-key.json"

# Or on Linux/Mac:
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/your/service-account-key.json

# Start Celery worker
celery -A celery_app worker --loglevel=info
```

**Expected output:**
```
 -------------- celery@YOUR_MACHINE v5.3.0 (emerald-rush)
--- ***** -----
-- ******* ----
- *** --- * ---
- ** ---------- [config]
- ** ---------- .broker: redis://localhost:6379/0
- ** ---------- .app: celery_app:0x...
- ** ---------- .pid: 12345
- ** ---------- .hostname: celery@...
- ** ---------- .loader: celery.loaders.app
- ** ---------- .loglevel: INFO
- ** ---------- .concurrency: 8
- ** ---------- .pool: prefork
- ** ---------- .time zone: UTC
- ** ---------- .scheduler: celery.beat.PersistentScheduler
--- **** --- * --- [queues]
 -------------- .default: exchange:celery
                 routing_key:celery

[tasks]
  . celery.accumulate
  . celery.backend_cleanup
  . celery.chain
  . celery.chord
  . celery.chord_unlock
  . tasks.google_drive_sync_task
  . tasks.ocr_extract_task
  . tasks.process_batch_task

[2026-06-30 14:30:00,000: INFO/MainProcess] celery@YOUR_MACHINE ready to accept tasks
```

✅ **Celery Worker Running!** Keep this terminal open.

---

## Step 2: Terminal 2 - FastAPI Backend

```bash
cd C:\Users\yugvk\Downloads\antigravityaudit\backend

# Set environment (if not already set globally)
$env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\your\service-account-key.json"

# Start FastAPI server
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

✅ **FastAPI Running on http://localhost:8000!** Keep this terminal open.

---

## Step 3: Terminal 3 - Next.js Frontend

```bash
cd C:\Users\yugvk\Downloads\antigravityaudit\frontend

# Install dependencies (if not done)
npm install

# Start development server
npm run dev
```

**Expected output:**
```
> next dev
  ▲ Next.js 14.0.0
  - Local:        http://localhost:3000
  - Environments: .env.local

 ✓ Ready in 3.2s
```

✅ **Frontend Running on http://localhost:3000!** Keep this terminal open.

---

## Step 4: Verify All Services

**Terminal 4** - Run verification:

```bash
# Check Redis
redis-cli ping
# Should return: PONG

# Check FastAPI
curl http://localhost:8000/docs
# Should show Swagger UI docs

# Check Celery
curl http://localhost:8000/api/health
# Should return: 200 OK

# Check Frontend
curl http://localhost:3000
# Should return HTML (Next.js page)
```

✅ **All Services Running!**

---

## Step 5: Open in Browser

**URL:** http://localhost:3000

You should see:
- ✅ AuditOS login page
- ✅ Sidebar with navigation
- ✅ "Drive Sync" option in sidebar

---

## Step 6: Login

1. Click "Login" or navigate to http://localhost:3000/login
2. Use test credentials:
   ```
   Email: dev@companyavenueadvisory.com
   Password: (your password)
   ```
   
   Or create a test user if needed

---

## Step 7: Navigate to Drive Sync

1. Click **"Drive Sync"** in the sidebar (☁️ icon)
2. You should see:
   ```
   ┌─────────────────────────────────────────┐
   │ Google Drive Invoice Sync               │
   │ Automatically monitor and process...    │
   └─────────────────────────────────────────┘
   
   Folder ID: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq ✓
   Excel Path: /data/invoices_output.xlsx ✓
   Invoice Type: Both ✓
   
   [🔵 Start Sync Now] Button
   ```

---

## Step 8: Click "Start Sync Now"

1. **Click the blue button** "Start Sync Now"

2. **Watch in real-time:**
   - Status changes to PROGRESS
   - Task ID appears
   - Live stats update every 2 seconds:
     ```
     Current Task: abc-123-def-456
     Status: ⏳ PROGRESS
     
     Total Files: 12
     New: 3
     Updated: 0
     Processed: 1 (incrementing...)
     Failed: 0
     Duration: 35 seconds
     ```

3. **Check Backend Logs:**
   - Terminal 2 (FastAPI): Shows API requests
   - Terminal 1 (Celery): Shows extraction progress

4. **Wait for Completion** (~2-5 minutes)
   - Status changes to SUCCESS
   - Shows final stats:
     ```
     Status: ✅ SUCCESS
     
     Total Files: 12
     New: 3
     Updated: 0
     Processed: 3
     Failed: 0
     Duration: 127.45 seconds
     ```

---

## Step 9: Verify Results

### 9.1 Check Excel File

```bash
# Windows
dir C:\data\invoices_output*.xlsx

# Linux/Mac
ls -lh /data/invoices_output*.xlsx
```

Should show:
```
invoices_output_sales.xlsx      (5 KB, today's date)
invoices_output_purchase.xlsx   (3 KB, today's date)
```

### 9.2 Open Excel File

Open in Excel/Google Sheets:
- Header row with column names
- Data rows with extracted invoice information
- "Processed Date" = today
- "Source File" = original filename

### 9.3 Check Database

```bash
# View sync jobs
sqlite3 audit.db "SELECT id, sync_timestamp, status, processed_files FROM google_drive_sync_jobs ORDER BY sync_timestamp DESC LIMIT 1;"

# Expected output:
# abc-123 | 2026-06-30 14:35:22 | completed | 3
```

### 9.4 View Sync History in UI

Click "Show Sync History" in the Drive Sync page:
- Table shows all past syncs
- Latest one at top with ✅ SUCCESS
- Shows: timestamp, status, total files, new, processed, failed

---

## 🎯 Live Testing Workflow

### Test Scenario 1: Upload New Invoice & Sync

1. Upload a new PDF to Google Drive folder
2. Click "Start Sync Now" in UI
3. Watch:
   - Status updates in real-time
   - new_files = 1
   - processed_files = 1
4. Excel file grows by new rows

### Test Scenario 2: Verify Deduplication

1. Click "Start Sync Now" again (NO new files uploaded)
2. Watch:
   - Status shows PROGRESS
   - new_files = 0
   - processed_files = 0 (nothing to do)
   - Duration ~10 seconds (much faster!)
3. ✅ Deduplication works!

### Test Scenario 3: Check Database Audit

1. Open database:
   ```bash
   sqlite3 audit.db
   ```

2. Run queries:
   ```sql
   -- See all syncs
   SELECT * FROM google_drive_sync_jobs ORDER BY sync_timestamp DESC;
   
   -- See file processing history
   SELECT filename, processing_status, processed_at FROM google_drive_file_tracker LIMIT 10;
   
   -- See failed files (if any)
   SELECT filename, error_message FROM google_drive_file_tracker WHERE processing_status = 'failed';
   ```

---

## 🔍 Monitoring Live

### Terminal 1 - Celery Worker Log
```
Shows:
- [tasks] google_drive_sync_task received
- [extraction] Processing invoice.pdf
- [completed] Task finished
```

### Terminal 2 - FastAPI Log
```
Shows:
- POST /api/google-drive-sync/trigger
- GET /api/google-drive-sync/status/{task_id}
- GET /api/google-drive-sync/history
```

### Terminal 4 - Browser Console (F12)
```
Shows:
- API requests/responses
- Status polling (every 2s)
- Any JavaScript errors
```

### Database Audit
```bash
sqlite3 audit.db
SELECT * FROM google_drive_sync_jobs WHERE sync_timestamp > datetime('now', '-1 hour');
```

---

## 🆘 If Something Goes Wrong

### Issue: "Failed to start sync"

**Check:**
1. Backend running? (Terminal 2 should show "Uvicorn running")
2. Celery worker running? (Terminal 1 should show "ready to accept tasks")
3. Redis running? (redis-cli ping → PONG)

**Fix:**
```bash
# Kill and restart
pkill -f celery
pkill -f uvicorn
pkill -f "npm run dev"

# Then restart services (Steps 1-3 above)
```

### Issue: "No files found in Google Drive"

**Check:**
1. Folder URL: https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
2. Service account shared on folder? (Should show "View" access)
3. Folder has PDFs? (Upload a test PDF)

**Fix:**
```bash
python -c "
from services.google_drive import GoogleDriveConnector
drive = GoogleDriveConnector('1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq')
files = drive.list_files(file_types=['application/pdf'])
print(f'Found {len(files)} files')
"
```

### Issue: "Sync stuck on PROGRESS"

**Check:**
1. Celery worker (Terminal 1) - should show logs
2. FastAPI (Terminal 2) - should show activity
3. Browser console (F12) - any errors?

**Fix:**
```bash
# Check Celery status
celery -A celery_app inspect active
celery -A celery_app inspect stats

# Restart Celery
pkill -f celery
celery -A celery_app worker --loglevel=info
```

---

## 📊 Performance Monitoring

### Frontend (Browser Console - F12)

```javascript
// Check API response time
// Should be < 1 second for status checks

// Monitor polling
// Should poll /api/google-drive-sync/status every 2 seconds

// Check for errors
console.error  // Should be empty
```

### Backend (Terminals 1-2)

```
Expected patterns:
- google_drive_sync_task received  (task queued)
- Received task: google_drive...   (worker picked it up)
- [extraction] Processing...       (actively extracting)
- [completed] Task google_drive...  (finished)
- 200 OK                           (API response)
```

### Database

```bash
# Check sync statistics
sqlite3 audit.db "
SELECT 
  COUNT(*) as total_syncs,
  SUM(processed_files) as total_processed,
  SUM(failed_files) as total_failed,
  AVG(CAST((julianday(completed_at) - julianday(sync_timestamp)) * 86400 AS FLOAT)) as avg_duration_sec
FROM google_drive_sync_jobs;
"
```

---

## ✅ Success Checklist

You've successfully tested end-to-end when:

```
✅ Celery worker shows "ready to accept tasks"
✅ FastAPI shows "Uvicorn running"
✅ Frontend loads without errors
✅ Can login and navigate to Drive Sync
✅ "Start Sync Now" button works
✅ Task ID appears within 2 seconds
✅ Status updates every 2 seconds
✅ Status shows PROGRESS with live stats
✅ Status changes to SUCCESS after 1-5 min
✅ processed_files > 0
✅ Excel file created at /data/invoices_output_*.xlsx
✅ Database has new entry in google_drive_sync_jobs
✅ Sync history table shows latest sync
✅ No red error messages in UI
✅ No errors in browser console (F12)
✅ No errors in backend logs
```

---

## 🎉 You're Live!

**Everything Running:**
- ✅ Celery Worker: http://localhost:6379 (Redis)
- ✅ FastAPI Backend: http://localhost:8000
- ✅ Next.js Frontend: http://localhost:3000
- ✅ Google Drive API: Connected & authenticated

**Open your browser:**
```
http://localhost:3000
→ Login
→ Click "Drive Sync"
→ Click "Start Sync Now"
→ Watch real-time status updates
→ See Excel file created
→ View database audit trail
```

**Done!** 🚀 You now have a complete live system running end-to-end.

---

## 🛑 Stopping Everything

When done testing:

```bash
# Terminal 1
Ctrl + C  # Stops Celery worker

# Terminal 2
Ctrl + C  # Stops FastAPI

# Terminal 3
Ctrl + C  # Stops Next.js

# Terminal 4
Ctrl + C  # Stops any other process
```

---

## 📚 Next Steps

1. ✅ System is running end-to-end
2. ✅ Test different scenarios (new files, dedup, etc.)
3. ✅ Review Excel output and database
4. ✅ Check logs for any warnings
5. ✅ When satisfied, deploy to production (see PRODUCTION_READY.md)

---

**System is LIVE and READY!** 🎊
