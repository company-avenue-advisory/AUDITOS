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
import asyncio
import logging
import tempfile
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func
from database import SessionLocal
from models import (
    Tenant, InvoiceTask, BatchJob, TaskStatus, SalesLineItem, PurchaseLineItem,
    GoogleDriveFileTracker, GoogleDriveSyncJob
)
from services.duplicate_detector import _norm as _dup_norm

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

    def run(self, model_config: Dict = None, max_files: Optional[int] = None) -> Dict:
        """
        Execute the full sync pipeline.

        Args:
            max_files: Cap on how many new/changed files to actually process this
                run. Extraction is LLM-bound at ~80-90s/file, and the Celery task
                wrapping this has a hard time_limit=3600 (1 hour) — an unbounded
                run against a large folder (e.g. ~419 files, ~9-10 hours) would
                never finish; it gets killed mid-run by Celery's time limit,
                leaving files stuck in "processing" state. Passing a max_files
                keeps each run inside that budget; already-processed files are
                tracked via file_tracker dedup, so repeated triggers naturally
                page through the backlog a batch at a time. None = no cap
                (only safe for small folders / already-synced backlogs).

        Returns:
            Summary dict with statistics, including `remaining_files` when capped.
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

            # Step 1: List files from Google Drive (PDFs and ZIPs)
            logger.info("[GoogleDriveSync] Listing files from Google Drive...")
            drive_files = self.drive.list_files(file_types=["application/pdf", "application/zip", "application/x-zip-compressed"])
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

            # Cap this run's actual work to max_files (see docstring). The rest
            # stay unprocessed in Drive/untracked and will be picked up by the
            # next trigger — dedup means we never reprocess what's already done.
            files_to_run = files_to_process[:max_files] if max_files else files_to_process
            remaining_after_this_run = len(files_to_process) - len(files_to_run)
            if remaining_after_this_run > 0:
                logger.info(
                    f"[GoogleDriveSync] max_files={max_files}: processing {len(files_to_run)} of "
                    f"{len(files_to_process)} new/updated files this run, {remaining_after_this_run} remaining"
                )

            # Step 3: Download files, extract concurrently, then persist sequentially.
            #
            # Extraction (process_pdf -> Gemini) is the ~80-90s/file bottleneck;
            # everything else (DB writes on self.db, Excel appends) is fast and
            # NOT thread-safe to run concurrently against one shared session/
            # workbook. So downloads + DB/Excel bookkeeping stay sequential here,
            # while only the extraction step for plain PDFs runs concurrently,
            # bounded by the same llm_semaphore + RpmGuard already tuned in
            # async_tasks.py for the interactive upload pipeline — both pipelines
            # now share one real rate budget against Gemini's RPM limit instead
            # of each unknowingly competing for it.
            logger.info(f"[GoogleDriveSync] Processing {len(files_to_run)} files...")
            temp_dir = tempfile.mkdtemp(prefix="google_drive_sync_")

            zip_jobs: List[Dict] = []
            pdf_jobs: List[Dict] = []

            for drive_file in files_to_run:
                file_id = drive_file["id"]
                filename = drive_file["name"]
                md5 = drive_file.get("md5Checksum", "")
                modified_time = drive_file.get("modifiedTime", "")

                try:
                    logger.info(f"[GoogleDriveSync] Downloading {filename}...")
                    self.file_tracker.mark_as_processing(file_id, self.tenant_id, filename, md5, modified_time)

                    local_path = os.path.join(temp_dir, filename)
                    if not self.drive.download_file(file_id, filename, local_path):
                        raise Exception(f"Failed to download {filename}")

                    is_zip = filename.lower().endswith('.zip') or drive_file.get("mimeType") in ["application/zip", "application/x-zip-compressed"]

                    if is_zip:
                        zip_jobs.append({"drive_file": drive_file, "local_path": local_path})
                    else:
                        # Create the task row now (before extraction) so a failed
                        # extraction still leaves a FAILED task in the audit trail,
                        # same as the previous sequential behavior.
                        task = self._create_pending_task(filename)
                        pdf_jobs.append({"drive_file": drive_file, "local_path": local_path, "task": task})

                except Exception as e:
                    logger.error(f"[GoogleDriveSync] Error downloading {filename}: {e}")
                    self.file_tracker.mark_as_failed(file_id, str(e))
                    sync_job.failed_files += 1

            # Concurrent extraction phase — plain PDFs only.
            extraction_results: Dict[str, Tuple] = {}
            if pdf_jobs:
                extraction_results = asyncio.run(self._extract_batch_concurrent(pdf_jobs, model_config))

            # Sequential persistence phase — original order, DB/Excel writes.
            for job in pdf_jobs:
                drive_file = job["drive_file"]
                file_id = drive_file["id"]
                filename = drive_file["name"]
                task = job["task"]

                res, pre_recon_status, attempts_used, extract_error = extraction_results.get(
                    file_id, (None, None, 0, Exception("missing extraction result"))
                )

                if extract_error is not None:
                    logger.error(f"[GoogleDriveSync] Error processing {filename}: {extract_error}")
                    self.file_tracker.mark_as_failed(file_id, str(extract_error))
                    try:
                        task.status = TaskStatus.FAILED
                        task.error_message = str(extract_error)
                        self.db.commit()
                    except Exception:
                        pass
                    sync_job.failed_files += 1
                    continue

                try:
                    result = self._finish_invoice(task, filename, res, pre_recon_status, attempts_used)

                    if not result or not result.get("task_id"):
                        raise Exception(f"Failed to extract invoice from {filename}")

                    task_id = result["task_id"]

                    if result.get("is_duplicate"):
                        # Same (invoice_no, party_gstin, voucher_date) already exists
                        # for this tenant — do NOT append to Excel (would double-count
                        # the invoice in GST filings). Still counted as processed.
                        self.file_tracker.mark_as_completed(file_id, task_id)
                        self._set_tracker_status(file_id, "duplicate_skipped", result.get("duplicate_reason"))
                        logger.warning(f"[GoogleDriveSync] {filename} SKIPPED — duplicate of {result.get('duplicate_reason')}")
                        sync_job.processed_files += 1
                        continue

                    recon_status = result.get("recon_status")
                    if recon_status == "ERP_READY":
                        # Only reconciled, arithmetically-sound invoices go into the
                        # clean output Excel that feeds GSTR-1/ITC exports.
                        self._append_to_excel(task_id, filename)
                        self.file_tracker.mark_as_completed(file_id, task_id)
                    else:
                        # NEEDS_REVIEW / BLOCKED — line items don't reconcile against
                        # the invoice's own printed totals. Route to the review file
                        # instead of silently mixing unverified data into the main sheet.
                        self._append_to_review_excel(task_id, filename, recon_status)
                        self._set_tracker_status(file_id, "needs_review", recon_status)
                        logger.warning(f"[GoogleDriveSync] {filename} flagged {recon_status} — routed to review file, not main Excel")

                    sync_job.processed_files += 1

                except Exception as e:
                    logger.error(f"[GoogleDriveSync] Error processing {filename}: {e}")
                    self.file_tracker.mark_as_failed(file_id, str(e))
                    sync_job.failed_files += 1

            # Zip jobs stay sequential (rare path, and each zip can contain a
            # variable number of nested PDFs) — unchanged from before.
            for job in zip_jobs:
                drive_file = job["drive_file"]
                local_path = job["local_path"]
                file_id = drive_file["id"]
                filename = drive_file["name"]

                try:
                    from services.google_drive_zip import PDFExtractor
                    with open(local_path, "rb") as f:
                        zip_data = f.read()

                    extracted_pdfs = PDFExtractor.extract_nested_zips(zip_data, filename)
                    if not extracted_pdfs:
                        logger.info(f"[GoogleDriveSync] No PDFs found inside {filename}")
                        self.file_tracker.mark_as_completed(file_id, "no_pdfs_in_zip")
                        sync_job.processed_files += 1
                        continue

                    all_successful = True
                    for pdf in extracted_pdfs:
                        pdf_filename = pdf["filename"]
                        pdf_data = pdf["data"]

                        pdf_local_path = os.path.join(temp_dir, f"{uuid4().hex}_{os.path.basename(pdf_filename)}")
                        with open(pdf_local_path, "wb") as f:
                            f.write(pdf_data)

                        # Tag the nested filename inside the zip for Excel output
                        tagged_filename = f"{filename}/{pdf_filename}"
                        result = self._process_invoice(pdf_local_path, tagged_filename, model_config)

                        if not result or not result.get("task_id"):
                            logger.error(f"[GoogleDriveSync] Failed to extract invoice from {pdf_filename} inside {filename}")
                            all_successful = False
                            continue

                        task_id = result["task_id"]

                        if result.get("is_duplicate"):
                            logger.warning(f"[GoogleDriveSync] {tagged_filename} SKIPPED — duplicate of {result.get('duplicate_reason')}")
                            continue

                        recon_status = result.get("recon_status")
                        if recon_status == "ERP_READY":
                            self._append_to_excel(task_id, tagged_filename)
                        else:
                            self._append_to_review_excel(task_id, tagged_filename, recon_status)

                    if all_successful:
                        self.file_tracker.mark_as_completed(file_id, "zip_processed")
                    else:
                        self.file_tracker.mark_as_failed(file_id, "some_pdfs_failed_in_zip")

                    sync_job.processed_files += 1

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
            summary = self._build_summary(sync_job)
            summary["remaining_files"] = remaining_after_this_run
            return summary

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

    def _check_duplicate(self, invoice_no: str, party_gstin: str, voucher_date: str, exclude_task_id: str) -> Optional[str]:
        """
        Look for an existing SalesLineItem/PurchaseLineItem for this tenant with the
        same (invoice_no, party_gstin, voucher_date), belonging to a different task.
        Returns a human-readable description of the match, or None.

        Mirrors the key used by services/duplicate_detector.py's within-batch/
        cross-batch checks so the "same invoice re-uploaded under a different
        filename" case (confirmed to happen in real client Drive folders) is
        caught before it double-counts in Excel/GSTR exports.
        """
        inv_no = _dup_norm(invoice_no)
        if not inv_no:
            return None
        gstin = _dup_norm(party_gstin)

        for model in (SalesLineItem, PurchaseLineItem):
            match = (
                self.db.query(model)
                .join(InvoiceTask, model.task_id == InvoiceTask.id)
                .join(BatchJob, InvoiceTask.batch_id == BatchJob.id)
                .filter(
                    BatchJob.tenant_id == self.tenant_id,
                    InvoiceTask.id != exclude_task_id,
                    func.upper(func.trim(model.invoice_no)) == inv_no,
                    func.upper(func.trim(model.party_gstin)) == gstin,
                    model.voucher_date == voucher_date,
                )
                .first()
            )
            if match:
                other_task = self.db.query(InvoiceTask).filter(InvoiceTask.id == match.task_id).first()
                return f"invoice {inv_no} already processed in {other_task.file_name if other_task else match.task_id}"
        return None

    def _run_reconciliation(self, task, res) -> str:
        """
        Run the same FinancialReconciliationEngine used by the regular upload
        path (async_tasks.py) so Drive-synced invoices get the same accuracy
        gate: ERP_READY | NEEDS_REVIEW | BLOCKED based on whether the extracted
        line items actually sum to the invoice's own printed totals.
        """
        try:
            from core.reconciliation.engine import FinancialReconciliationEngine
            from core.reconciliation.adapter import build_canonical_invoice

            canonical = build_canonical_invoice(
                sales_items=res.sales_items,
                purchase_items=res.purchase_items,
                overall_taxable_value=res.overall_taxable_value,
                overall_cgst_amount=res.overall_cgst_amount,
                overall_sgst_amount=res.overall_sgst_amount,
                overall_igst_amount=res.overall_igst_amount,
                overall_total_invoice_value=res.overall_total_invoice_value,
                overall_round_off=getattr(res, "overall_round_off", 0.0),
                source="google_drive_sync",
            )
            recon_engine = FinancialReconciliationEngine()
            recon_report = recon_engine.reconcile(canonical)
            task.recon_status = recon_report.status
            task.recon_report_json = recon_report.model_dump_json(exclude_none=True)
            self.db.commit()
            return recon_report.status
        except Exception as e:
            logger.error(f"[GoogleDriveSync] Reconciliation error: {e}")
            # Fail closed: unknown reconciliation state is treated as needing review,
            # never silently treated as clean.
            task.recon_status = "NEEDS_REVIEW"
            self.db.commit()
            return "NEEDS_REVIEW"

    def _set_tracker_status(self, google_drive_id: str, status: str, detail: str = None):
        tracker = self.db.query(GoogleDriveFileTracker).filter(
            GoogleDriveFileTracker.google_drive_id == google_drive_id
        ).first()
        if tracker:
            tracker.processing_status = status
            if detail:
                tracker.error_message = str(detail)
            tracker.updated_at = datetime.utcnow()
            self.db.commit()

    MAX_EXTRACTION_ATTEMPTS = 3

    def _extract_with_retry(self, file_path: str, model_config: Dict, process_type: str, filename: str):
        """
        Extraction is not deterministic — the same PDF can produce a clean,
        reconciled result on one call and a garbled one (wrong column picked,
        line items missed) on the next (confirmed empirically: re-running the
        same invoice through process_pdf() twice gave ERP_READY once and
        BLOCKED with a ~3 lakh variance the next time).

        Re-run extraction up to MAX_EXTRACTION_ATTEMPTS times, checking
        reconciliation status after each attempt (without touching the DB),
        and stop as soon as one attempt reaches ERP_READY. If none do, return
        the attempt with the smallest total variance so the human reviewer
        gets the closest candidate, not an arbitrary one.

        Returns (res, recon_status, attempts_used).
        """
        from invoice_processor import process_pdf
        from core.reconciliation.engine import FinancialReconciliationEngine
        from core.reconciliation.adapter import build_canonical_invoice

        recon_engine = FinancialReconciliationEngine()
        best_res, best_status, best_variance = None, None, float("inf")

        for attempt in range(1, self.MAX_EXTRACTION_ATTEMPTS + 1):
            res = process_pdf(file_path, model_config or {}, process_type)
            try:
                canonical = build_canonical_invoice(
                    sales_items=res.sales_items,
                    purchase_items=res.purchase_items,
                    overall_taxable_value=res.overall_taxable_value,
                    overall_cgst_amount=res.overall_cgst_amount,
                    overall_sgst_amount=res.overall_sgst_amount,
                    overall_igst_amount=res.overall_igst_amount,
                    overall_total_invoice_value=res.overall_total_invoice_value,
                    overall_round_off=getattr(res, "overall_round_off", 0.0),
                    source="google_drive_sync_retry_probe",
                )
                report = recon_engine.reconcile(canonical)
                status = report.status
                variance = abs(report.variance_taxable or 0.0) + abs(report.variance_total or 0.0)
            except Exception as e:
                logger.error(f"[GoogleDriveSync] Reconciliation probe failed on attempt {attempt} for {filename}: {e}")
                status, variance = "NEEDS_REVIEW", float("inf")

            logger.info(f"[GoogleDriveSync] {filename} attempt {attempt}/{self.MAX_EXTRACTION_ATTEMPTS}: {status} (variance={variance:.2f})")

            if variance < best_variance:
                best_res, best_status, best_variance = res, status, variance

            if status == "ERP_READY":
                return res, status, attempt

        return best_res, best_status, self.MAX_EXTRACTION_ATTEMPTS

    async def _extract_batch_concurrent(self, jobs: List[Dict], model_config: Dict) -> Dict[str, Tuple]:
        """
        Run LLM extraction for multiple plain-PDF jobs concurrently, bounded by
        the same llm_semaphore + RpmGuard already tuned in async_tasks.py for
        the interactive upload pipeline. This is the only part of the sync that
        actually benefits from concurrency — DB/Excel writes are fast and stay
        sequential in run() (see _finish_invoice).

        jobs: list of {"drive_file": ..., "local_path": ..., "task": ...}
        Returns: {drive_file_id: (res, pre_recon_status, attempts_used, error)}
        """
        from async_tasks import llm_semaphore, _get_rpm_guard

        process_type = self.invoice_type if self.invoice_type != "both" else "both"
        rpm_guard = _get_rpm_guard(model_config or {})

        async def _run_one(job: Dict):
            drive_file = job["drive_file"]
            file_id = drive_file["id"]
            filename = drive_file["name"]
            local_path = job["local_path"]
            try:
                await rpm_guard.acquire()
                async with llm_semaphore:
                    res, status, attempts = await asyncio.to_thread(
                        self._extract_with_retry, local_path, model_config, process_type, filename
                    )
                logger.info(
                    f"[GoogleDriveSync] {filename}: extraction settled at {status} "
                    f"after {attempts} attempt(s)"
                )
                return file_id, (res, status, attempts, None)
            except Exception as e:
                logger.error(f"[GoogleDriveSync] Concurrent extraction failed for {filename}: {e}")
                return file_id, (None, None, 0, e)

        results = await asyncio.gather(*(_run_one(job) for job in jobs))
        return dict(results)

    def _create_pending_task(self, filename: str) -> InvoiceTask:
        """Create the BatchJob (if needed) + a PENDING InvoiceTask row ahead of
        extraction, so a failed extraction still leaves a FAILED task in the
        audit trail — matches the previous sequential behavior."""
        batch_id = f"sync_{self.tenant_id}_{datetime.now().strftime('%Y%m%d')}"

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
        return task

    def _process_invoice(self, file_path: str, filename: str, model_config: Dict = None) -> Dict:
        """
        Sequential extraction + persistence, used for PDFs pulled out of zip
        archives (rare enough not to be worth including in the concurrent
        batch — see _extract_batch_concurrent). Plain PDFs go through
        _create_pending_task + _extract_batch_concurrent + _finish_invoice
        instead (see run()).
        """
        task = self._create_pending_task(filename)
        process_type = self.invoice_type if self.invoice_type != "both" else "both"
        try:
            res, pre_recon_status, attempts_used = self._extract_with_retry(
                file_path, model_config, process_type, filename
            )
        except Exception as e:
            logger.error(f"[GoogleDriveSync] Error extracting {filename}: {e}")
            try:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                self.db.commit()
            except Exception:
                pass
            return None
        return self._finish_invoice(task, filename, res, pre_recon_status, attempts_used)

    def _finish_invoice(self, task: InvoiceTask, filename: str, res, pre_recon_status: str, attempts_used: int) -> Dict:
        """
        Persist an already-extracted invoice against an existing (PENDING)
        InvoiceTask row: write line items, run duplicate detection, then
        reconciliation. Split out from _process_invoice so extraction can run
        concurrently across files while these DB writes — which share
        self.db and are not thread-safe — stay sequential in run().

        Returns dict: {task_id, recon_status, is_duplicate, duplicate_reason}
        or None on hard failure.
        """
        task_id = task.id
        try:
            logger.info(
                f"[GoogleDriveSync] {filename}: extraction settled at {pre_recon_status} "
                f"after {attempts_used} attempt(s)"
            )

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

            # Duplicate check: same (invoice_no, party_gstin, voucher_date) already
            # exists for this tenant under a different task/filename.
            first_item = (res.sales_items or res.purchase_items or [None])[0]
            duplicate_reason = None
            if first_item is not None:
                duplicate_reason = self._check_duplicate(
                    first_item.invoice_no, first_item.party_gstin, first_item.voucher_date, task_id
                )

            if duplicate_reason:
                # Mark on the task itself (not just the file tracker) so generic export
                # endpoints querying InvoiceTask directly by batch_id can also exclude it.
                task.recon_status = "DUPLICATE"
                self.db.commit()
                return {"task_id": task_id, "recon_status": "DUPLICATE", "is_duplicate": True, "duplicate_reason": duplicate_reason}

            recon_status = self._run_reconciliation(task, res)
            return {"task_id": task_id, "recon_status": recon_status, "is_duplicate": False, "duplicate_reason": None}

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

    def _append_to_review_excel(self, task_id: str, source_filename: str, recon_status: str):
        """
        Append extraction results that failed reconciliation (NEEDS_REVIEW / BLOCKED)
        to a separate '_review.xlsx' file instead of the main output. Keeps unverified
        data out of anything that feeds GSTR-1/ITC exports until a human confirms it.
        """
        from services.excel_sync import ExcelSyncService

        try:
            task = self.db.query(InvoiceTask).filter(InvoiceTask.id == task_id).first()
            if not task:
                return

            if not hasattr(self, "_review_sales"):
                self._review_sales = ExcelSyncService(
                    self.excel_output_path.replace(".xlsx", "_review_sales.xlsx"), "sales"
                )
            if not hasattr(self, "_review_purchase"):
                self._review_purchase = ExcelSyncService(
                    self.excel_output_path.replace(".xlsx", "_review_purchase.xlsx"), "purchase"
                )

            tagged_filename = f"[{recon_status}] {source_filename}"
            if task.sales_items:
                self._review_sales.append_batch(task.sales_items, tagged_filename, is_sales=True)
            if task.purchase_items:
                self._review_purchase.append_batch(task.purchase_items, tagged_filename, is_sales=False)

            logger.info(f"[GoogleDriveSync] Routed {source_filename} ({recon_status}) to review Excel")

        except Exception as e:
            logger.error(f"[GoogleDriveSync] Error appending to review Excel: {e}")
            raise

    def _build_summary(self, sync_job) -> Dict:
        """Build summary of sync results, including batch_id for Excel download."""
        batch_id = f"sync_{sync_job.tenant_id}_{sync_job.sync_timestamp.strftime('%Y%m%d')}"

        tracker_rows = self.db.query(GoogleDriveFileTracker).filter(
            GoogleDriveFileTracker.tenant_id == sync_job.tenant_id
        ).all()
        duplicate_count = sum(1 for t in tracker_rows if t.processing_status == "duplicate_skipped")
        needs_review_count = sum(1 for t in tracker_rows if t.processing_status == "needs_review")

        return {
            "sync_job_id": sync_job.id,
            "batch_id": batch_id,
            "status": sync_job.status,
            "total_files_found": sync_job.total_files_found,
            "new_files": sync_job.new_files,
            "updated_files": sync_job.updated_files,
            "processed_files": sync_job.processed_files,
            "failed_files": sync_job.failed_files,
            "duplicate_files_skipped": duplicate_count,
            "needs_review_files": needs_review_count,
            "excel_output_path": sync_job.excel_output_path,
            "duration_seconds": (sync_job.completed_at - sync_job.sync_timestamp).total_seconds() if sync_job.completed_at else None,
        }
