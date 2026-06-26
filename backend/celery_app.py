import os
import sys
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
    celery_app.conf.update(
        broker_url=broker_url,
        result_backend=broker_url,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        worker_hijack_root_logger=False,
        # Set a reasonable prefetch limit (e.g. 1 task per worker at a time)
        worker_prefetch_multiplier=1,
    )
else:
    # No broker URL configured (running in local fallback mode)
    pass

@celery_app.task(name="tasks.process_batch_task")
def process_batch_task(batch_id: str, tasks: list, model_config: dict, type_val: str):
    """
    Celery task wrapper that runs our asynchronous process_batch pipeline.
    """
    from async_tasks import process_batch
    print(f"Celery worker processing batch {batch_id} containing {len(tasks)} files.")
    
    try:
        # Run the async pipeline under asyncio event loop
        asyncio.run(process_batch(batch_id, tasks, model_config, type_val))
        print(f"Celery worker successfully processed batch {batch_id}.")
        return {"status": "SUCCESS", "batch_id": batch_id}
    except Exception as e:
        print(f"Error inside Celery worker for batch {batch_id}: {e}")
        import traceback
        traceback.print_exc()
        raise e
