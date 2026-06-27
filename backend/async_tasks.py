import asyncio
import os
import time
from database import SessionLocal
from models import InvoiceTask, TaskStatus, BatchJob, SalesLineItem, PurchaseLineItem
from invoice_processor import process_pdf, InvoiceExtractionResponse
from services.observability import ObsLogger, now_utc, calc_cost_inr
from services.gcs_storage import gcs_storage

# 🛑 CRITICAL ARCHITECTURE PIVOT 🛑
# Restrict concurrent LLM API calls to an absolute maximum of 20 at any given time.
llm_semaphore = asyncio.Semaphore(20)

async def extract_invoice_async(file_path: str, model_config: dict, invoice_type: str, logger=None):
    """Wraps the synchronous process_pdf in an async thread, guarded by the semaphore."""
    async with llm_semaphore:
        # asyncio.to_thread runs the synchronous pdfplumber & LLM logic in a background thread
        res = await asyncio.to_thread(process_pdf, file_path, model_config, invoice_type, logger=logger)
        return res

async def process_batch(batch_id: str, tasks: list, model_config: dict, type_val: str):
    """
    Background task that processes an entire batch of invoices concurrently.
    The internal semaphore ensures no more than 20 hit the API at once.
    """
    from ws_manager import manager
    total = len(tasks)
    completed_count = 0
    failed_count = 0
    progress_lock = asyncio.Lock()

    # Resolve model options
    if model_config:
        model_identifier = model_config.get("model") or os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
        api_provider = model_config.get("provider")
    else:
        model_identifier = "gemini-2.5-flash"
        api_provider = "google_native"
        
    api_endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/" if api_provider == "google_native" else ("https://openrouter.ai/api/v1" if api_provider == "openrouter" else "http://localhost:11434/v1")

    # Step 1a — Emit Batch Envelope
    db = SessionLocal()
    try:
        ObsLogger.emit_batch_envelope(
            batch_id=batch_id,
            session_id=batch_id,
            model_selected="auto" if not model_config else model_identifier,
            model_identifier=model_identifier,
            api_provider=api_provider,
            api_endpoint=api_endpoint,
            total_files=total,
            batch_type=type_val,
            environment="development",
            db_session=db
        )
    except Exception as e:
        print(f"Error logging batch envelope: {e}")
    finally:
        db.close()

    # Step 1b — Emit File Manifest
    files_meta = []
    for t in tasks:
        filename = os.path.basename(t["file_path"])
        size_bytes = os.path.getsize(t["file_path"]) if os.path.exists(t["file_path"]) else 0
        files_meta.append({
            "file_id": t["id"],
            "filename": filename,
            "size_bytes": size_bytes
        })
    db = SessionLocal()
    try:
        ObsLogger.emit_file_manifest(
            batch_id=batch_id,
            files_meta=files_meta,
            db_session=db
        )
    except Exception as e:
        print(f"Error logging file manifest: {e}")
    finally:
        db.close()

    batch_tasks_meta = []
    meta_lock = asyncio.Lock()

    async def broadcast_progress():
        async with progress_lock:
            msg = {
                "total": total,
                "completed": completed_count,
                "failed": failed_count,
                "status": "PROCESSING"
            }
            if completed_count + failed_count == total:
                msg["status"] = "COMPLETED"
        await manager.broadcast_to_batch(batch_id, msg)

    async def process_single_task(task_id: str, file_path: str):
        nonlocal completed_count, failed_count
        db = SessionLocal()
        task = db.query(InvoiceTask).filter(InvoiceTask.id == task_id).first()
        if not task:
            db.close()
            return
            
        task.status = TaskStatus.PROCESSING
        db.commit()

        started_task = now_utc()
        t_start = time.time()
        
        # Instantiate ObsLogger
        logger = ObsLogger(
            batch_id=batch_id,
            file_id=task_id,
            model_identifier=model_identifier,
            api_provider=api_provider,
            db_session=db
        )
        
        try:
            # If the local file is missing, pull it down from GCS
            if not os.path.exists(file_path) and gcs_storage.is_active():
                gcs_blob_name = f"batches/{batch_id}/{task.file_name}"
                gcs_storage.download_file(gcs_blob_name, file_path)
                
            res: InvoiceExtractionResponse = await extract_invoice_async(file_path, model_config, type_val, logger=logger)
            
            # Serialize the results to SQL rows
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
                    db.add(db_item)
                    
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
                    db.add(db_item)
            
            # Phase 4A: Run Financial Reconciliation Engine and persist audit report
            try:
                import json as _json
                from core.reconciliation.engine import FinancialReconciliationEngine
                from core.schema import CanonicalInvoice
                from core.schema.tax import TaxSummary, TaxField
                from core.schema.document import DocumentMetadata
                from core.schema.supplier import SupplierInfo

                recon_engine = FinancialReconciliationEngine()

                def _tf(v): return TaxField(value=float(v or 0.0), confidence=0.9, sources=["async_task"])

                tax_summary = TaxSummary(
                    taxable_value=_tf(res.overall_taxable_value),
                    cgst_amount=_tf(res.overall_cgst_amount),
                    sgst_amount=_tf(res.overall_sgst_amount),
                    igst_amount=_tf(res.overall_igst_amount),
                    cess_amount=_tf(0.0),
                    round_off=_tf(0.0),
                    grand_total=_tf(res.overall_total_invoice_value),
                )

                line_items_raw = []
                for it in res.sales_items:
                    line_items_raw.append({
                        "particulars": it.particulars, "hsn": it.hsn,
                        "taxable_value": it.taxable_value, "cgst_amount": it.cgst_amount,
                        "sgst_amount": it.sgst_amount, "igst_amount": it.igst_amount,
                        "total_invoice_value": it.total_invoice_value
                    })
                for it in res.purchase_items:
                    line_items_raw.append({
                        "particulars": it.particulars, "hsn": it.hsn,
                        "taxable_value": it.taxable_value, "cgst_amount": it.cgst_amount,
                        "sgst_amount": it.sgst_amount, "igst_amount": it.igst_amount,
                        "total_invoice_value": it.total_invoice_value
                    })

                canonical = CanonicalInvoice(
                    metadata=DocumentMetadata(invoice_no=None, voucher_date=None, voucher_type=None),
                    supplier=SupplierInfo(),
                    tax_summary=tax_summary,
                    line_items=line_items_raw,
                )
                recon_report = recon_engine.reconcile(canonical)
                task.recon_status = recon_report.status
                task.recon_report_json = recon_report.model_dump_json(exclude_none=True)
            except Exception as _re:
                print(f"[Recon4A] Error running reconciliation for task {task_id}: {_re}")

            task.status = TaskStatus.COMPLETED
            db.commit()

            # Emit final output saving stage log
            completed_output = now_utc()
            total_duration_ms = int((time.time() - t_start) * 1000)
            logger.emit_final_output(
                started_at=started_task,
                completed_at=completed_output,
                pipeline_total_ms=total_duration_ms,
                line_items_written=len(res.sales_items) + len(res.purchase_items),
                gstr1_rows=len(res.sales_items),
                gstr2b_rows=len(res.purchase_items),
                output_saved=True
            )

            # Compute cost
            cost_info = calc_cost_inr(
                model_identifier,
                res.prompt_tokens or 0,
                res.completion_tokens or 0
            )

            # Emit extraction context snapshot (Step 3)
            logger.emit_context_snapshot(
                filename=task.file_name,
                invoice_header={
                    "overall_taxable_value": res.overall_taxable_value,
                    "overall_cgst_amount": res.overall_cgst_amount,
                    "overall_sgst_amount": res.overall_sgst_amount,
                    "overall_igst_amount": res.overall_igst_amount,
                    "overall_total_invoice_value": res.overall_total_invoice_value
                },
                extraction_summary={
                    "sales_items_count": len(res.sales_items),
                    "purchase_items_count": len(res.purchase_items)
                },
                correction_meta=res.correction_meta or {}
            )

            # Reconcile variance and statutory math status
            variance = abs(res.overall_taxable_value + res.overall_cgst_amount + res.overall_sgst_amount + res.overall_igst_amount - res.overall_total_invoice_value)
            statutory_math_balanced = variance <= 2.0

            # Statutory GSTIN regex validator
            import re
            gstin_pattern = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
            gstin = res.sales_items[0].party_gstin if res.sales_items else (res.purchase_items[0].party_gstin if res.purchase_items else "")
            gstin_format_valid = bool(gstin_pattern.match(str(gstin))) if gstin else False

            # Check no IGST CGST conflict
            no_igst_cgst_conflict = True
            for item in res.sales_items:
                if (item.igst_amount or 0) > 0 and ((item.cgst_amount or 0) > 0 or (item.sgst_amount or 0) > 0):
                    no_igst_cgst_conflict = False
                    break
            for item in res.purchase_items:
                if (item.igst_amount or 0) > 0 and ((item.cgst_amount or 0) > 0 or (item.sgst_amount or 0) > 0):
                    no_igst_cgst_conflict = False
                    break

            # Step 5 — Emit Quality Score
            score = logger.emit_quality_score(
                filename=task.file_name,
                has_valid_items=len(res.sales_items) > 0 or len(res.purchase_items) > 0,
                jini_present=True,
                output_saved=True,
                total_cost_inr=cost_info["total_cost_inr"],
                page_count=res.total_pages or 1,
                statutory_math_balanced=statutory_math_balanced,
                variance_inr=variance,
                gstin_format_valid=gstin_format_valid,
                no_igst_cgst_conflict=no_igst_cgst_conflict,
                grounding_score=0.85
            )

            # Step 6 — Evaluate Flags
            flags = logger.evaluate_flags(
                filename=task.file_name,
                composite_score=score,
                correction_meta=res.correction_meta or {},
                json_parse_ok=True,
                statutory_math_balanced=statutory_math_balanced,
                gstin_format_valid=gstin_format_valid,
                no_igst_cgst_conflict=no_igst_cgst_conflict,
                total_cost_inr=cost_info["total_cost_inr"],
                batch_avg_cost=0.0,  # Batch average evaluated at batch level
                raw_items=len(res.sales_items) + len(res.purchase_items)
            )

            # Step 4a — Emit File Metrics
            logger.emit_file_metrics(
                filename=task.file_name,
                page_count=res.total_pages or 1,
                latency_breakdown={"llm_extraction_ms": res.latency_ms or 0},
                token_usage={"prompt_tokens": res.prompt_tokens or 0, "completion_tokens": res.completion_tokens or 0},
                model_identifier=model_identifier,
                correction_meta=res.correction_meta or {},
                llm_retries=res.total_retries or 0,
                stage_failed=None,
                error_type=None
            )

            # Step 7a — Emit Debug Record if Flagged
            if flags:
                logger.emit_debug_record(
                    filename=task.file_name,
                    flags=flags,
                    correction_meta=res.correction_meta or {},
                    line_items=len(res.sales_items) + len(res.purchase_items),
                    total_taxable=res.overall_taxable_value,
                    total_invoice=res.overall_total_invoice_value,
                    total_cost_inr=cost_info["total_cost_inr"],
                    batch_avg_cost=0.0,
                    composite_score=score,
                    output_saved=True,
                    trace_complete=True,
                    recommended_action="Review flagged records in database"
                )

            # Record metrics for final batch aggregation
            async with meta_lock:
                batch_tasks_meta.append({
                    "file_id": task_id,
                    "status": "ok",
                    "total_ms": total_duration_ms,
                    "cost_inr": cost_info["total_cost_inr"],
                    "corrections": sum([
                        res.correction_meta.get("gst_rates_snapped", 0),
                        res.correction_meta.get("subtotal_rows_dropped", 0),
                        res.correction_meta.get("unallocated_rows_injected", 0)
                    ]) if res.correction_meta else 0,
                    "unallocated_injected": bool(res.correction_meta.get("unallocated_rows_injected", 0)) if res.correction_meta else False,
                    "rates_snapped": res.correction_meta.get("gst_rates_snapped", 0) if res.correction_meta else 0
                })

            async with progress_lock:
                completed_count += 1
        except Exception as e:
            task.error_message = str(e)
            task.status = TaskStatus.FAILED
            db.commit()

            async with meta_lock:
                batch_tasks_meta.append({
                    "file_id": task_id,
                    "status": "failed",
                    "total_ms": int((time.time() - t_start) * 1000),
                    "cost_inr": 0.0,
                    "corrections": 0,
                    "unallocated_injected": False,
                    "rates_snapped": 0
                })

            async with progress_lock:
                failed_count += 1
        finally:
            db.close()
            await broadcast_progress()
            # We keep the temp file so the Side-by-Side viewer can display it
            pass

    # Create awaitable coroutines for all tasks in the batch
    coroutines = [process_single_task(t['id'], t['file_path']) for t in tasks]
    
    # Run them concurrently. The semaphore inside extract_invoice_async will throttle them.
    await asyncio.gather(*coroutines)
    
    # Check if batch is fully complete and update batch status
    db = SessionLocal()
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if batch:
        all_tasks = db.query(InvoiceTask).filter(InvoiceTask.batch_id == batch_id).all()
        completed = sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)
        if completed + failed == len(all_tasks) and len(all_tasks) > 0:
            batch.status = TaskStatus.COMPLETED
            db.commit()
            
    # Step 4b — Emit Batch Metrics & batch-level alerts
    try:
        ObsLogger.emit_batch_metrics(
            batch_id=batch_id,
            tasks_meta=batch_tasks_meta,
            model_identifier=model_identifier,
            api_provider=api_provider,
            db_session=db
        )
    except Exception as e:
        print(f"Error logging batch metrics: {e}")
        
    db.close()
