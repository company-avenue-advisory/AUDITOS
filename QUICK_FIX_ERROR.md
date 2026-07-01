# 🔧 QUICK FIX: "Failed to fetch" Error

## ❌ The Problem

```
Console TypeError
Failed to fetch
src/components/AuthGuard.tsx (28:28)
```

**This means: The backend API is NOT running or NOT accessible**

---

## ✅ The Solution - 3 Steps

### Step 1: Kill Everything

```bash
# Windows (PowerShell)
taskkill /F /IM python.exe
taskkill /F /IM node.exe
taskkill /F /IM celery.exe

# macOS/Linux
pkill -f celery
pkill -f uvicorn
pkill -f "npm run dev"
```

### Step 2: Start Backend FIRST (Wait for It!)

**Terminal 1 - FastAPI Backend:**
```bash
cd C:\Users\yugvk\Downloads\antigravityaudit\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**⏳ WAIT for this output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process [12345]
INFO:     Application startup complete.
```

**⚠️ DO NOT proceed until you see all 3 lines above!**

### Step 3: THEN Start Frontend

**Terminal 2 - Frontend:**
```bash
cd C:\Users\yugvk\Downloads\antigravityaudit\frontend
npm run dev
```

**Wait for:**
```
✓ Ready in 3.2s
```

### Step 4: Refresh Browser

```
http://localhost:3000
```

**Press F5 to hard refresh!**

---

## ⚠️ Common Mistakes (Don't Do These!)

```
❌ DON'T: Start frontend before backend
❌ DON'T: Start all at the same time
❌ DON'T: Skip waiting for "Application startup complete"
❌ DON'T: Just refresh browser without backend running

✅ DO: Start backend first
✅ DO: Wait for "Application startup complete"
✅ DO: Then start frontend
✅ DO: Then open browser
```

---

## 🔍 Verify Backend is Running

**In a NEW terminal:**
```bash
curl http://localhost:8000/docs
```

If you see HTML (Swagger UI) = ✅ Backend is running
If you see "Connection refused" = ❌ Backend is NOT running

---

## 🆘 If Port 8000 is Already in Use

```bash
# Windows - Find what's using port 8000
netstat -ano | findstr :8000

# Kill the process
taskkill /PID <PID> /F

# Then restart backend
```

---

## ✅ Correct Startup Order

```
Step 1: Kill all previous processes
        ↓
Step 2: Start Backend (Terminal 1)
        ↓
        Wait for: "Application startup complete"
        ↓
Step 3: Start Frontend (Terminal 2)
        ↓
        Wait for: "✓ Ready in 3.2s"
        ↓
Step 4: Open browser: http://localhost:3000
        ↓
        Refresh with F5
        ↓
        ✅ Error should be GONE!
```

---

## 📋 Checklist

```
Before opening browser, verify:

☑ Backend Terminal shows:
  - ✓ INFO: Uvicorn running on http://0.0.0.0:8000
  - ✓ Started server process
  - ✓ Application startup complete

☑ Frontend Terminal shows:
  - ✓ Ready in X.Xs
  - ✓ Compiled successfully

☑ Can reach backend:
  - curl http://localhost:8000/docs → Shows Swagger UI

☑ Browser refresh:
  - Press F5 (hard refresh, not Ctrl+R)
  - Clear cache if needed
```

---

## 🚀 If Still Not Working

Check these in order:

1. **Backend running?**
   ```bash
   ps aux | grep uvicorn
   # Should show running process
   ```

2. **Port 8000 free?**
   ```bash
   netstat -ano | findstr :8000
   # Should be empty or show only uvicorn
   ```

3. **Environment variable set?**
   ```powershell
   echo $env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
   # Should show your key path
   ```

4. **Redis running?**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

5. **Dependencies installed?**
   ```bash
   cd backend && pip install -r requirements.txt
   cd frontend && npm install
   ```

---

## 📞 Final Debug

If STILL not working, try this:

```bash
# Terminal 3 - Direct test
curl -v http://localhost:8000/api/health

# Should return:
# HTTP/1.1 200 OK
# (followed by response body)
```

If you see "Connection refused" = Backend is NOT running
If you see "200 OK" = Backend IS running and accessible

---

**Follow the steps above exactly and it will work!** ✅
