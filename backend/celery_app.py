import os
import sys
import json
import asyncio
from celery import Celery
from dotenv import load_dotenv

# Insert unconditionally: celery's import_from_cwd() runs this module inside
# cwd_in_path(), which temporarily puts cwd on sys.path and REMOVES it after --
# a `not in sys.path` guard silently no-ops (already present at that point)
# and leaves workers unable to resolve deferred in-task imports (async_tasks,
# services.*, database, models) once celery_app.py finishes loading.
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

# Load environment variables
env_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=env_path)

broker_url = os.getenv("CELERY_BROKER_URL")

celery_app = Celery("audit_os")

if broker_url:
    # Upstash Redis uses TLS (rediss://). Append ssl_cert_reqs so Celery can validate the URL.
    if broker_url.startswith("rediss://") and "ssl_cert_reqs" not in broker_url:
        broker_url = broker_url + ("&" if "?" in broker_url else "?") + "ssl_cert_reqs=CERT_NONE"
    import ssl
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE} if broker_url.startswith("rediss://") else {}
    celery_app.conf.update(
        broker_url=broker_url,
        result_backend=broker_url,
        broker_use_ssl=_ssl_opts or None,
        redis_backend_use_ssl=_ssl_opts or None,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        result_expires=3600,
        timezone="UTC",
        enable_utc=True,
        worker_hijack_root_logger=False,
        worker_prefetch_multiplier=1,
        worker_pool="solo" if sys.platform == "win32" else "prefork",
        task_routes={
            "tasks.ocr_extract_task": {"queue": "ocr"},
            "tasks.process_batch_task": {"queue": "default"},
            "tasks.google_drive_sync_task": {"queue": "default"},
            "tasks.sales_ingestion_task": {"queue": "drive_sync"},
            "tasks.purchase_ingestion_task": {"queue": "drive_sync"},
            "tasks.gstr2b_ingestion_task": {"queue": "drive_sync"},
        },
    )
    # Explicitly declare every queue task_routes references. Without this,
    # a worker started with no -Q flag (both render.yaml and
    # START_ALL_WINDOWS.bat run plain "celery -A celery_app worker") only
    # ever consumes the implicit default "celery" queue - task_routes alone
    # does NOT make a worker consume "default"/"ocr"/"drive_sync". Any task
    # routed to one of those queues would sit in Redis forever, never
    # picked up. Confirmed by inspecting both worker start commands: neither
    # passes -Q, and this file previously declared no task_queues at all.
    from kombu import Queue
    celery_app.conf.task_queues = (
        Queue("celery"), Queue("default"), Queue("ocr"), Queue("drive_sync"),
    )


def _load_beat_schedules() -> dict:
    """
    Load persistent beat schedules from backend/data/beat_schedules.json.
    Each entry written by setup_google_drive_sync.py becomes a live crontab schedule.
    """
    from celery.schedules import crontab

    schedule_file = os.path.join(backend_dir, "data", "beat_schedules.json")
    if not os.path.exists(schedule_file):
        return {}

    try:
        with open(schedule_file, encoding="utf-8") as f:
            registry = json.load(f)
    except Exception as e:
        print(f"[CeleryBeat] Warning: could not load beat_schedules.json — {e}")
        return {}

    schedules = {}
    for name, entry in registry.items():
        parts = entry.get("cron", "0 0 1 * *").split()
        if len(parts) != 5:
            print(f"[CeleryBeat] Skipping '{name}': invalid cron '{entry.get('cron')}'")
            continue
        minute, hour, dom, month, dow = parts
        schedules[name] = {
            "task": entry["task"],
            "schedule": crontab(
                minute=minute,
                hour=hour,
                day_of_month=dom,
                month_of_year=month,
                day_of_week=dow,
            ),
            "kwargs": entry.get("kwargs", {}),
            "options": entry.get("options", {}),
        }
        print(f"[CeleryBeat] Registered schedule '{name}' — cron: {entry.get('cron')}")

    return schedules


celery_app.conf.beat_schedule = _load_beat_schedules()


@celery_app.task(name="tasks.process_batch_task", bind=True, max_retries=2)
def process_batch_task(self, batch_id: str, tasks: list, model_config: dict, type_val: str):
    """Celery task that runs the async invoice extraction pipeline."""
    from async_tasks import process_batch
    print(f"[Celery:default] Processing batch {batch_id} — {len(tasks)} files.")
    try:
        asyncio.run(process_batch(batch_id, tasks, model_config, type_val))
        print(f"[Celery:default] Batch {batch_id} complete.")
        return {"status": "SUCCESS", "batch_id": batch_id}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise self.retry(exc=e, countdown=10)


@celery_app.task(name="tasks.ocr_extract_task", bind=True, max_retries=1,
                 soft_time_limit=120, time_limit=150)
def ocr_extract_task(self, pdf_bytes_b64: str, provider: str = "auto") -> str:
    """
    Dedicated OCR worker task — runs EasyOCR in the 'ocr' queue so heavy
    CPU-bound OCR jobs don't starve the default LLM extraction queue.

    soft_time_limit=120s raises SoftTimeLimitExceeded so the worker can
    clean up gracefully; hard time_limit=150s kills the process if needed.
    """
    import base64
    from services.document_core import ocr_extract
    try:
        pdf_bytes = base64.b64decode(pdf_bytes_b64)
        result = ocr_extract(pdf_bytes, provider=provider)
        return result
    except Exception as e:
        print(f"[Celery:ocr] OCR task failed: {e}")
        raise self.retry(exc=e, countdown=5)


@celery_app.task(name="tasks.google_drive_sync_task", bind=True, max_retries=1, time_limit=3600)
def google_drive_sync_task(self, tenant_id: str, google_drive_folder_id: str,
                           excel_output_path: str, invoice_type: str = "both",
                           model_config: dict = None) -> dict:
    """
    Scheduled sync task — monitors Google Drive for new/updated invoices,
    processes them, and appends results to Excel.

    Runs on the schedule registered via setup_google_drive_sync.py.
    Respects dedup via Google Drive file ID + md5Checksum.
    """
    from services.google_drive_sync import GoogleDriveSyncPipeline

    try:
        print(f"[Celery:google_drive_sync] Starting sync for tenant {tenant_id}")

        pipeline = GoogleDriveSyncPipeline(
            tenant_id=tenant_id,
            google_drive_folder_id=google_drive_folder_id,
            excel_output_path=excel_output_path,
            invoice_type=invoice_type
        )

        result = pipeline.run(model_config=model_config)
        print(f"[Celery:google_drive_sync] Sync completed: {json.dumps(result, default=str)}")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Celery:google_drive_sync] Sync failed: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


def _load_drive_path_config(tenant_id: str, tenant_slug: str):
    """
    Loads this tenant's self-resolving Drive-path config from the DB
    (models.GoogleDriveSyncConfig row, set via POST /api/google-drive-sync/config)
    - added 2026-07-09 so any tenant can configure Sales/Purchase/GSTR-2B
    ingestion from the Drive Sync UI instead of needing a hand-edited
    data/drive_paths/<slug>.json file on the server (which only ever
    existed for OneStack - the one tenant that got one by hand this
    session). Returns None if no config row exists yet, so callers can
    return a clean SKIPPED result instead of raising.
    """
    from database import SessionLocal
    from models import GoogleDriveSyncConfig
    from services.drive_path_resolver import load_tenant_path_config_from_db

    db = SessionLocal()
    try:
        cfg_row = db.query(GoogleDriveSyncConfig).filter(GoogleDriveSyncConfig.tenant_id == tenant_id).first()
        if not cfg_row:
            return None
        return load_tenant_path_config_from_db(cfg_row, tenant_slug)
    finally:
        db.close()


@celery_app.task(name="tasks.sales_ingestion_task", bind=True, max_retries=1, time_limit=3600)
def sales_ingestion_task(self, tenant_id: str, tenant_slug: str,
                          excel_output_path: str, invoice_type: str = "sales",
                          model_config: dict = None) -> dict:
    """
    Self-resolving Sales ingestion sync — unlike google_drive_sync_task
    above (which takes a single google_drive_folder_id baked into the
    schedule forever), this resolves the CURRENT month's Drive folder at
    run time via drive_path_resolver.py + the tenant's DB-backed
    GoogleDriveSyncConfig row (see _load_drive_path_config above). A
    tenant onboarded this way never needs their schedule re-registered
    when a new month's folder is created - only initial setup (via the
    Drive Sync page, or scripts/setup_sales_ingestion_schedule.py) is a
    one-time step.

    Scheduled DAILY, not monthly: invoices trickle into Drive throughout
    the month (confirmed against real timestamps this session - June
    invoices arrived from the 2nd through the 30th, not all on day one),
    so ingestion needs to run frequently to stay current. "Monthly" only
    describes when a FILING happens after a period closes - that's a
    separate concern (reconciliation + GSTR-1 generation).

    Chained automatically once a client sheet is found in the month's
    folder: GoogleDriveSyncPipeline.run() calls
    generate_period_review_for_tenant() (skip_if_pending=True) at the end
    of every run, producing a PENDING_REVIEW SalesPeriodReview a human
    still has to approve/reject before anything reaches a GST portal -
    the review gate (Phase 7) is what makes this safe to auto-run instead
    of just logging the client sheet's shape and stopping there.

    If this month's folder doesn't exist in Drive yet (e.g. the client
    hasn't created it), this is logged clearly and treated as "nothing to
    ingest yet", not an error - the same convention
    drive_path_resolver.resolve_month_folder_id already establishes by
    returning None rather than raising.
    """
    from datetime import date
    from services.drive_path_resolver import resolve_month_folder_id
    from services.google_drive import GoogleDriveConnector
    from services.google_drive_sync import GoogleDriveSyncPipeline

    try:
        print(f"[Celery:sales_ingestion] Resolving current month's Drive folder for tenant '{tenant_slug}'...")
        cfg = _load_drive_path_config(tenant_id, tenant_slug)
        if not cfg or not cfg.sales_root_folder_id:
            msg = f"No sales_root_folder_id configured for '{tenant_slug}' - nothing to ingest."
            print(f"[Celery:sales_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}
        connector = GoogleDriveConnector(cfg.sales_root_folder_id)

        def lister(folder_id):
            return connector.list_files(file_types=None, folder_id=folder_id)

        folder_id = resolve_month_folder_id(lister, cfg, date.today())
        if not folder_id:
            msg = f"No Drive folder found yet for '{tenant_slug}'s current month - nothing to ingest."
            print(f"[Celery:sales_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        period = date.today().strftime("%Y-%m")
        print(f"[Celery:sales_ingestion] Resolved folder {folder_id} - starting sync for tenant {tenant_id}, period {period}")
        pipeline = GoogleDriveSyncPipeline(
            tenant_id=tenant_id,
            google_drive_folder_id=folder_id,
            excel_output_path=excel_output_path,
            invoice_type=invoice_type,
            period=period,
        )
        result = pipeline.run(model_config=model_config)
        print(f"[Celery:sales_ingestion] Sync completed for '{tenant_slug}': {json.dumps(result, default=str)}")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Celery:sales_ingestion] Failed for '{tenant_slug}': {e}")
        raise self.retry(exc=e, countdown=300)


@celery_app.task(name="tasks.purchase_ingestion_task", bind=True, max_retries=1, time_limit=3600)
def purchase_ingestion_task(self, tenant_id: str, tenant_slug: str,
                             excel_output_path: str, model_config: dict = None) -> dict:
    """
    Self-resolving Purchase ingestion sync - same self-resolving-month-
    folder design as sales_ingestion_task above, but against
    cfg.purchase_root_folder_id instead of cfg.sales_root_folder_id, and
    always invoice_type="purchase" (a Purchase sync only ever walks the
    Purchase Drive tree; "both" doesn't apply here since Sales and
    Purchase are two separate root folders - a combined sync is two
    separate scheduled tasks, not one).

    Unlike Sales, Purchase invoices come from arbitrary vendors with no
    fixed template, organized into the vendor's own expense-category
    subfolders (HR, Telecom, Rental, ...) rather than document-type
    folders - GoogleDriveSyncPipeline routes this through
    walk_and_classify_purchase (see drive_classifier.py) instead of the
    Sales-tree walker once invoice_type="purchase" is set.

    No period/review-gate chaining here (period stays None) - Purchase
    has no reconciliation/filing/review-gate equivalent yet (Phase 0b is
    ingestion only); wiring one is a natural follow-on once that exists,
    matching how Sales' own auto-chain was only added once its review
    gate (Phase 7) did.
    """
    from datetime import date
    from services.drive_path_resolver import resolve_month_folder_id
    from services.google_drive import GoogleDriveConnector
    from services.google_drive_sync import GoogleDriveSyncPipeline

    try:
        print(f"[Celery:purchase_ingestion] Resolving current month's Drive folder for tenant '{tenant_slug}'...")
        cfg = _load_drive_path_config(tenant_id, tenant_slug)
        if not cfg or not cfg.purchase_root_folder_id:
            msg = f"No purchase_root_folder_id configured for '{tenant_slug}' - nothing to ingest."
            print(f"[Celery:purchase_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        connector = GoogleDriveConnector(cfg.purchase_root_folder_id)

        def lister(folder_id):
            return connector.list_files(file_types=None, folder_id=folder_id)

        folder_id = resolve_month_folder_id(lister, cfg, date.today(), root_folder_id=cfg.purchase_root_folder_id)
        if not folder_id:
            msg = f"No Drive folder found yet for '{tenant_slug}'s current Purchase month - nothing to ingest."
            print(f"[Celery:purchase_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        print(f"[Celery:purchase_ingestion] Resolved folder {folder_id} - starting sync for tenant {tenant_id}")
        pipeline = GoogleDriveSyncPipeline(
            tenant_id=tenant_id,
            google_drive_folder_id=folder_id,
            excel_output_path=excel_output_path,
            invoice_type="purchase",
        )
        result = pipeline.run(model_config=model_config)
        print(f"[Celery:purchase_ingestion] Sync completed for '{tenant_slug}': {json.dumps(result, default=str)}")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Celery:purchase_ingestion] Failed for '{tenant_slug}': {e}")
        raise self.retry(exc=e, countdown=300)


@celery_app.task(name="tasks.gstr2b_ingestion_task", bind=True, max_retries=1, time_limit=1800)
def gstr2b_ingestion_task(self, tenant_id: str, tenant_slug: str) -> dict:
    """
    Self-resolving GSTR-2B Drive-drop ingestion - Phase A automation
    (2026-07-08: full GSP/portal-API automation is a separate vendor/
    business decision, deferred as Phase B - see this session's
    conversation on GSP pricing). Finds this month's GSTR-2B JSON
    file(s) in cfg.gstr2b_root_folder_id/<month folder>, parses and
    reconciles each against this tenant's PurchaseLineItem records for
    the period, and creates a PENDING_REVIEW PurchaseGstr2bReview per
    GSTIN found - a human still approves/rejects before anything feeds a
    GSTR-3B ITC claim, same review-gate pattern Sales uses (Phase 7).

    Someone still has to download the GSTR-2B JSON from the GST portal
    by hand each month and drop it in this folder - this task only
    automates what happens after that (parsing + reconciling + creating
    a reviewable record), not the portal download itself.

    A month folder can hold more than one .json (OneStack has two
    registrations - MH and HR - each gets its own GSTR-2B statement);
    every file found is processed independently, keyed by the GSTIN read
    out of its own content (see gstr2b_ingest.extract_recipient_gstin).
    """
    import tempfile
    from datetime import date
    from database import SessionLocal
    from services.drive_path_resolver import resolve_month_folder_id
    from services.google_drive import GoogleDriveConnector
    from services.gstr2b_ingest import extract_recipient_gstin, list_gstr2b_json_files
    from services.purchase_review import generate_review_for_tenant

    try:
        print(f"[Celery:gstr2b_ingestion] Resolving current month's GSTR-2B Drive folder for tenant '{tenant_slug}'...")
        cfg = _load_drive_path_config(tenant_id, tenant_slug)
        if not cfg or not cfg.gstr2b_root_folder_id:
            msg = f"No gstr2b_root_folder_id configured for '{tenant_slug}' - nothing to ingest."
            print(f"[Celery:gstr2b_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        connector = GoogleDriveConnector(cfg.gstr2b_root_folder_id)

        def lister(folder_id):
            return connector.list_files(file_types=None, folder_id=folder_id)

        folder_id = resolve_month_folder_id(lister, cfg, date.today(), root_folder_id=cfg.gstr2b_root_folder_id)
        if not folder_id:
            msg = f"No Drive folder found yet for '{tenant_slug}'s current GSTR-2B month - nothing to ingest."
            print(f"[Celery:gstr2b_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        json_files = list_gstr2b_json_files(lister, folder_id)
        if not json_files:
            msg = f"No .json files found in '{tenant_slug}'s current GSTR-2B month folder yet."
            print(f"[Celery:gstr2b_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        period = date.today().strftime("%Y-%m")
        temp_dir = tempfile.mkdtemp(prefix="gstr2b_ingest_")
        db = SessionLocal()
        results = []
        try:
            for jf in json_files:
                local_path = f"{temp_dir}/{jf['name']}"
                if not connector.download_file(jf["id"], jf["name"], local_path):
                    print(f"[Celery:gstr2b_ingestion] Failed to download {jf['name']}, skipping.")
                    results.append({"file": jf["name"], "status": "DOWNLOAD_FAILED"})
                    continue

                import json as _json
                with open(local_path, "r", encoding="utf-8") as f:
                    raw = _json.load(f)
                gstin = extract_recipient_gstin(raw)
                if not gstin:
                    print(f"[Celery:gstr2b_ingestion] Could not determine recipient GSTIN from {jf['name']}, skipping.")
                    results.append({"file": jf["name"], "status": "GSTIN_NOT_FOUND"})
                    continue

                review, created = generate_review_for_tenant(
                    db, tenant_id, period, gstin, local_path, skip_if_pending=True,
                )
                print(
                    f"[Celery:gstr2b_ingestion] {jf['name']} (GSTIN {gstin}): "
                    f"{'created new' if created else 'skipped, already pending'} review {review.id}"
                )
                results.append({
                    "file": jf["name"], "gstin": gstin, "status": "OK",
                    "created": created, "review_id": review.id,
                })
        finally:
            db.close()

        return {"status": "COMPLETED", "period": period, "results": results}

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Celery:gstr2b_ingestion] Failed for '{tenant_slug}': {e}")
        raise self.retry(exc=e, countdown=300)
