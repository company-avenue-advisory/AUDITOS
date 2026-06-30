import os
from fastapi import BackgroundTasks
from dotenv import load_dotenv

# Ensure env is loaded
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=env_path)

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_ACTIVE = bool(CELERY_BROKER_URL)

# Log dispatch mode at import time so it's visible in server startup logs
if CELERY_ACTIVE:
    print(f"[TaskQueue] Celery ACTIVE — broker: {CELERY_BROKER_URL[:40]}...")
else:
    print("[TaskQueue] WARNING: CELERY_BROKER_URL not set. Using in-process BackgroundTasks (NOT production-safe).")


def check_celery_workers() -> dict:
    """
    Pings the Celery broker and checks for active workers.
    Returns a dict with 'active', 'worker_count', and 'error' keys.
    """
    if not CELERY_ACTIVE:
        return {"active": False, "worker_count": 0, "error": "CELERY_BROKER_URL not configured"}
    try:
        from celery_app import celery_app
        inspector = celery_app.control.inspect(timeout=3.0)
        ping_result = inspector.ping()
        if ping_result:
            return {"active": True, "worker_count": len(ping_result), "error": None}
        return {"active": False, "worker_count": 0, "error": "No workers responded to ping"}
    except Exception as e:
        return {"active": False, "worker_count": 0, "error": str(e)}


def dispatch_batch_task(background_tasks: BackgroundTasks, batch_id: str, tasks: list, model_config: dict, type_val: str) -> str:
    """
    Dispatches a batch processing task to Celery if active, or falls back to FastAPI BackgroundTasks.
    Returns "celery" or "local" to indicate the dispatch target.

    IMPORTANT: Celery is the production path. The BackgroundTasks fallback is for local dev only.
    If CELERY_BROKER_URL is set but workers aren't running, tasks will queue in Redis but not execute.
    Monitor /api/health/workers to verify workers are alive.
    """
    if CELERY_ACTIVE:
        try:
            from celery_app import process_batch_task
            process_batch_task.delay(batch_id, tasks, model_config, type_val)
            print(f"[TaskQueue] Enqueued batch {batch_id} ({len(tasks)} files) → Celery.")
            return "celery"
        except Exception as e:
            print(f"[TaskQueue] ERROR: Failed to enqueue to Celery: {e}. Falling back to BackgroundTasks (data at risk if process restarts).")

    from async_tasks import process_batch
    background_tasks.add_task(process_batch, batch_id, tasks, model_config, type_val)
    print(f"[TaskQueue] Enqueued batch {batch_id} ({len(tasks)} files) → local BackgroundTasks.")
    return "local"
