"""
Google Drive auto-sync pipeline — the orchestrator.

Workflow:
  1. List files from Google Drive folder
  2. Filter PDFs only (mime type: application/pdf)
  3. Check dedup database (track by id + md5Checksum)
  4. Download new/changed files
  5. Process through existing extraction pipeline
  6. Append results to Excel
  7. Update tracker database

Scheduled via Celery Beat (monthly or on-demand).
"""

import os
import logging
import tempfile
from typing import Dict, List, Tuple
from datetime import datetime
from uuid import uuid4

from database import SessionLocal
from models import (
    Tenant, InvoiceTask, BatchJob, TaskStatus, SalesLineItem, PurchaseLineItem,
    GoogleDriveFileTracker, GoogleDriveSyncJob
)

logger = logging.getLogger(__name__)


class GoogleDriveSyncPipeline:
    """
    Main orchestrator for Google Drive to Excel sync.
    """

    def __init__(self, tenant_id: str, google_drive_folder_id: str,
                 excel_output_path: str, invoice_type: str = "both"):
        """
        Initialize sync pipeline.

        Args:
            tenant_id: Tenant ID to sync for
            google_drive_folder_id: Google Drive folder ID containing invoices
            excel_output_path: Path where Excel file should be saved
            invoice_type: "sales", "purchase", or "both"
        """
        from services.google_drive import GoogleDriveConnector, GoogleDriveFileTracker as DBTracker
        from services.excel_sync import ExcelSyncService

        self.tenant_id = tenant_id
        self.google_drive_folder_id = google_drive_folder_id
        self.excel_output_path = excel_output_path
        self.invoice_type = invoice_type

        self.drive = GoogleDriveConnector(google_drive_folder_id)
        self.db = SessionLocal()
        self.file_tracker = DBTracker(self.db)

        # Excel sync services for sales and purchase
        if invoice_type in ["sales", "both"]:
            self.excel_sales = ExcelSyncService(excel_output_path.replace(".xlsx", "_sales.xlsx"), "sales")
        if invoice_type in ["purchase", "both"]:
            self.excel_purchase = ExcelSyncService(excel_output_path.replace(".xlsx", "_purchase.xlsx"), "purchase")

    def run(self, model_config: Dict = None) -> Dict:
        """
        Execute the full sync pipeline.

        Returns:
            Summary dict with statistics
        """
        sync_job_id = str(uuid4())
        start_time = datetime.utcnow()

        try:
            # Create sync job record
            sync_job = GoogleDriveSyncJob(
                id=sync_job_id,
                tenant_id=self.tenant_id,
                sync_timestamp=start_time,
                status="in_progress"
            )
            self.db.add(sync_job)
            self.db.commit()

            logger.info(f"[GoogleDriveSync] Starting sync job {sync_job_id} for tenant {self.tenant_id}")

            # Step 1: List files from Google Drive (PDFs only)
            logger.info("[GoogleDriveSync] Listing files from Google Drive...")
            drive_files = self.drive.list_files(file_types=["application/pdf"])
            sync_job.total_files_found = len(drive_files)
            self.db.commit()

            if not drive_files:
                logger.warning("[GoogleDriveSync] No PDF files found in Google Drive folder")
                sync_job.status = "completed"
                sync_job.completed_at = datetime.utcnow()
                self.db.commit()
                return self._build_summary(sync_job)

            # Step 2: Identify new/changed files
            logger.info("[GoogleDriveSync] Checking which files are new or updated...")
            files_to_process = []
            for drive_file in drive_files:
                file_id = drive_file["id"]
                md5 = drive_file.get("md5Checksum", "")

                if not self.file_tracker.is_file_processed(file_id, md5):
                    files_to_process.append(drive_file)
                    if self.file_tracker.db.query(GoogleDriveFileTracker).filter(
                        GoogleDriveFileTracker.google_drive_id == file_id
                    ).first():
                        sync_job.updated_files += 1
                    else:
                        sync_job.new_files += 1

            self.db.commit()
            logger.info(f"[GoogleDriveSync] {len(files_to_process)} new/updated files to process")

            if not files_to_process:
                logger.info("[GoogleDriveSync] No new files to process. Sync complete.")
                sync_job.status = "completed"
                sync_job.completed_at = datetime.utcnow()
                self.db.commit()
                return self._build_summary(sync_job)

            # Step 3: Download and process files
            logger.info(f"[GoogleDriveSync] Processing {len(files_to_process)} files...")
            temp_dir = tempfile.mkdtemp(prefix="google_drive_sync_")

            for drive_file in files_to_process:
                try:
                    file_id = drive_file["id"]
                    filename = drive_file["name"]
                    md5 = drive_file.get("md5Checksum", "")
                    modified_time = drive_file.get("modifiedTime", "")

                    logger.info(f"[GoogleDriveSync] Processing {filename}...")

                    # Mark as processing
                    self.file_tracker.mark_as_processing(file_id, self.tenant_id, filename, md5, modified_time)

                    # Download file
                    local_path = os.path.join(temp_dir, filename)
                    if not self.drive.download_file(file_id, filename, local_path):
                        raise Exception(f"Failed to download {filename}")

                    # Process through extraction pipeline
                    task_id = self._process_invoice(local_path, filename, model_config)

                    if task_id:
                        # Append to Excel
                        self._append_to_excel(task_id, filename)
                        self.file_tracker.mark_as_completed(file_id, task_id)
                        sync_job.processed_files += 1
                    else:
                        raise Exception(f"Failed to extract invoice from {filename}")

                except Exception as e:
                    logger.error(f"[GoogleDriveSync] Error processing {filename}: {e}")
                    self.file_tracker.mark_as_failed(file_id, str(e))
                    sync_job.failed_files += 1

            self.db.commit()

            # Step 4: Finalize sync job
            sync_job.status = "completed"
            sync_job.excel_output_path = self.excel_output_path
            sync_job.completed_at = datetime.utcnow()
            self.db.commit()

            logger.info(f"[GoogleDriveSync] Sync job {sync_job_id} completed successfully")
            return self._build_summary(sync_job)

        except Exception as e:
            logger.error(f"[GoogleDriveSync] Fatal error in sync job {sync_job_id}: {e}")
            try:
                sync_job.status = "failed"
                sync_job.error_message = str(e)
                sync_job.completed_at = datetime.utcnow()
                self.db.commit()
            except:
                pass
            raise

        finally:
            self.db.close()

    def _process_invoice(self, file_path: str, filename: str, model_config: Dict = None) -> str:
        """
        Process invoice through extraction pipeline.
        Returns task_id if successful, None otherwise.
        """
        from invoice_processor import process_pdf
        from services.observability import ObsLogger, now_utc, calc_cost_inr
        import time

        try:
            batch_id = f"sync_{self.tenant_id}_{datetime.now().strftime('%Y%m%d')}"

            # Create batch job if doesn't exist
            batch = self.db.query(BatchJob).filter(BatchJob.id == batch_id).first()
            if not batch:
                batch = BatchJob(
                    id=batch_id,
                    tenant_id=self.tenant_id,
                    total_files=0,
                    status=TaskStatus.PENDING
                )
                self.db.add(batch)
                self.db.commit()

            # Create task
            task_id = str(uuid4())
            task = InvoiceTask(
                id=task_id,
                batch_id=batch_id,
                file_name=filename,
                status=TaskStatus.PENDING,
                invoice_type=self.invoice_type
            )
            self.db.add(task)
            self.db.commit()

            # Process PDF
            logger.info(f"[GoogleDriveSync] Extracting {filename}...")
            t_start = time.time()

            # Determine invoice type for processing
            process_type = self.invoice_type if self.invoice_type != "both" else "both"

            res = process_pdf(file_path, model_config or {}, process_type)

            # Save extraction results to DB
            if res.sales_items:
                for item in res.sales_items:
                    db_item = SalesLineItem(
                        task_id=task.id,
                        voucher_date=item.voucher_date,
                        voucher_type=item.voucher_type,
                        invoice_no=item.invoice_no,
                        party_ledger_name=item.party_ledger_name,
                        party_gstin=item.party_gstin,
                        place_of_supply=item.place_of_supply,
                        particulars=item.particulars,
                        hsn=item.hsn,
                        qty=item.qty,
                        rate=item.rate,
                        taxable_value=item.taxable_value,
                        discount=item.discount,
                        advances=item.advances,
                        cgst_amount=item.cgst_amount,
                        sgst_amount=item.sgst_amount,
                        igst_amount=item.igst_amount,
                        total_invoice_value=item.total_invoice_value,
                        gstr1_category=item.gstr1_category,
                        narration=item.narration
                    )
                    self.db.add(db_item)

            if res.purchase_items:
                for item in res.purchase_items:
                    db_item = PurchaseLineItem(
                        task_id=task.id,
                        voucher_date=item.voucher_date,
                        voucher_type=item.voucher_type,
                        invoice_no=item.invoice_no,
                        party_ledger_name=item.party_ledger_name,
                        party_gstin=item.party_gstin,
                        place_of_supply=item.place_of_supply,
                        particulars=item.particulars,
                        hsn=item.hsn,
                        qty=item.qty,
                        rate=item.rate,
                        taxable_value=item.taxable_value,
                        cgst_amount=item.cgst_amount,
                        sgst_amount=item.sgst_amount,
                        igst_amount=item.igst_amount,
                        total_invoice_value=item.total_invoice_value,
                        itc_eligibility=item.itc_category,
                        narration=item.narration
                    )
                    self.db.add(db_item)

            task.status = TaskStatus.COMPLETED
            self.db.commit()

            logger.info(f"[GoogleDriveSync] Extracted {filename} in {time.time() - t_start:.2f}s")
            return task_id

        except Exception as e:
            logger.error(f"[GoogleDriveSync] Error processing {filename}: {e}")
            try:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                self.db.commit()
            except:
                pass
            return None

    def _append_to_excel(self, task_id: str, source_filename: str):
        """
        Append extraction results from task to Excel file.
        """
        try:
            task = self.db.query(InvoiceTask).filter(InvoiceTask.id == task_id).first()
            if not task:
                return

            # Append sales items
            if hasattr(self, 'excel_sales') and task.sales_items:
                self.excel_sales.append_batch(task.sales_items, source_filename, is_sales=True)

            # Append purchase items
            if hasattr(self, 'excel_purchase') and task.purchase_items:
                self.excel_purchase.append_batch(task.purchase_items, source_filename, is_sales=False)

            logger.info(f"[GoogleDriveSync] Appended results from {source_filename} to Excel")

        except Exception as e:
            logger.error(f"[GoogleDriveSync] Error appending to Excel: {e}")
            raise

    def _build_summary(self, sync_job) -> Dict:
        """Build summary of sync results."""
        return {
            "sync_job_id": sync_job.id,
            "status": sync_job.status,
            "total_files_found": sync_job.total_files_found,
            "new_files": sync_job.new_files,
            "updated_files": sync_job.updated_files,
            "processed_files": sync_job.processed_files,
            "failed_files": sync_job.failed_files,
            "excel_output_path": sync_job.excel_output_path,
            "duration_seconds": (sync_job.completed_at - sync_job.sync_timestamp).total_seconds() if sync_job.completed_at else None
        }
