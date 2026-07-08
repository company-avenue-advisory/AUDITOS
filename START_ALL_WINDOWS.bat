@echo off
REM ============================================
REM Start All Services - Windows Batch Script
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo  Google Drive Sync - Start All Services
echo ========================================
echo.

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend
set FRONTEND_DIR=%SCRIPT_DIR%frontend

REM Check for environment variable
if "%GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON%"=="" (
    echo.
    echo WARNING: GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set!
    echo.
    echo Set it with:
    echo   set GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=C:\path\to\your\service-account-key.json
    echo.
    echo Or continue without it (service may fail).
    echo.
    timeout /t 5
)

REM Check if Redis is running
echo Checking Redis...
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Redis is not running!
    echo.
    echo Please start Redis first:
    echo   redis-server
    echo.
    pause
    exit /b 1
)
echo ✓ Redis is running

REM Check if Node is installed
echo.
echo Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Node.js not found!
    echo.
    echo Please install Node.js v16+
    echo   https://nodejs.org/
    echo.
    pause
    exit /b 1
)
echo ✓ Node.js is installed

REM Check if Python is installed
echo.
echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python not found!
    echo.
    echo Please install Python 3.9+
    echo   https://www.python.org/
    echo.
    pause
    exit /b 1
)
echo ✓ Python is installed

echo.
echo ========================================
echo Starting services in separate windows...
echo ========================================
echo.

REM Set environment variable for all child processes
set GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=%GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON%

REM Start Celery Worker in new window
echo [1/4] Starting Celery Worker...
start "Celery Worker" cmd /k ^
  cd /d "%BACKEND_DIR%" ^& ^
  echo Celery Worker starting... ^& ^
  celery -A celery_app worker --loglevel=info -Q celery,default,ocr,drive_sync

REM Wait a moment for Celery to start
timeout /t 3 /nobreak

REM Start Celery Beat in new window — dispatches scheduled sync jobs from
REM beat_schedules.json. Without this running, no scheduled task ever fires,
REM regardless of what's registered (the worker only runs tasks it's handed).
echo [2/4] Starting Celery Beat...
start "Celery Beat" cmd /k ^
  cd /d "%BACKEND_DIR%" ^& ^
  echo Celery Beat starting... ^& ^
  celery -A celery_app beat --loglevel=info

REM Wait a moment for Beat to start
timeout /t 3 /nobreak

REM Start FastAPI Backend in new window
echo [3/4] Starting FastAPI Backend...
start "FastAPI Backend" cmd /k ^
  cd /d "%BACKEND_DIR%" ^& ^
  echo FastAPI Backend starting... ^& ^
  python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

REM Wait a moment for FastAPI to start
timeout /t 3 /nobreak

REM Start Frontend in new window
echo [4/4] Starting Next.js Frontend...
start "Next.js Frontend" cmd /k ^
  cd /d "%FRONTEND_DIR%" ^& ^
  echo Next.js Frontend starting... ^& ^
  npm run dev

REM Wait for services to start
timeout /t 5

echo.
echo ========================================
echo ✓ All services started!
echo ========================================
echo.
echo Services running:
echo   Celery Worker:  Queue for background tasks
echo   FastAPI:        http://localhost:8000
echo   Next.js:        http://localhost:3000
echo.
echo Next steps:
echo   1. Open your browser: http://localhost:3000
echo   2. Login with your credentials
echo   3. Navigate to "Drive Sync" in sidebar
echo   4. Click "Start Sync Now"
echo.
echo Logs are displayed in separate windows.
echo Close any window to stop that service.
echo.
echo Documentation: RUN_LIVE_SERVER.md
echo.
pause
