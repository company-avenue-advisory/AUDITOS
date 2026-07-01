# 🚀 START HERE: Complete Testing Guide

Everything is ready. Follow these steps to test the Google Drive sync end-to-end.

---

## ⏱️ Total Time: 30 minutes

```
Step 1: Prepare Backend     (5 min)
Step 2: Start Frontend      (5 min)
Step 3: Access UI           (1 min)
Step 4: Run First Sync      (5 min)
Step 5: Verify Results      (5 min)
Step 6: Troubleshoot        (5 min, if needed)
```

---

## 📋 Prerequisites Checklist

```
☐ Backend installed: pip install -r requirements.txt
☐ Frontend installed: npm install
☐ Redis running (for Celery broker)
☐ Google Drive folder shared: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
☐ Service account JSON downloaded and path known
```

---

## Step 1: Prepare Backend (5 min)

### 1.1 Set Environment Variable

**Windows (PowerShell):**
```powershell
# Option A: Inline
$env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\your\service-account-key.json"

# Option B: Edit .env file in backend/
# GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=C:\path\to\key.json
```

**macOS/Linux:**
```bash
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/service-account-key.json

# Or edit backend/.env:
# GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json
```

### 1.2 Start Backend Services

**Terminal 1 — Celery Worker:**
```bash
cd backend
celery -A celery_app worker --loglevel=info
```

**Terminal 2 — FastAPI Server:**
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Verify:**
```bash
# Terminal 3 — Test endpoints
curl http://localhost:8000/docs  # Should show API docs
redis-cli ping                   # Should return PONG
```

---

## Step 2: Start Frontend (5 min)

**Terminal 3:**
```bash
cd frontend
npm run dev
```

**Verify:**
```
✓ Compiled /app
Local: http://localhost:3000
```

---

## Step 3: Access UI (1 min)

1. Open browser: **http://localhost:3000**
2. Login with your credentials
3. Click **"Drive Sync"** in sidebar (☁️ icon)

**You should see:**
- Dark theme UI
- "Google Drive Invoice Sync" heading
- "Trigger Sync" control panel
- "What Happens" info card

---

## Step 4: Run First Sync (5 min)

### Verify Configuration

Check the form shows:
```
📁 Folder ID: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq ✓
📄 Excel Path: /data/invoices_output.xlsx ✓
📋 Invoice Type: Both (Sales & Purchase) ✓
```

### Click "Start Sync Now"

You should see:

1. **Immediately:** Button changes to "Sync In Progress..."
2. **Within 2s:** Task ID appears with PENDING status
3. **Within 5s:** Status changes to PROGRESS
4. **After ~30s:** Shows stats updating in real-time:
   ```
   Current Task: [task-id]
   Status: ⏳ PROGRESS
   
   Total Files: 12
   New: 3
   Updated: 0
   Processed: 0 (incrementing...)
   Failed: 0
   ```
5. **After 1-3 min:** Status changes to SUCCESS
   ```
   Status: ✅ SUCCESS
   
   Total Files: 12
   New: 3
   Updated: 0
   Processed: 3
   Failed: 0
   Duration: 127.45s
   ```

### Success Messages

You should see green success message:
```
✅ Sync completed successfully!
```

---

## Step 5: Verify Results (5 min)

### 5.1 Check Excel File

```bash
# Windows
dir /s /b C:\data\invoices_output*.xlsx

# macOS/Linux
ls -lh /data/invoices_output*.xlsx
```

**Should exist:**
- `/data/invoices_output_sales.xlsx` (if sales invoices found)
- `/data/invoices_output_purchase.xlsx` (if purchase invoices found)

**File should contain:**
- Header row with column names
- Data rows with extracted invoice information
- "Processed Date" column (today's date)
- "Source File" column (original filename)

### 5.2 Check Database

```bash
# View sync job history
sqlite3 audit.db "SELECT id, sync_timestamp, total_files_found, processed_files, status FROM google_drive_sync_jobs ORDER BY sync_timestamp DESC LIMIT 5;"

# Expected output:
# id | sync_timestamp | total_files_found | processed_files | status
# abc-123 | 2026-06-30 14:30:00 | 12 | 3 | completed
```

### 5.3 Check File Tracker

```bash
sqlite3 audit.db "SELECT google_drive_id, filename, processing_status, processed_at FROM google_drive_file_tracker WHERE tenant_id = 'your_tenant' LIMIT 5;"

# Should show files marked as 'completed'
```

### 5.4 View Sync History in UI

1. On Drive Sync page, click **"Show Sync History"**
2. Should see table with:
   - Timestamp
   - Status: ✅ completed
   - Total files: 12
   - New: 3
   - Processed: 3
   - Failed: 0

---

## Step 6: Troubleshooting (if needed)

### Issue: "Failed to start sync"

```
❌ Error: Failed to start sync
```

**Check 1:** Backend running?
```bash
curl http://localhost:8000/api/health
# If fails: check terminal 2
```

**Check 2:** Correct auth token?
```bash
# Open browser console (F12), check:
localStorage.getItem('auth_token')
# Should have a long token string
```

**Check 3:** Environment variable set?
```bash
# Windows:
echo $env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
# macOS/Linux:
echo $GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
# Should show path to JSON file
```

### Issue: "Status stuck on PROGRESS"

```
⏳ PROGRESS (for > 5 minutes)
```

**Check 1:** Celery worker running?
```bash
# Check Terminal 1
# Should show: ready to accept tasks
```

**Check 2:** Redis running?
```bash
redis-cli ping
# Should return: PONG
```

**Check 3:** Google Drive access?
```bash
python -c "
from services.google_drive import GoogleDriveConnector
drive = GoogleDriveConnector('1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq')
files = drive.list_files(file_types=['application/pdf'])
print(f'Found {len(files)} files')
"
# Should find files in folder
```

### Issue: "Processed files = 0"

```
Processed: 0 (but total_files_found > 0)
```

**Possible causes:**
- All files already processed (check new_files)
- PDF extraction failed (check logs)
- No valid invoices in folder

**Check:**
```bash
# View file tracker
sqlite3 audit.db "SELECT filename, processing_status, error_message FROM google_drive_file_tracker WHERE processing_status = 'failed' LIMIT 5;"

# Check Celery logs
# Terminal 1 should show any extraction errors
```

### Issue: "Google Drive connection failed"

```
❌ Google Drive connected - found 0 PDF files
```

**Check:**
1. Folder URL is valid: https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
2. Service account shared on folder
3. Folder actually has PDFs

**Fix:**
```bash
# Re-share folder with service account email
# Find service account email in service-account-key.json:
python -c "import json; print(json.load(open('key.json'))['client_email'])"

# Then go to: https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq
# Click Share → paste email → Viewer role → Share
```

---

## ✅ Success Criteria

You've successfully completed the test if:

```
✅ Backend starts without errors
✅ Frontend loads at http://localhost:3000
✅ Drive Sync page loads with form
✅ "Start Sync Now" button works (doesn't show 500 error)
✅ Task ID appears within 2 seconds
✅ Status updates from PENDING → PROGRESS → SUCCESS
✅ Stats show processed_files > 0
✅ Excel file created at /data/invoices_output_*.xlsx
✅ Database has new entries in google_drive_sync_jobs table
✅ Sync History table shows the completed sync
```

---

## 🎁 Bonus: Test Deduplication

After first sync succeeds:

1. **Click "Start Sync Now" again** (without uploading new files)
2. Status should show:
   ```
   Total Files: 12
   New: 0 (no new files)
   Updated: 0 (no changed files)
   Processed: 0 (nothing to process)
   Duration: ~10s (much faster!)
   ```

**This proves deduplication works!** ✅

---

## 🎯 Next Steps After Testing

### If All Works:

1. **Schedule monthly sync:**
   ```python
   # Add to celerybeat-schedule.json
   "google_drive_sync_client": {
     "task": "tasks.google_drive_sync_task",
     "schedule": {
       "minute": "0",
       "hour": "0",
       "day_of_month": "1"  # 1st of month at 00:00 UTC
     },
     "kwargs": {...}
   }
   ```

2. **Start Celery Beat:**
   ```bash
   celery -A celery_app beat --loglevel=info
   ```

3. **Sync will now run automatically monthly!**

### If Something Breaks:

1. Check the troubleshooting section above
2. Read backend logs (Terminal 1 & 2)
3. Check frontend console (F12)
4. Read [FRONTEND_SETUP.md](FRONTEND_SETUP.md) for details

---

## 📞 Quick Reference

| What | Where | Command |
|------|-------|---------|
| **Start Backend** | Terminal 1 | `celery -A celery_app worker --loglevel=info` |
| **Start API** | Terminal 2 | `python -m uvicorn main:app --reload` |
| **Start Frontend** | Terminal 3 | `npm run dev` |
| **Test API** | Terminal 4 | `curl http://localhost:8000/api/health` |
| **View Logs** | DB | `sqlite3 audit.db "..."` |
| **Check Sync** | UI | http://localhost:3000 → Drive Sync |

---

## 📚 Documentation

- **Frontend:** [FRONTEND_SETUP.md](FRONTEND_SETUP.md) — UI details, features, troubleshooting
- **Backend:** [backend/docs/SETUP_FOR_CLIENT.md](backend/docs/SETUP_FOR_CLIENT.md) — Detailed setup
- **Advanced:** [backend/docs/GOOGLE_DRIVE_ADVANCED.md](backend/docs/GOOGLE_DRIVE_ADVANCED.md) — ZIP, webhooks, locking

---

## ⏱️ Timeline

```
Now:       Follow steps 1-5
Today:     Test works end-to-end
This week: Configure monthly CRON or webhooks
Next week: Verify automatic monthly sync runs
```

---

**You're ready!** 🚀

Open a terminal and start with:
```bash
cd backend
celery -A celery_app worker --loglevel=info
```

Then in another terminal:
```bash
cd backend
python -m uvicorn main:app --reload
```

Then in another terminal:
```bash
cd frontend
npm run dev
```

Then go to: **http://localhost:3000** → Click "Drive Sync" → Click "Start Sync Now"

Enjoy! 🎉
