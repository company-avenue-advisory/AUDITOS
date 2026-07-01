# Frontend Google Drive Sync Integration

Your frontend now has a complete Google Drive Sync Manager UI. Here's how to use it.

---

## 🚀 Access the Feature

### In Your App

1. **Start your frontend:**
   ```bash
   cd frontend
   npm run dev
   # App running on http://localhost:3000
   ```

2. **Login to your dashboard**

3. **Click "Drive Sync" in the sidebar**
   - New navigation item under the modules section
   - Icon: Cloud ☁️

---

## 📱 UI Overview

### Main Panel: Trigger Sync

**Configuration:**
- ✅ **Google Drive Folder ID** — Pre-filled with your folder ID (readonly)
  - Direct link to open folder: `https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq`
- 🗂️ **Excel Output Path** — Editable (default: `/data/invoices_output.xlsx`)
- 📋 **Invoice Type** — Dropdown: Both / Sales Only / Purchase Only

**Action:**
- 🔵 **"Start Sync Now"** Button — Triggers async sync job

### Right Panel: What Happens

Step-by-step breakdown:
1. Connects to Google Drive
2. Lists all PDF files (& ZIPs)
3. Checks for new/updated files
4. Extracts invoice data via LLM
5. Appends results to Excel
6. Updates database audit log

### Real-Time Status

When sync is running:
- ⏳ Shows current task ID
- 📊 Live stats:
  - Total files found
  - New files
  - Updated files
  - Processed files
  - Failed files
  - Elapsed time

Status updates every 2 seconds while sync is running.

### Sync History

Click **"Show Sync History"** to see:
- Timestamp of each sync
- Status (completed/failed/in_progress)
- Statistics (total, new, processed, failed)
- Sortable table of past syncs

---

## 🧪 Testing Workflow

### Test 1: Verify Connection (2 min)

```
1. Go to Drive Sync page
2. Click "Start Sync Now"
3. Watch status update
4. Expected: Shows "connected - found X PDF files"
```

**Success indicators:**
- ✅ Task ID appears
- ✅ Status changes from PENDING → PROGRESS
- ✅ Files count > 0

### Test 2: First Sync (5 min)

```
1. Make sure at least one PDF is in the folder
2. Click "Start Sync Now"
3. Wait for completion (watch status updates)
4. Check for Excel file at output path
```

**Success indicators:**
- ✅ Status: SUCCESS
- ✅ processed_files > 0
- ✅ Excel file created with data

### Test 3: Deduplication (5 min)

```
1. Run sync again (no new files)
2. Should show: new_files = 0
3. processed_files = 0
```

**Success indicators:**
- ✅ Recognizes same files
- ✅ Skips re-processing

### Test 4: New File Upload (5 min)

```
1. Upload a new PDF to Google Drive folder
2. Run sync again
3. Should detect new file
```

**Success indicators:**
- ✅ new_files = 1
- ✅ processed_files = 1
- ✅ Excel has new rows

---

## 🔌 Backend Integration Checklist

Before testing, make sure backend is ready:

```
☐ Backend running: python -m uvicorn main:app --reload
☐ Celery worker running: celery -A celery_app worker --loglevel=info
☐ Redis running (for broker)
☐ Database initialized with tables
☐ GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON set
☐ API endpoints working (test with curl)
```

**Test backend endpoints:**

```bash
# 1. Trigger sync (POST)
curl -X POST http://localhost:8000/api/google-drive-sync/trigger \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "google_drive_folder_id": "1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq",
    "excel_output_path": "/data/output.xlsx",
    "invoice_type": "both"
  }'

# Expected: {"status": "sync_started", "task_id": "...", ...}

# 2. Check status (GET)
curl http://localhost:8000/api/google-drive-sync/status/TASK_ID \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected: {"task_id": "...", "status": "SUCCESS", "result": {...}}

# 3. Get history (GET)
curl http://localhost:8000/api/google-drive-sync/history \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected: {"sync_jobs": [...]}
```

---

## 🐛 Troubleshooting

### Issue: "Failed to start sync"

**Causes:**
- Backend not running
- API endpoint not reachable
- Auth token invalid/expired

**Solution:**
```bash
# Check backend is running
curl http://localhost:8000/api/health

# Check Celery worker is running
ps aux | grep celery

# Check token in browser console
localStorage.getItem('auth_token')
```

### Issue: "Sync started but status never updates"

**Causes:**
- Celery worker not processing tasks
- Redis not running
- LLM model not available

**Solution:**
```bash
# Check Celery worker logs
celery -A celery_app worker --loglevel=debug

# Check Redis
redis-cli ping  # Should return PONG

# Check if model is available
echo $OLLAMA_MODEL_NAME  # Or your model provider
```

### Issue: "Task stuck on PROGRESS"

**Causes:**
- Extraction timeout (LLM taking too long)
- Database locked
- Network issue

**Solution:**
- Wait longer (first extraction can be slow)
- Check Celery worker logs
- Restart Celery worker: `celery -A celery_app worker --loglevel=info`

### Issue: "No files found in folder"

**Causes:**
- Wrong folder ID
- Service account not shared on folder
- Folder has no PDFs

**Solution:**
```bash
# Verify folder access
python -c "
from services.google_drive import GoogleDriveConnector
drive = GoogleDriveConnector('1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq')
files = drive.list_files(file_types=['application/pdf'])
print(f'Found {len(files)} files')
"

# If 0 files:
# 1. Check folder URL has PDFs
# 2. Re-share folder with service account
# 3. Verify service account JSON is valid
```

---

## 📊 Understanding the Results

### Sample Sync Result

```json
{
  "sync_job_id": "abc-123",
  "status": "completed",
  "total_files_found": 50,
  "new_files": 3,
  "updated_files": 2,
  "processed_files": 5,
  "failed_files": 0,
  "excel_output_path": "/data/invoices_output.xlsx",
  "duration_seconds": 127.45
}
```

**Interpretation:**
- ✅ 50 total PDFs in folder
- ✅ 3 new (never seen before)
- ✅ 2 updated (md5 changed)
- ✅ 5 processed (new + updated)
- ✅ 0 failed (all successful)
- ✅ Took ~2 minutes

**In Excel:**
- 15 rows appended (3 new files × 5 items average)
- All historical data preserved
- "Processed Date" and "Source File" columns added

---

## 🎨 UI Features

### Status Colors

| Status | Color | Meaning |
|--------|-------|---------|
| PENDING | Yellow | Queued, waiting to start |
| PROGRESS | Blue (spinning) | Currently processing |
| SUCCESS | Green ✓ | Completed successfully |
| FAILURE | Red ✗ | Failed with errors |

### Quick Stats

Real-time display while syncing:
```
Total Files: 50          (total in folder)
New: 3                   (never processed)
Updated: 2               (md5 changed)
Processed: 5             (being extracted now)
Failed: 0                (errors)
Duration: 2m 7s          (elapsed time)
```

### Configuration Options

```
📁 Folder ID      → Read-only (your folder)
📄 Excel Path     → Editable (where to save)
📋 Invoice Type   → Dropdown (sales/purchase/both)
```

---

## 🔐 Authentication

The UI automatically uses your auth token:

```javascript
// Token from localStorage
const token = localStorage.getItem('auth_token');

// Used in fetch headers
headers: {
  'Authorization': `Bearer ${token}`
}
```

**Token required for:**
- POST /api/google-drive-sync/trigger
- GET /api/google-drive-sync/status/:id
- GET /api/google-drive-sync/history

If you see 401 errors, your token may be expired. **Log out and log back in.**

---

## 📚 Related Files

Frontend:
- `frontend/src/app/google-drive-sync/page.tsx` — UI component
- `frontend/src/components/Sidebar.tsx` — Navigation (updated)

Backend:
- `backend/main.py` — API endpoints
- `backend/services/google_drive_sync.py` — Pipeline orchestrator
- `backend/celery_app.py` — Celery task definition

---

## 🎯 What You Can Do Now

### From the UI:

✅ **Trigger syncs manually** (anytime, any frequency)  
✅ **Monitor progress** (real-time status updates)  
✅ **View history** (all past syncs with stats)  
✅ **Configure output** (change Excel path, invoice type)  
✅ **Download results** (Excel file in configured location)  

### What Happens Behind the Scenes:

1. Connects to Google Drive
2. Lists all PDFs (& extracts ZIPs)
3. Deduplicates using file ID + MD5
4. Downloads new/changed files
5. Extracts via LLM pipeline
6. Appends to Excel (with locking)
7. Updates database audit trail
8. Returns statistics

---

## 🚀 Next Steps

1. **Today:** Access Drive Sync page, verify backend is running
2. **Today:** Click "Start Sync Now" and watch it process
3. **Today:** Check Excel output and database
4. **Week 1:** Schedule monthly CRON or set up webhooks
5. **Week 1:** Share with team, gather feedback

---

## 💡 Tips

- **First sync** may be slow (LLM extraction bottleneck)
- **Subsequent syncs** are faster (only new/changed files)
- **Polling interval** is 2 seconds (reasonable for UX)
- **Can run multiple syncs** in parallel (different folders)
- **History persists** even if you close the page

---

**Ready to test?** 🎯

1. Make sure backend is running
2. Go to http://localhost:3000
3. Click "Drive Sync" in sidebar
4. Click "Start Sync Now"
5. Watch the magic happen ✨

Questions? Check the docs in `backend/docs/` folder.
