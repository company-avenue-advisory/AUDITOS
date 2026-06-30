"""
File locking for safe concurrent Excel writes.

Prevents corruption when multiple processes write to the same .xlsx file.
Uses a separate .lock file to coordinate access.
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class FileLockError(Exception):
    """Raised when lock cannot be acquired."""
    pass


class ExcelFileLock:
    """
    Context manager for safe file locking.

    Usage:
      with ExcelFileLock(excel_path, timeout=10) as lock:
          wb = load_workbook(lock.file_path)
          # modify and save
          wb.save(lock.file_path)
    """

    def __init__(self, file_path: str, timeout: int = 30, poll_interval: float = 0.1):
        """
        Initialize lock.

        Args:
            file_path: Path to Excel file
            timeout: Max seconds to wait for lock
            poll_interval: Seconds between lock attempts
        """
        self.file_path = file_path
        self.lock_file_path = f"{file_path}.lock"
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.lock_acquired = False
        self.lock_time = None

    def acquire(self) -> None:
        """Acquire lock with timeout."""
        start_time = time.time()

        while True:
            if not os.path.exists(self.lock_file_path):
                try:
                    # Try to create lock file atomically
                    # Use os.open with O_CREAT|O_EXCL for atomic creation
                    fd = os.open(
                        self.lock_file_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                    with os.fdopen(fd, 'w') as f:
                        f.write(f"locked at {time.time()}\n")

                    self.lock_acquired = True
                    self.lock_time = time.time()
                    logger.debug(f"[FileLock] Acquired lock on {self.file_path}")
                    return

                except FileExistsError:
                    # Lock file exists, wait and retry
                    pass

            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                raise FileLockError(
                    f"Could not acquire lock on {self.file_path} after {self.timeout}s. "
                    f"Lock file exists: {self.lock_file_path}. "
                    f"Remove manually if process crashed."
                )

            time.sleep(self.poll_interval)

    def release(self) -> None:
        """Release lock."""
        if self.lock_acquired:
            try:
                if os.path.exists(self.lock_file_path):
                    os.remove(self.lock_file_path)
                    self.lock_acquired = False
                    logger.debug(f"[FileLock] Released lock on {self.file_path}")
            except Exception as e:
                logger.error(f"[FileLock] Error releasing lock: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


class ExcelAtomicWrite:
    """
    Safe atomic write to Excel file.

    Strategy:
      1. Write to temporary file
      2. Acquire lock
      3. Atomic rename (temp → final)
      4. Release lock

    This ensures the final file is always in a consistent state.
    """

    @staticmethod
    @contextmanager
    def atomic_write(file_path: str, timeout: int = 30):
        """
        Context manager for atomic Excel writes.

        Usage:
          with ExcelAtomicWrite.atomic_write(excel_path) as temp_path:
              wb = load_workbook(temp_path)
              wb.save(temp_path)
              # File automatically swapped in on exit
        """
        import tempfile

        # Create temp file in same directory (same filesystem)
        base_dir = os.path.dirname(file_path) or '.'
        os.makedirs(base_dir, exist_ok=True)

        temp_fd, temp_path = tempfile.mkstemp(
            suffix='.xlsx',
            prefix='.tmp_',
            dir=base_dir
        )
        os.close(temp_fd)

        try:
            yield temp_path

            # Copy original to backup if it exists
            backup_path = f"{file_path}.backup"
            if os.path.exists(file_path):
                try:
                    import shutil
                    shutil.copy2(file_path, backup_path)
                except Exception as e:
                    logger.warning(f"[ExcelAtomicWrite] Could not create backup: {e}")

            # Atomic swap with lock
            with ExcelFileLock(file_path, timeout=timeout):
                # On Windows, remove target first; on Unix, rename is atomic
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.error(f"[ExcelAtomicWrite] Could not remove old file: {e}")
                        raise

                os.rename(temp_path, file_path)
                logger.info(f"[ExcelAtomicWrite] Atomically wrote {file_path}")

        except Exception as e:
            # Clean up temp file on error
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass
            logger.error(f"[ExcelAtomicWrite] Write failed: {e}")
            raise


def cleanup_stale_locks(base_dir: str, max_age_hours: int = 24) -> int:
    """
    Clean up stale lock files (process crashed).

    Args:
        base_dir: Directory to scan for .lock files
        max_age_hours: Remove locks older than this

    Returns:
        Number of locks removed
    """
    import glob
    from datetime import datetime, timedelta

    removed = 0
    cutoff_time = time.time() - (max_age_hours * 3600)

    for lock_file in glob.glob(os.path.join(base_dir, '*.lock')):
        try:
            mtime = os.path.getmtime(lock_file)
            if mtime < cutoff_time:
                os.remove(lock_file)
                logger.warning(f"[FileLock] Removed stale lock: {lock_file}")
                removed += 1
        except Exception as e:
            logger.error(f"[FileLock] Error cleaning up {lock_file}: {e}")

    return removed
