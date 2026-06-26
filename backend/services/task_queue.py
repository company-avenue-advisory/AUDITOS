import os
from fastapi import BackgroundTasks
from dotenv import load_dotenv

# Ensure env is loaded
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=env_path)

# Check if celery broker is active
CELERY_ACTIVE = bool(os.getenv("CELERY_BROKER_URL"))

def dispatch_batch_task(background_tasks: BackgroundTasks, batch_id: str, tasks: list, model_config: dict, type_val: str) -> str:
    """
    Dispatches a batch processing task to Celery if active, or falls back to FastAPI BackgroundTasks.
    Returns "celery" or "local" to indicate the dispatch target.
    """
    if CELERY_ACTIVE:
        try:
            from celery_app import process_batch_task
            # Enqueue task in Celery Redis queue
            process_batch_task.delay(batch_id, tasks, model_config, type_val)
            print(f"Successfully enqueued batch {batch_id} with {len(tasks)} files to Celery worker.")
            return "celery"
        except Exception as e:
            print(f"Failed to enqueue to Celery: {e}. Falling back to local BackgroundTasks.")
            # Fall through to local fallback
            
    # Fallback to FastAPI background task pool
    from async_tasks import process_batch
    background_tasks.add_task(process_batch, batch_id, tasks, model_config, type_val)
    print(f"Successfully enqueued batch {batch_id} with {len(tasks)} files to local background thread.")
    return "local"
