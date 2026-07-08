"""
Google Drive auto-sync pipeline — the orchestrator.

Workflow:
  1. Recursively walk the Drive folder and classify every file
     (invoice / credit_note / client_sheet / ignore / unknown) - see
     drive_classifier.py. Folder location is the classification signal,
     never the filename (proven unreliable against OneStack's real tree).
  2. INVOICE files go through the existing extraction pipeline. CREDIT_NOTE
     files go through invoice_processor.extract_credit_note (a separate,
     deterministic path - never through the invoice extractor, which would
     misparse them the same way the discount-line bug did). Buyer GSTIN is
     resolved by looking up the credit note's Original Invoice Number
     against this tenant's own past invoices; if that invoice isn't on
     record, the credit note is still stored (GSTIN left blank) rather than
     lost, flagged for manual resolution - never a fabricated GSTIN.
     CLIENT_SHEET is still just tracked - no parser exists yet.
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
from services.drive_classifier import walk_and_classify, DocumentType, ClassifiedFile

logger = logging.getLogger(__name__)


class GoogleDriveSyncPipeline:
    """
    Main orchestrator for Google Drive to Excel sync.
    """

    def __init__(self, tenant_id: str, google_drive_folder_id: str,
                 excel_output_path: str, invoice_type: str = "both",
                 period: str = None):
        """
        Initialize sync pipeline.

        Args:
            tenant_id: Tenant ID to sync for
            google_drive_folder_id: Google Drive folder ID containing invoices
            excel_output_path: Path where Excel file should be saved
            invoice_type: "sales", "purchase", or "both"
            period: "YYYY-MM" for the month this folder represents. When
                set (only passed by sales_ingestion_task's scheduled runs -
                the legacy google_drive_sync_task still passes None), a
                SalesPeriodReview is generated automatically at the end of
                run() once a client sheet is found, via the same
                generate_period_review_for_tenant() the manual
                /api/sales/period-reviews/generate endpoint uses. Left None
                to skip - a folder without a known period (or a
                purchase-only sync, where reconciliation doesn't apply)
                shouldn't try to auto-generate a review.
        """
        from services.google_drive import GoogleDriveConnector, GoogleDriveFileTracker as DBTracker
        from services.excel_sync import ExcelSyncService

        self.tenant_id = tenant_id
        self.google_drive_folder_id = google_drive_folder_id
        self.excel_output_path = excel_output_path
        self.invoice_type = invoice_type
        self.period = period

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

            # Step 1: Recursively walk the Drive folder and classify every file
            logger.info("[GoogleDriveSync] Walking and classifying Drive folder tree...")
            classified_files = self._discover_and_classify()
            sync_job.total_files_found = len(classified_files)
            self.db.commit()

            invoice_files = [f for f in classified_files if f.document_type == DocumentType.INVOICE]
            credit_note_files = [f for f in classified_files if f.document_type == DocumentType.CREDIT_NOTE]
            client_sheet_files = [f for f in classified_files if f.document_type == DocumentType.CLIENT_SHEET]
            unknown_files = [f for f in classified_files if f.document_type == DocumentType.UNKNOWN]

            logger.info(
                f"[GoogleDriveSync] Classified {len(classified_files)} files: "
                f"{len(invoice_files)} invoice, {len(credit_note_files)} credit_note, "
                f"{len(client_sheet_files)} client_sheet, {len(unknown_files)} unknown"
            )
            for f in unknown_files:
                logger.warning(f"[GoogleDriveSync] UNKNOWN document type, not processed: {'/'.join(f.path)}/{f.name}")

            # Credit notes now have an extractor - process them.
            temp_dir_cn = tempfile.mkdtemp(prefix="google_drive_sync_cn_")
            cn_processed, cn_failed = self._process_credit_note_files(credit_note_files, temp_dir_cn, sync_job)

            # Client sheet now has a parser - parse and log a summary. Not
            # persisted to the DB yet: there's no reconciliation engine (a
            # later phase) to consume it, and its storage schema should be
            # designed against what that engine actually needs, not guessed
            # now. Parsing here at least proves the parser against the real
            # file every run and surfaces its shape immediately.
            self._log_client_sheet_summary(client_sheet_files)

            # Auto-generate a period review now (not persisted purely by
            # side effect of ingestion - see _maybe_generate_period_review)
            # so it reflects this run's newly-ingested rows too, and runs
            # regardless of whether there are new invoice files below (a
            # client sheet arriving after all invoices were already synced
            # is exactly the case this needs to still catch).
            self._period_review_result = self._maybe_generate_period_review()

            # stashed on self so _build_summary() can include them from every
            # return point in this method without threading them through each one
            self._credit_notes_found = len(credit_note_files)
            self._credit_notes_processed = cn_processed
            self._credit_notes_failed = cn_failed
            self._client_sheets_found = len(client_sheet_files)
            self._unknown_found = len(unknown_files)

            drive_files = invoice_files

            if not drive_files:
                logger.warning("[GoogleDriveSync] No invoice files found in Google Drive folder")
                sync_job.status = "completed"
                sync_job.completed_at = datetime.utcnow()
                self.db.commit()
                return self._build_summary(sync_job)

            # Step 2: Identify new/changed files
            logger.info("[GoogleDriveSync] Checking which files are new or updated...")
            files_to_process = []
            for drive_file in drive_files:
                file_id = drive_file.id
                md5 = drive_file.md5_checksum or ""

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
                    file_id = drive_file.id
                    filename = drive_file.name
                    md5 = drive_file.md5_checksum or ""
                    modified_time = drive_file.modified_time or ""

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

    def _discover_and_classify(self) -> List[ClassifiedFile]:
        """
        Recursively walks self.google_drive_folder_id and classifies every
        file found. Kept as its own method (pure w.r.t. the rest of the
        pipeline - only touches self.drive.list_files) so it can be unit
        tested against a fixture lister without live Drive credentials,
        DB, or Celery.
        """
        def lister(folder_id: str):
            return self.drive.list_files(file_types=None, folder_id=folder_id)
        return walk_and_classify(lister, self.google_drive_folder_id)

    def _track_unprocessed(self, files: List[ClassifiedFile], reason: str):
        """
        Logs files found this run without writing anything to the dedup
        tracker DB. Deliberately not marking them "seen" - once whatever's
        missing (an extractor, a downstream consumer) exists, they must
        still be picked up on the next run, not silently skipped because
        an earlier run already saw the file.
        """
        for f in files:
            location = "/".join(f.path) if f.path else "(month root)"
            logger.info(f"[GoogleDriveSync] Found but not yet processed ({reason}): {location}/{f.name}")

    def _log_client_sheet_summary(self, client_sheet_files: List[ClassifiedFile]):
        """
        Downloads and parses each classified client-sheet file, logging a
        summary (row counts, doc-type split), and stashes the local path of
        the last one successfully parsed on self._client_sheet_local_path
        for _maybe_generate_period_review() to reconcile against. Not
        marked "seen" in the dedup tracker: every run must still re-surface
        the client sheet, since it's the reconciliation input, not a
        document to ingest once and forget.
        """
        from services.client_sheet_parser import parse_client_sheet

        self._client_sheet_local_path = None
        for cf in client_sheet_files:
            location = "/".join(cf.path) if cf.path else "(month root)"
            try:
                temp_dir = tempfile.mkdtemp(prefix="google_drive_sync_cs_")
                local_path = os.path.join(temp_dir, cf.name)
                if not self.drive.download_file(cf.id, cf.name, local_path):
                    raise Exception(f"Failed to download {cf.name}")
                rows = parse_client_sheet(local_path)
                invoices = sum(1 for r in rows if r["doc_type"] == "Invoice")
                credit_notes = sum(1 for r in rows if r["doc_type"] == "Credit Note")
                logger.info(
                    f"[GoogleDriveSync] Parsed client sheet {location}/{cf.name}: "
                    f"{len(rows)} rows ({invoices} invoice, {credit_notes} credit note)"
                )
                self._client_sheet_local_path = local_path
            except Exception as e:
                logger.error(f"[GoogleDriveSync] Error parsing client sheet {cf.name}: {e}")

    def _maybe_generate_period_review(self) -> dict:
        """
        Generates a SalesPeriodReview for self.period if a client sheet was
        found this run and a period was given at construction time (only
        true for the scheduled sales_ingestion_task path - see __init__).
        skip_if_pending=True: a daily scheduled sync shouldn't pile up a
        fresh unreviewed row every day while a human hasn't acted on
        yesterday's yet.
        """
        if not self.period or not getattr(self, "_client_sheet_local_path", None):
            return {"attempted": False}

        from services.period_review import generate_period_review_for_tenant

        try:
            review, created = generate_period_review_for_tenant(
                self.db, self.tenant_id, self.period,
                self._client_sheet_local_path, skip_if_pending=True,
            )
            logger.info(
                f"[GoogleDriveSync] Period review for {self.period}: "
                f"{'created new' if created else 'skipped, already pending'} review {review.id}"
            )
            return {"attempted": True, "created": created, "review_id": review.id}
        except Exception as e:
            logger.error(f"[GoogleDriveSync] Failed to auto-generate period review for {self.period}: {e}")
            return {"attempted": True, "created": False, "error": str(e)}

    def _process_credit_note_files(self, credit_note_files: List[ClassifiedFile],
                                    temp_dir: str, sync_job) -> Tuple[int, int]:
        """
        Downloads and stores each classified credit-note file via the
        shared credit_note_ingest module (also used by main.py's zip
        upload path, so GSTIN resolution and SalesLineItem construction
        don't drift between the two entry points). Returns
        (processed_count, failed_count).

        voucher_type="Credit Note" is what classify_gstr1_item already
        keys off to route these into CDNR/CDNUR in gstr1_generator.py -
        no new downstream plumbing needed for the ones with a resolvable
        GSTIN.
        """
        from services.credit_note_ingest import ingest_credit_note_pdf

        processed = 0
        failed = 0
        for cf in credit_note_files:
            file_id = cf.id
            filename = cf.name
            md5 = cf.md5_checksum or ""
            modified_time = cf.modified_time or ""

            if self.file_tracker.is_file_processed(file_id, md5):
                continue

            try:
                self.file_tracker.mark_as_processing(file_id, self.tenant_id, filename, md5, modified_time)

                local_path = os.path.join(temp_dir, filename)
                if not self.drive.download_file(file_id, filename, local_path):
                    raise Exception(f"Failed to download {filename}")

                batch_id = f"sync_{self.tenant_id}_{datetime.now().strftime('%Y%m%d')}"
                batch = self.db.query(BatchJob).filter(BatchJob.id == batch_id).first()
                if not batch:
                    batch = BatchJob(id=batch_id, tenant_id=self.tenant_id, total_files=0, status=TaskStatus.PENDING)
                    self.db.add(batch)
                    self.db.commit()

                task_id = ingest_credit_note_pdf(self.db, self.tenant_id, batch_id, local_path, filename)
                if not task_id:
                    raise Exception(f"{filename} classified as credit_note but 'Credit Note Number' not found in text")

                self.file_tracker.mark_as_completed(file_id, task_id)
                sync_job.processed_files += 1
                processed += 1

            except Exception as e:
                logger.error(f"[GoogleDriveSync] Error processing credit note {filename}: {e}")
                self.file_tracker.mark_as_failed(file_id, str(e))
                sync_job.failed_files += 1
                failed += 1

        self.db.commit()
        return processed, failed

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
        """Build summary of sync results, including batch_id for Excel download."""
        batch_id = f"sync_{sync_job.tenant_id}_{sync_job.sync_timestamp.strftime('%Y%m%d')}"
        return {
            "sync_job_id": sync_job.id,
            "batch_id": batch_id,
            "status": sync_job.status,
            "total_files_found": sync_job.total_files_found,
            "new_files": sync_job.new_files,
            "updated_files": sync_job.updated_files,
            "processed_files": sync_job.processed_files,
            "failed_files": sync_job.failed_files,
            "excel_output_path": sync_job.excel_output_path,
            "duration_seconds": (sync_job.completed_at - sync_job.sync_timestamp).total_seconds() if sync_job.completed_at else None,
            # not persisted on GoogleDriveSyncJob (no migration for this yet) -
            # in-memory only, so these don't survive a server restart mid-run
            "credit_notes_found": getattr(self, "_credit_notes_found", 0),
            "credit_notes_processed": getattr(self, "_credit_notes_processed", 0),
            "credit_notes_failed": getattr(self, "_credit_notes_failed", 0),
            "client_sheets_found": getattr(self, "_client_sheets_found", 0),
            "unknown_found": getattr(self, "_unknown_found", 0),
            "period_review": getattr(self, "_period_review_result", {"attempted": False}),
        }
