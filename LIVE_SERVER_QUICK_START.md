# 🚀 LIVE SERVER QUICK START

**Get the entire system running in 60 seconds!**

---

## For Windows Users

### Option A: One-Click Start (Easiest)

1. **Make sure Redis is running:**
   ```bash
   redis-server
   ```

2. **Set environment variable in PowerShell:**
   ```powershell
   $env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\your\service-account-key.json"
   ```

3. **Double-click this file:**
   ```
   START_ALL_WINDOWS.bat
   ```

4. **That's it!** Three new windows will open:
   - ✅ Celery Worker
   - ✅ FastAPI Backend
   - ✅ Next.js Frontend

5. **Open browser:**
   ```
   http://localhost:3000
   ```

---

### Option B: Manual Start (More Control)

**Terminal 1 - Celery Worker:**
```powershell
cd backend
celery -A celery_app worker --loglevel=info
```

**Terminal 2 - FastAPI:**
```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 - Frontend:**
```powershell
cd frontend
npm run dev
```

**Browser:**
```
http://localhost:3000
```

---

## For macOS/Linux Users

### Option A: One-Click Start (Easiest)

1. **Make sure Redis is running:**
   ```bash
   redis-server
   ```

2. **Set environment variable:**
   ```bash
   export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/your/service-account-key.json
   ```

3. **Make script executable & run:**
   ```bash
   chmod +x START_ALL_LINUX.sh
   ./START_ALL_LINUX.sh
   ```

4. **That's it!** New windows/tabs will open with:
   - ✅ Celery Worker
   - ✅ FastAPI Backend
   - ✅ Next.js Frontend

5. **Open browser:**
   ```
   http://localhost:3000
   ```

---

### Option B: Manual Start (More Control)

**Terminal 1 - Celery Worker:**
```bash
cd backend
celery -A celery_app worker --loglevel=info
```

**Terminal 2 - FastAPI:**
```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 - Frontend:**
```bash
cd frontend
npm run dev
```

**Browser:**
```
http://localhost:3000
```

---

## ✅ Verify Everything is Running

Open a new terminal and check:

```bash
# 1. Redis
redis-cli ping
# Returns: PONG

# 2. FastAPI
curl http://localhost:8000/docs
# Opens Swagger UI documentation

# 3. Frontend
curl http://localhost:3000
# Returns HTML

# 4. Celery
curl http://localhost:8000/api/health
# Returns: 200 OK
```

---

## 🎯 Test Drive Sync (5 minutes)

### Step 1: Login
```
URL: http://localhost:3000
Email: dev@companyavenueadvisory.com
Password: (your password)
```

### Step 2: Navigate to Drive Sync
```
Click sidebar → "Drive Sync" (☁️ icon)
```

### Step 3: Verify Configuration
```
Folder ID: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq ✓
Excel Path: /data/invoices_output.xlsx ✓
Invoice Type: Both ✓
```

### Step 4: Click "Start Sync Now"
```
Blue button → Triggers sync
Watch status update in real-time
```

### Step 5: Monitor Progress
```
Task ID appears
Status: PENDING → PROGRESS → SUCCESS
Live stats update every 2 seconds
```

### Step 6: Check Results
```
✅ Excel file created: /data/invoices_output_*.xlsx
✅ Database updated: google_drive_sync_jobs table
✅ Sync history shows latest sync
```

---

## 📊 What You Should See

### Browser (http://localhost:3000)
```
┌─────────────────────────────────────────────────┐
│ Google Drive Invoice Sync                       │
│ Automatically monitor and process invoices      │
├─────────────────────────────────────────────────┤
│                                                 │
│ Folder: 1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq     │
│ Excel:  /data/invoices_output.xlsx             │
│ Type:   Both                                    │
│                                                 │
│ [🔵 Start Sync Now]                            │
│                                                 │
│ ⏳ PROGRESS                                      │
│ Task: abc-123-def-456                          │
│ Total: 12   New: 3   Processed: 1   Failed: 0 │
│ Duration: 45s                                  │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Terminal 1 - Celery
```
[2026-06-30 14:35:00,000: INFO/MainProcess] celery@YOUR_MACHINE ready to accept tasks
[2026-06-30 14:35:22,123: INFO/MainProcess] Received task: tasks.google_drive_sync_task
[2026-06-30 14:35:23,000: INFO/MainProcess] google_drive_sync_task: Processing invoice.pdf
[2026-06-30 14:35:35,000: INFO/MainProcess] google_drive_sync_task: SUCCESS
```

### Terminal 2 - FastAPI
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     POST /api/google-drive-sync/trigger
INFO:     GET /api/google-drive-sync/status/abc-123-def-456
INFO:     GET /api/google-drive-sync/history
```

### Terminal 3 - Frontend
```
  ▲ Next.js 14.0.0
  - Local:        http://localhost:3000

 ✓ Ready in 3.2s
 ✓ Compiled client and server successfully
```

---

## 🔥 Common Issues & Fixes

### "Redis not running"
```bash
# macOS
brew services start redis
# OR
redis-server

# Ubuntu/Debian
sudo systemctl start redis-server

# Windows
# Install Redis from: https://github.com/microsoftarchive/redis/releases
redis-server
```

### "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set"
```powershell
# PowerShell
$env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\Users\yugvk\path\to\key.json"

# Bash/Zsh
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json
```

### "Port 8000 already in use"
```bash
# Find what's using port 8000
# Windows
netstat -ano | findstr :8000

# macOS/Linux
lsof -i :8000

# Kill the process and restart
```

### "npm not found"
```bash
# Install Node.js
# https://nodejs.org/ (v16+ recommended)

# Then install dependencies
cd frontend
npm install
```

### "Python not found"
```bash
# Install Python
# https://www.python.org/ (3.9+ recommended)

# Then install backend dependencies
cd backend
pip install -r requirements.txt
```

---

## 📈 Expected Performance

```
First sync (with 50 files):
  Time: 3-5 minutes (LLM extraction is bottleneck)
  Files processed: ~50
  Excel size: +150 KB
  
Subsequent syncs (no new files):
  Time: ~10 seconds
  Files processed: 0 (dedup skips them)
  
UI responsiveness:
  Button click → Task ID in 2 seconds
  Status updates: Every 2 seconds
  Completion → Excel created in 1 minute
```

---

## 🎯 Success Indicators

You know everything works when:

```
✅ All three terminal windows open without errors
✅ Browser loads http://localhost:3000
✅ Can login and see dashboard
✅ "Drive Sync" appears in sidebar
✅ Configuration shows correct folder ID
✅ "Start Sync Now" button is clickable
✅ Task ID appears immediately when clicked
✅ Status updates every 2 seconds
✅ Status changes from PENDING → PROGRESS → SUCCESS
✅ Processed files > 0
✅ No red error messages
✅ Excel file created
✅ Sync history shows latest sync with ✅ SUCCESS
```

---

## 🛑 Stop Everything

When done testing:

```bash
# In each terminal window:
Ctrl + C

# Or if using the batch script:
# Close each window individually
```

---

## 📚 Learn More

- **Live Server Details:** `RUN_LIVE_SERVER.md`
- **Production Deployment:** `PRODUCTION_READY.md`
- **Frontend Guide:** `FRONTEND_SETUP.md`
- **Troubleshooting:** `START_HERE_TESTING.md`

---

## 🚀 You're Ready!

**Just ONE of these:**

### Windows:
```powershell
# Set env var first
$env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\key.json"

# Then double-click
START_ALL_WINDOWS.bat
```

### macOS/Linux:
```bash
# Set env var first
export GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=/path/to/key.json

# Then run
chmod +x START_ALL_LINUX.sh
./START_ALL_LINUX.sh
```

### Open browser:
```
http://localhost:3000
```

**Enjoy!** 🎉
