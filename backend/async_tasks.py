import asyncio
import collections
import hashlib
import json
import os
import time
from database import SessionLocal
from models import InvoiceTask, TaskStatus, BatchJob, SalesLineItem, PurchaseLineItem
from invoice_processor import process_pdf, InvoiceExtractionResponse
from services.observability import ObsLogger, now_utc, calc_cost_inr
from services.gcs_storage import gcs_storage

# ---------------------------------------------------------------------------
# Redis PDF cache — keyed by SHA-256(file bytes) + invoice_type + model.
# TTL: 7 days. Eliminates re-extraction cost when the same PDF is re-uploaded.
# Uses the same Upstash Redis broker already configured for Celery.
# ---------------------------------------------------------------------------
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is None:
        broker_url = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")
        if broker_url:
            try:
                import redis as redis_lib
                _redis_client = redis_lib.from_url(broker_url, decode_responses=True, socket_connect_timeout=3)
                _redis_client.ping()
            except Exception as e:
                print(f"[PDF Cache] Redis unavailable: {e}. Cache disabled.")
                _redis_client = None
    return _redis_client


def _pdf_cache_key(file_path: str, invoice_type: str, model_config: dict) -> str:
    """SHA-256 of file bytes + type + model → deterministic cache key."""
    try:
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""
    model_key = json.dumps(model_config or {}, sort_keys=True)
    compound = f"{file_hash}:{invoice_type}:{model_key}"
    return f"auditOS:pdf_cache:{hashlib.sha256(compound.encode()).hexdigest()}"


def _cache_get(key: str) -> InvoiceExtractionResponse | None:
    if not key:
        return None
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        if raw:
            return InvoiceExtractionResponse(**json.loads(raw))
    except Exception:
        pass
    return None


def _cache_set(key: str, result: InvoiceExtractionResponse):
    if not key:
        return
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, 7 * 86400, result.model_dump_json())  # 7-day TTL
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Concurrency controls — defaults tuned for Gemini 2.5 Flash FREE tier
# (15 RPM limit), but env-driven so a paid key doesn't stay pinned to
# free-tier throughput. This was the single biggest wall-clock ceiling in
# the pipeline (confirmed: comment itself noted paid Flash allows ~3500 RPM
# while the hardcoded values kept every batch throttled to free-tier speed
# regardless of the actual API tier in use).
#
# llm_semaphore   : max simultaneous LLM threads in-flight across all batches.
#                   LLM_CONCURRENCY env var, default 3 (free-tier safe).
#
# RpmGuard        : sliding-window RPM limiter per model family.
#                   RPM_GEMINI_FLASH / RPM_GEMINI_PRO / RPM_GROQ / RPM_DEFAULT
#                   env vars, defaulting to the same free-tier-safe values as
#                   before. Falls back to no-op when provider is unknown.
# ---------------------------------------------------------------------------
llm_semaphore = asyncio.Semaphore(int(os.getenv("LLM_CONCURRENCY", "3")))


class RpmGuard:
    """
    Token-bucket style RPM limiter using a sliding deque of call timestamps.
    Thread-safe via asyncio lock — safe for concurrent coroutines.
    """
    def __init__(self, rpm: int):
        self._rpm = rpm
        self._window = 60.0
        self._calls: collections.deque = collections.deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            # Drop timestamps older than 60 s
            while self._calls and now - self._calls[0] >= self._window:
                self._calls.popleft()
            if len(self._calls) >= self._rpm:
                # Wait until the oldest call falls out of the window
                sleep_for = self._window - (now - self._calls[0]) + 0.05
                await asyncio.sleep(sleep_for)
                now = asyncio.get_event_loop().time()
                while self._calls and now - self._calls[0] >= self._window:
                    self._calls.popleft()
            self._calls.append(asyncio.get_event_loop().time())


# One guard per model family — shared across all concurrent coroutines.
# Env-driven: bump these once a paid tier is in use, instead of hand-editing
# code. Defaults match the previous hardcoded free-tier-safe values exactly.
_rpm_guards: dict[str, RpmGuard] = {
    "gemini-flash": RpmGuard(int(os.getenv("RPM_GEMINI_FLASH", "10"))),  # Free: 15 RPM limit; 10 = safe headroom. Paid Flash allows ~3500 RPM.
    "gemini-pro":   RpmGuard(int(os.getenv("RPM_GEMINI_PRO", "10"))),    # Free: 15 RPM
    "groq":         RpmGuard(int(os.getenv("RPM_GROQ", "18"))),          # Free: ~20 RPM effective
    "default":      RpmGuard(int(os.getenv("RPM_DEFAULT", "10"))),
}

def _get_rpm_guard(model_config: dict) -> RpmGuard:
    provider = (model_config or {}).get("provider", "")
    model    = (model_config or {}).get("model", "")
    if "groq" in provider:
        return _rpm_guards["groq"]
    if "pro" in model:
        return _rpm_guards["gemini-pro"]
    if "gemini" in provider or "gemini" in model or "google" in provider:
        return _rpm_guards["gemini-flash"]
    return _rpm_guards["default"]


async def extract_invoice_async(file_path: str, model_config: dict, invoice_type: str, logger=None):
    """
    Wraps the synchronous process_pdf in an async thread.
    Guarded by:
      1. Redis SHA-256 cache  — returns instantly if same PDF was processed before
      2. llm_semaphore        — caps total concurrent LLM threads
      3. RpmGuard             — sliding-window RPM limiter per model family
    """
    cache_key = _pdf_cache_key(file_path, invoice_type, model_config)
    cached = _cache_get(cache_key)
    if cached:
        print(f"[PDF Cache] HIT for {os.path.basename(file_path)} — skipping LLM extraction.")
        return cached

    rpm_guard = _get_rpm_guard(model_config)
    await rpm_guard.acquire()
    async with llm_semaphore:
        res = await asyncio.to_thread(process_pdf, file_path, model_config, invoice_type, logger=logger)
        _cache_set(cache_key, res)
        return res

async def process_batch(batch_id: str, tasks: list, model_config: dict, type_val: str):
    """
    Background task that processes an entire batch of invoices concurrently.
    Concurrency is governed by llm_semaphore (3 slots) + per-model RpmGuard.
    Stays safely under Gemini Flash free tier 15 RPM limit.
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

    # Resolve tenant_id from BatchJob for observability logs
    _tenant_id = None
    _db_tmp = SessionLocal()
    try:
        from models import BatchJob as _BJ
        _bj = _db_tmp.query(_BJ).filter(_BJ.id == batch_id).first()
        if _bj:
            _tenant_id = _bj.tenant_id
    except Exception:
        pass
    finally:
        _db_tmp.close()

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
            db_session=db,
            tenant_id=_tenant_id
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
            db_session=db,
            tenant_id=_tenant_id
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
            db_session=db,
            tenant_id=_tenant_id,
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
            #
            # recon_report is initialized to None here (not left undefined) so that
            # the observability calls further down — which read its status and
            # overall_confidence for the quality-score / flag / failure-tracking
            # payloads — have a well-defined "reconciliation did not complete"
            # value to report instead of raising a NameError or, worse, silently
            # falling through with a stale value from a previous loop iteration.
            recon_report = None
            try:
                import json as _json
                from core.reconciliation.engine import FinancialReconciliationEngine
                from core.schema import CanonicalInvoice
                from core.schema.tax import TaxSummary
                from core.schema.confidence import ProvenancedValue
                from core.schema.document import DocumentMetadata
                from core.schema.supplier import Supplier

                recon_engine = FinancialReconciliationEngine()

                def _tf(v): return ProvenancedValue(value=float(v or 0.0), confidence=0.9, sources=["async_task"])

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
                    supplier=Supplier(),
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

            # grounding_score previously a hardcoded 0.85 regardless of what the
            # reconciliation engine actually found. It now reflects the real
            # ReconciliationReport.overall_confidence when reconciliation
            # completed (Phase 4A above), and a low, explicit fallback (not a
            # false-confident default) when reconciliation itself failed to run —
            # a missing reconciliation result is itself evidence of a problem,
            # not a reason to report high confidence.
            recon_confidence = recon_report.overall_confidence if recon_report is not None else 0.3
            recon_status = recon_report.status if recon_report is not None else "RECONCILIATION_ERROR"

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
                grounding_score=recon_confidence
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
                raw_items=len(res.sales_items) + len(res.purchase_items),
                reconciliation_status=recon_status,
                reconciliation_confidence=recon_confidence
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
                stage_failed="reconciliation" if recon_report is None else None,
                error_type="RECONCILIATION_ERROR" if recon_report is None else None
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
            db_session=db,
            tenant_id=batch.tenant_id if batch else None
        )
    except Exception as e:
        print(f"Error logging batch metrics: {e}")
        
    db.close()
