import os
import sys
import json
import asyncio
from celery import Celery
from dotenv import load_dotenv

# Ensure the backend directory is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

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


@celery_app.task(name="tasks.sales_ingestion_task", bind=True, max_retries=1, time_limit=3600)
def sales_ingestion_task(self, tenant_id: str, tenant_slug: str,
                          excel_output_path: str, invoice_type: str = "sales",
                          model_config: dict = None) -> dict:
    """
    Self-resolving Sales ingestion sync — unlike google_drive_sync_task
    above (which takes a single google_drive_folder_id baked into the
    schedule forever), this resolves the CURRENT month's Drive folder at
    run time via drive_path_resolver.py + the tenant's
    data/drive_paths/{tenant_slug}.json config. A tenant onboarded this
    way never needs their schedule re-registered when a new month's
    folder is created - only initial setup (see
    scripts/setup_sales_ingestion_schedule.py) is a one-time step.

    Scheduled DAILY, not monthly: invoices trickle into Drive throughout
    the month (confirmed against real timestamps this session - June
    invoices arrived from the 2nd through the 30th, not all on day one),
    so ingestion needs to run frequently to stay current. "Monthly" only
    describes when a FILING happens after a period closes - that's a
    separate concern (reconciliation + GSTR-1 generation), not yet wired
    to run automatically after this task. That chaining depends on a
    review gate (a later phase) existing to check the output first -
    deliberately not done here to avoid auto-filing unreviewed data.

    If this month's folder doesn't exist in Drive yet (e.g. the client
    hasn't created it), this is logged clearly and treated as "nothing to
    ingest yet", not an error - the same convention
    drive_path_resolver.resolve_month_folder_id already establishes by
    returning None rather than raising.
    """
    from datetime import date
    from services.drive_path_resolver import load_tenant_path_config, resolve_month_folder_id
    from services.google_drive import GoogleDriveConnector
    from services.google_drive_sync import GoogleDriveSyncPipeline

    try:
        print(f"[Celery:sales_ingestion] Resolving current month's Drive folder for tenant '{tenant_slug}'...")
        cfg = load_tenant_path_config(tenant_slug)
        connector = GoogleDriveConnector(cfg.sales_root_folder_id)

        def lister(folder_id):
            return connector.list_files(file_types=None, folder_id=folder_id)

        folder_id = resolve_month_folder_id(lister, cfg, date.today())
        if not folder_id:
            msg = f"No Drive folder found yet for '{tenant_slug}'s current month - nothing to ingest."
            print(f"[Celery:sales_ingestion] {msg}")
            return {"status": "SKIPPED", "reason": msg}

        print(f"[Celery:sales_ingestion] Resolved folder {folder_id} - starting sync for tenant {tenant_id}")
        pipeline = GoogleDriveSyncPipeline(
            tenant_id=tenant_id,
            google_drive_folder_id=folder_id,
            excel_output_path=excel_output_path,
            invoice_type=invoice_type,
        )
        result = pipeline.run(model_config=model_config)
        print(f"[Celery:sales_ingestion] Sync completed for '{tenant_slug}': {json.dumps(result, default=str)}")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Celery:sales_ingestion] Failed for '{tenant_slug}': {e}")
        raise self.retry(exc=e, countdown=300)
