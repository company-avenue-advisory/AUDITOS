# Google Drive Sync — Strategic Overhaul Plan

**Date:** 2026-08-01
**Author:** CTO Review (Opus orchestrator)
**Status:** In Progress

---

## Problem Statement

The Google Drive Sync feature is functional but not production-ready for accountant use. Key issues:

1. **Failed files permanently skipped** — dedup logic ignores `processing_status`
2. **No period scoping** — pulling June invoices from August is impossible
3. **No cancel mechanism** — once started, a sync cannot be stopped
4. **UX too technical** — cron expressions, folder IDs, dual overlapping sync mechanisms visible to accountants

## Reference: aiAccountant.com

- Clean white background, professional blue accent
- Clear readable fonts (14px+ body)
- Cards with subtle shadows
- Plain-language labels — no technical jargon exposed

---

## Phase 1: Backend P0 Fixes

### 1.1 Dedup Bug Fix
- **File:** `backend/services/google_drive.py:203-227`
- **Bug:** `is_file_processed()` only checks `google_drive_id` + `md5_checksum`
- **Impact:** Files with status `processing` (crashed) or `failed` are permanently skipped
- **Fix:** Add check `if existing.processing_status != "completed": return False`

### 1.2 Cancel/Stop Mechanism
- **Model:** Add `celery_task_id` column to `GoogleDriveSyncJob` (models.py:326)
- **Endpoint:** `POST /api/google-drive-sync/cancel/{task_id}`
- **Implementation:** `celery_app.control.revoke(task_id, terminate=True)`
- **Migration:** ALTER TABLE script for running production DB

### 1.3 Period Parameter
- **Endpoints:** `trigger-sales` (main.py:2517), `trigger-purchase` (main.py:2546)
- **Change:** Accept optional `period` body param (YYYY-MM format)
- **Thread to:** `resolve_month_folder_id()` with parsed date instead of `date.today()`

---

## Phase 2: Theme Overhaul

### 2.1 White-First Theme
- Swap `:root` (dark) and `[data-theme="light"]` in globals.css
- New default: white background, dark text, blue accent (#2563EB)
- Cards: white with subtle shadow instead of dark glass

### 2.2 Font Readability
- Body font size: 14px minimum
- Line height: 1.6
- Labels: 13px minimum (currently many at 11-12px)

### 2.3 Layout Default
- layout.tsx: default to `'light'` instead of system preference

---

## Phase 3: Drive Sync Page Redesign

### Target UX (Accountant-Friendly)

**Zone 1 — Primary Action:**
```
[Month Dropdown: June 2026 ▼] [Import Sales Invoices] [Import Purchase Invoices]
```

**Zone 2 — Live Status:**
```
Importing June sales... 42 of 118 processed [████████░░░░] [Stop]
```

**Zone 3 — Results:**
```
Last import: 42 new invoices imported, 5 already existed (skipped), 3 could not be read
[Download Sales Excel] [Download Purchase Excel]
```

**Advanced Setup (collapsed):**
- Drive folder connections
- Fiscal year start month
- Folder pattern
- GSTR-2B folder

### Changes Required
- Complete rewrite of `frontend/src/app/google-drive-sync/page.tsx`
- Month selector sends `{ period: "2026-06", max_files: 100 }`
- Stop button calls `POST /cancel/{task_id}`
- Hide cron, folder IDs, task IDs behind `<details>` toggle

---

## Phase 4: System-Wide UX Audit

- Dashboard page
- Invoice extraction page
- Tally connector page
- GSTR reconciliation page
- All pages get consistent white theme, readable fonts, accountant-friendly labels

---

## Cost of Inaction

| Issue | Impact |
|-------|--------|
| Dedup bug | Failed files never retry — data loss |
| No period selector | Accountants must ask devs to run past-month imports |
| No cancel | Runaway 635-file sync wastes tokens and blocks pipeline |
| Developer UX | Training overhead, user errors, lost confidence |
