# Quick Setup Script for Google Drive Auto-Sync (Windows PowerShell)
# Usage: .\scripts\quick_setup.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Google Drive Auto-Sync Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$FolderId = "1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq"
$TenantId = if ($args.Length -gt 0) { $args[0] } else { "default_tenant" }
$ExcelOutput = "/data/invoices_output.xlsx"

Write-Host "📁 Google Drive Folder: $FolderId" -ForegroundColor Yellow
Write-Host "👤 Tenant ID: $TenantId" -ForegroundColor Yellow
Write-Host "📊 Excel Output: $ExcelOutput" -ForegroundColor Yellow
Write-Host ""

# Step 1: Check environment
Write-Host "Step 1: Checking environment..." -ForegroundColor Cyan
$ServiceAccountJson = $env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
if ([string]::IsNullOrEmpty($ServiceAccountJson)) {
    Write-Host "❌ GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set" -ForegroundColor Red
    Write-Host ""
    Write-Host "Set it with:" -ForegroundColor Yellow
    Write-Host '  $env:GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = "C:\path\to\key.json"' -ForegroundColor Gray
    Write-Host "or add to .env file" -ForegroundColor Gray
    Write-Host ""
    exit 1
}
Write-Host "✅ GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is set" -ForegroundColor Green

# Step 2: Install dependencies
Write-Host ""
Write-Host "Step 2: Installing dependencies..." -ForegroundColor Cyan
pip install -q google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 openpyxl
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# Step 3: Initialize database
Write-Host ""
Write-Host "Step 3: Initializing database..." -ForegroundColor Cyan
Set-Location $PSScriptRoot\..\
python -c "from database import engine, Base; Base.metadata.create_all(bind=engine); print('✅ Database tables created')"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database initialized" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to initialize database" -ForegroundColor Red
    exit 1
}

# Step 4: Test Google Drive connection
Write-Host ""
Write-Host "Step 4: Testing Google Drive connection..." -ForegroundColor Cyan
python -c @"
from services.google_drive import GoogleDriveConnector
try:
    drive = GoogleDriveConnector('$FolderId')
    files = drive.list_files(file_types=['application/pdf'])
    print(f'✅ Google Drive connected - found {len(files)} PDF files')
except Exception as e:
    print(f'❌ Error: {e}')
    import sys
    sys.exit(1)
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Google Drive connection failed" -ForegroundColor Red
    exit 1
}

# Step 5: Test database tracking
Write-Host ""
Write-Host "Step 5: Initializing file tracker..." -ForegroundColor Cyan
python -c @"
from database import SessionLocal
from models import GoogleDriveFileTracker
from services.google_drive import GoogleDriveFileTracker as Tracker

db = SessionLocal()
tracker = Tracker(db)
print('✅ File tracker initialized')
db.close()
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ File tracker ready" -ForegroundColor Green
} else {
    Write-Host "❌ File tracker initialization failed" -ForegroundColor Red
    exit 1
}

# Step 6: Show next steps
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host ""

Write-Host "1️⃣  Run a test sync:" -ForegroundColor Cyan
Write-Host "    python -c `"from celery_app import google_drive_sync_task; result = google_drive_sync_task.delay('$TenantId', '$FolderId', '$ExcelOutput', 'both'); print(f'Task: {result.id}')`"" -ForegroundColor Gray
Write-Host ""

Write-Host "2️⃣  Check sync status:" -ForegroundColor Cyan
Write-Host "    curl http://localhost:8000/api/google-drive-sync/status/TASK_ID" -ForegroundColor Gray
Write-Host ""

Write-Host "3️⃣  View sync history:" -ForegroundColor Cyan
Write-Host '    sqlite3 audit.db "SELECT id, sync_timestamp, processed_files FROM google_drive_sync_jobs LIMIT 5;"' -ForegroundColor Gray
Write-Host ""

Write-Host "4️⃣  Schedule monthly sync (add to celerybeat-schedule.json):" -ForegroundColor Cyan
$scheduleJson = @{
    "google_drive_sync_$TenantId" = @{
        "task" = "tasks.google_drive_sync_task"
        "schedule" = @{"minute"=0; "hour"=0; "day_of_month"=1}
        "kwargs" = @{
            "tenant_id" = $TenantId
            "google_drive_folder_id" = $FolderId
            "excel_output_path" = $ExcelOutput
            "invoice_type" = "both"
        }
    }
} | ConvertTo-Json
Write-Host "    $scheduleJson" -ForegroundColor Gray
Write-Host ""

Write-Host "5️⃣  Start Celery worker:" -ForegroundColor Cyan
Write-Host "    celery -A celery_app worker --loglevel=info" -ForegroundColor Gray
Write-Host ""

Write-Host "📚 Documentation:" -ForegroundColor Cyan
Write-Host "    docs/GOOGLE_DRIVE_SYNC_QUICKSTART.md" -ForegroundColor Gray
Write-Host "    docs/GOOGLE_DRIVE_SYNC_SETUP.md" -ForegroundColor Gray
Write-Host "    docs/GOOGLE_DRIVE_ADVANCED.md" -ForegroundColor Gray
Write-Host ""
