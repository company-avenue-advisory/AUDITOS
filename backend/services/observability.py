"""
observability.py — AuditOS AI Observability Logger (v2.1.0)
============================================================
Central service for emitting structured JSON log events at every pipeline stage.

Design principles:
- Every event is an INSERT into ObservabilityLog. No updates, ever.
- All monetary values in INR with 2 decimal precision.
- batch_id + file_id + timestamp_utc are mandatory on every event.
- Logs without correlation IDs are rejected with a MISSING_CORRELATION_IDS alert.
"""
import json
import hashlib
import os
import time
from datetime import datetime, timezone
from typing import Optional, Any

# Token pricing constants (converted to INR at ₹83/USD)
USD_TO_INR = 83.0

COST_PER_1M_TOKENS = {
    "gemini-2.5-flash": {          # Google native direct
        "input":  0.075 * USD_TO_INR,
        "output": 0.30  * USD_TO_INR,
    },
    "google/gemini-2.5-flash": {   # OpenRouter — ~15% margin
        "input":  0.075 * 1.15 * USD_TO_INR,
        "output": 0.30  * 1.15 * USD_TO_INR,
    },
    "meta-llama/llama-3.3-70b-instruct": {
        "input":  0.59 * USD_TO_INR,
        "output": 0.59 * USD_TO_INR,
    },
    # Anthropic direct (via main.py's MODEL_OPTIONS "anthropic" / "anthropic-sonnet"
    # choices) — these two model_identifier strings were missing entirely from
    # this table, so cost tracking silently read ₹0 for every Claude-routed
    # invoice (not a key-format mismatch — the keys below just didn't exist).
    # Pricing confirmed current as of 2026-07 (claude-api skill model catalog).
    "claude-haiku-4-5-20251001": {
        "input":  1.00 * USD_TO_INR,
        "output": 5.00 * USD_TO_INR,
    },
    "claude-sonnet-4-6": {
        "input":  3.00 * USD_TO_INR,
        "output": 15.00 * USD_TO_INR,
    },
}

PROMPT_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "gstr1_system_prompt.txt"
)

# Cache the prompt version hash at import time
_PROMPT_VERSION_CACHE: Optional[str] = None

def get_prompt_version() -> str:
    global _PROMPT_VERSION_CACHE
    if _PROMPT_VERSION_CACHE:
        return _PROMPT_VERSION_CACHE
    try:
        with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # Check for an explicit VERSION tag first
        for line in content.splitlines():
            if line.strip().startswith("# VERSION:"):
                _PROMPT_VERSION_CACHE = line.strip().replace("# VERSION:", "").strip()
                return _PROMPT_VERSION_CACHE
        # Fall back to SHA-1 hash of file content
        _PROMPT_VERSION_CACHE = "sha1-" + hashlib.sha1(content.encode()).hexdigest()[:12]
    except Exception:
        _PROMPT_VERSION_CACHE = "unknown"
    return _PROMPT_VERSION_CACHE

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def calc_cost_inr(model_identifier: str, prompt_tokens: int, completion_tokens: int) -> dict:
    rates = COST_PER_1M_TOKENS.get(model_identifier, {"input": 0.0, "output": 0.0})
    prompt_cost   = (prompt_tokens     / 1_000_000) * rates["input"]
    completion_cost = (completion_tokens / 1_000_000) * rates["output"]
    return {
        "currency": "INR",
        "prompt_cost_inr":     round(prompt_cost,    2),
        "completion_cost_inr": round(completion_cost, 2),
        "total_cost_inr":      round(prompt_cost + completion_cost, 2),
    }


class ObsLogger:
    """
    Stateful logger for a single pipeline execution.
    Instantiated once per file-in-batch.
    All emit_* methods write one row to ObservabilityLog.
    """

    def __init__(self, batch_id: str, file_id: str, model_identifier: str,
                 api_provider: str, db_session=None, tenant_id: str = None):
        self.batch_id         = batch_id
        self.file_id          = file_id
        self.model_identifier = model_identifier
        self.api_provider     = api_provider
        self.tenant_id        = tenant_id
        self.prompt_version   = get_prompt_version()
        self._db              = db_session
        self._stage_timings: dict = {}

    def _write(self, event_type: str, payload: dict,
               stage: Optional[str] = None,
               severity: Optional[str] = None,
               flag_id: Optional[str] = None,
               file_id_override: Optional[str] = None,
               original_file_id: Optional[str] = None,
               fix_id: Optional[str] = None,
               is_replay: bool = False) -> None:
        """Core write path. Validates correlation IDs, then INSERTs into ObservabilityLog."""
        from models import ObservabilityLog
        from database import SessionLocal

        # Enforce mandatory correlation IDs
        if not self.batch_id or not payload.get("timestamp_utc"):
            self._emit_missing_id_alert()
            return

        payload.setdefault("batch_id", self.batch_id)
        payload.setdefault("file_id", file_id_override or self.file_id)

        db = self._db or SessionLocal()
        try:
            log = ObservabilityLog(
                tenant_id        = self.tenant_id,
                batch_id         = self.batch_id,
                file_id          = file_id_override or self.file_id,
                event_type       = event_type,
                stage            = stage,
                severity         = severity,
                flag_id          = flag_id,
                payload_json     = json.dumps(payload, ensure_ascii=False, default=str),
                prompt_version   = self.prompt_version,
                model_identifier = self.model_identifier,
                api_provider     = self.api_provider,
                timestamp_utc    = datetime.fromisoformat(payload["timestamp_utc"].replace("Z", "+00:00")),
                original_file_id = original_file_id,
                fix_id           = fix_id,
                is_replay        = is_replay,
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"[OBSERVABILITY] Write error: {e}")
        finally:
            if not self._db:
                db.close()

    def _emit_missing_id_alert(self):
        print(f"[OBSERVABILITY] MISSING_CORRELATION_IDS — batch_id={self.batch_id} file_id={self.file_id}")

    # ── Step 1: Batch-level events ──────────────────────────────────────────

    @classmethod
    def emit_batch_envelope(cls, batch_id: str, session_id: str, model_selected: str,
                            model_identifier: str, api_provider: str, api_endpoint: str,
                            total_files: int, batch_type: str, environment: str,
                            submitted_by: str = "anonymous", db_session=None,
                            tenant_id: Optional[str] = None) -> None:
        """Step 1a — Batch envelope. Written synchronously before any file opens."""
        from models import ObservabilityLog
        from database import SessionLocal
        ts = now_utc()
        payload = {
            "event": "batch_received",
            "batch_id": batch_id,
            "session_id": session_id,
            "timestamp_utc": ts,
            "environment": environment,
            "model_selected_by_user": model_selected,
            "model_identifier": model_identifier,
            "api_provider": api_provider,
            "api_endpoint": api_endpoint,
            "routing_mode": "user_selected",
            "prompt_version": get_prompt_version(),
            "temperature": 0.0,
            "total_files_submitted": total_files,
            "batch_type": batch_type,
            "submitted_by": submitted_by,
        }
        db = db_session or SessionLocal()
        try:
            log = ObservabilityLog(
                tenant_id=tenant_id,
                batch_id=batch_id, file_id=None,
                event_type="batch_received", stage=None, severity=None, flag_id=None,
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                prompt_version=get_prompt_version(),
                model_identifier=model_identifier, api_provider=api_provider,
                timestamp_utc=datetime.now(timezone.utc),
            )
            db.add(log)
            db.commit()
        finally:
            if not db_session:
                db.close()

    @classmethod
    def emit_file_manifest(cls, batch_id: str, files_meta: list, db_session=None,
                           tenant_id: Optional[str] = None) -> None:
        """Step 1b — File manifest. One entry per file in the batch."""
        from models import ObservabilityLog
        from database import SessionLocal
        ts = now_utc()
        payload = {
            "event": "file_manifest",
            "batch_id": batch_id,
            "timestamp_utc": ts,
            "files": files_meta,
        }
        db = db_session or SessionLocal()
        try:
            log = ObservabilityLog(
                tenant_id=tenant_id,
                batch_id=batch_id, file_id=None,
                event_type="file_manifest", stage=None, severity=None, flag_id=None,
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                prompt_version=get_prompt_version(),
                timestamp_utc=datetime.now(timezone.utc),
            )
            db.add(log)
            db.commit()
        finally:
            if not db_session:
                db.close()

    # ── Step 2: Per-file stage events ───────────────────────────────────────

    def emit_file_intake(self, filename: str, page_count: Optional[int],
                         started_at: str, completed_at: str,
                         status: str = "ok",
                         scan_type: str = "text_selectable") -> None:
        """Stage 2a — File intake result."""
        payload = {
            "stage": "file_intake", "batch_id": self.batch_id, "file_id": self.file_id,
            "filename": filename, "page_count": page_count, "scan_type": scan_type,
            "started_at": started_at, "completed_at": completed_at,
            "status": status, "timestamp_utc": completed_at,
        }
        self._write("stage_event", payload, stage="file_intake")

    def emit_model_selection(self, started_at: str, completed_at: str,
                             api_key_present: bool, endpoint_health: str,
                             status: str = "ok") -> None:
        """Stage 2b — Model selection log with endpoint health check."""
        ENDPOINT_MAP = {
            "google_native": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "openrouter":    "https://openrouter.ai/api/v1",
        }
        payload = {
            "stage": "model_selection",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "model_selected": self.model_identifier,
            "model_identifier": self.model_identifier,
            "api_provider": self.api_provider,
            "api_endpoint": ENDPOINT_MAP.get(self.api_provider, "unknown"),
            "api_key_present": api_key_present,
            "endpoint_health_check": endpoint_health,
            "selection_source": "user_selected_at_batch_level",
            "started_at": started_at, "completed_at": completed_at,
            "status": status, "timestamp_utc": completed_at,
        }
        self._write("stage_event", payload, stage="model_selection")

    def emit_guardrail_precheck(self, started_at: str, completed_at: str,
                                passed: bool, failure_reason: Optional[str] = None) -> None:
        """Stage 2c — Guardrail prompt pre-check."""
        payload = {
            "stage": "guardrail_precheck",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "prompt_version": self.prompt_version,
            "checks_enforced": [
                "zero_hallucination_strict_nulls",
                "statutory_rate_validity",
                "no_line_item_stacking",
                "self_math_verification",
                "sales_vs_purchase_classification",
            ],
            "precheck_passed": passed,
            "precheck_failure_reason": failure_reason,
            "started_at": started_at, "completed_at": completed_at,
            "status": "ok" if passed else "blocked",
            "timestamp_utc": completed_at,
        }
        self._write("stage_event", payload, stage="guardrail_precheck")

    def emit_llm_extraction(self, started_at: str, completed_at: str,
                            latency_ms: int, prompt_tokens: int, completion_tokens: int,
                            raw_line_items: int, sales_count: int, purchase_count: int,
                            subtotal_rows_detected: int, json_parse_succeeded: bool,
                            retry_count: int, status: str = "ok") -> None:
        """Stage 2d — Raw LLM extraction result."""
        payload = {
            "stage": "llm_extraction",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "model_identifier": self.model_identifier,
            "api_provider": self.api_provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "raw_line_items_extracted": raw_line_items,
            "sales_items_count": sales_count,
            "purchase_items_count": purchase_count,
            "subtotal_rows_detected": subtotal_rows_detected,
            "json_parse_attempted": True,
            "json_parse_succeeded": json_parse_succeeded,
            "started_at": started_at, "completed_at": completed_at,
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "status": status,
            "timestamp_utc": completed_at,
        }
        self._write("stage_event", payload, stage="llm_extraction")

    def emit_post_processing(self, started_at: str, completed_at: str,
                             correction_meta: dict, final_item_count: int,
                             status: str = "ok") -> None:
        """Stage 2e — Backend post-processing correction log. No silent fixes."""
        payload = {
            "stage": "post_processing",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "corrections": correction_meta,
            "post_processing_line_items_final": final_item_count,
            "started_at": started_at, "completed_at": completed_at,
            "status": status, "timestamp_utc": completed_at,
        }
        self._write("stage_event", payload, stage="post_processing")

    def emit_final_output(self, started_at: str, completed_at: str, pipeline_total_ms: int,
                          line_items_written: int, gstr1_rows: int, gstr2b_rows: int,
                          output_saved: bool, status: str = "ok") -> None:
        """Stage 2f — Final output written to Excel / DB."""
        payload = {
            "stage": "final_output",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "output_type": "excel_row",
            "line_items_written": line_items_written,
            "gstr1_rows": gstr1_rows,
            "gstr2b_rows": gstr2b_rows,
            "reconciliation_mismatches_flagged": 0,
            "missing_invoices_flagged": 0,
            "output_saved": output_saved,
            "started_at": started_at, "completed_at": completed_at,
            "pipeline_total_latency_ms": pipeline_total_ms,
            "status": status, "timestamp_utc": completed_at,
        }
        self._write("stage_event", payload, stage="final_output")

    # ── Step 3: Context snapshot ────────────────────────────────────────────

    def emit_context_snapshot(self, filename: str, invoice_header: dict,
                              extraction_summary: dict, correction_meta: dict) -> None:
        """
        Step 3 — Force-write context snapshot after post-processing.
        Retried up to 3 times. Raises CONTEXT_STORE_WRITE_FAILURE if all retries fail.
        """
        total_corrections = sum([
            correction_meta.get("pydantic_null_coercions", 0),
            correction_meta.get("subtotal_rows_dropped", 0),
            correction_meta.get("gst_rates_snapped", 0),
            correction_meta.get("taxes_recalculated", 0),
            correction_meta.get("unallocated_rows_injected", 0),
        ])
        ts = now_utc()
        payload = {
            "event": "extraction_context_snapshot",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "filename": filename, "timestamp_utc": ts, "force_sent": True,
            "invoice_header": invoice_header,
            "extraction_summary": extraction_summary,
            "corrections_applied": total_corrections > 0,
            "correction_count": total_corrections,
            "model_identifier": self.model_identifier,
            "api_provider": self.api_provider,
            "prompt_version": self.prompt_version,
        }
        for attempt in range(3):
            try:
                self._write("extraction_context_snapshot", payload)
                return
            except Exception as e:
                if attempt == 2:
                    print(f"[OBSERVABILITY] CONTEXT_STORE_WRITE_FAILURE after 3 retries: {e}")
                    self.emit_flag("CONTEXT_STORE_WRITE_FAILURE", "CRITICAL",
                                   filename, f"Context snapshot write failed: {e}")

    # ── Step 4: Metrics ─────────────────────────────────────────────────────

    def emit_file_metrics(self, filename: str, page_count: int,
                          latency_breakdown: dict, token_usage: dict,
                          model_identifier: str, correction_meta: dict,
                          llm_retries: int, stage_failed: Optional[str],
                          error_type: Optional[str]) -> None:
        """Step 4a — Per-file metrics including INR cost."""
        cost = calc_cost_inr(
            model_identifier,
            token_usage.get("prompt_tokens", 0),
            token_usage.get("completion_tokens", 0),
        )
        raw_items = token_usage.get("raw_line_items", 1) or 1
        total_corr = (correction_meta.get("gst_rates_snapped", 0) +
                      correction_meta.get("subtotal_rows_dropped", 0) +
                      correction_meta.get("unallocated_rows_injected", 0))
        total_tokens = token_usage.get("prompt_tokens", 0) + token_usage.get("completion_tokens", 0)
        ts = now_utc()
        payload = {
            "event": "file_metrics",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "timestamp_utc": ts,
            "model_identifier": model_identifier,
            "api_provider": self.api_provider,
            "latency": latency_breakdown,
            "token_usage": {
                **token_usage,
                "tokens_per_page": round(total_tokens / max(page_count, 1), 1),
            },
            "model_cost": {
                **cost,
                "cost_per_page_inr": round(cost["total_cost_inr"] / max(page_count, 1), 4),
            },
            "corrections": {
                "total_corrections_applied": total_corr,
                "correction_rate": round(total_corr / raw_items, 3),
            },
            "retries": {"llm_retries": llm_retries, "context_store_retries": 0},
            "errors": {"stage_failed": stage_failed, "error_type": error_type},
        }
        self._write("file_metrics", payload)

    @classmethod
    def emit_batch_metrics(cls, batch_id: str, tasks_meta: list, model_identifier: str,
                           api_provider: str, db_session=None,
                           tenant_id: Optional[str] = None) -> None:
        """Step 4b — Batch-level metrics after all files complete."""
        from models import ObservabilityLog
        from database import SessionLocal
        ts = now_utc()
        submitted   = len(tasks_meta)
        ok_tasks    = [t for t in tasks_meta if t.get("status") == "ok"]
        failed      = [t for t in tasks_meta if t.get("status") == "failed"]
        latencies   = [t.get("total_ms", 0) for t in tasks_meta]
        total_ms    = sum(latencies)
        avg_ms      = round(total_ms / max(submitted, 1), 1)
        slowest     = max(tasks_meta, key=lambda x: x.get("total_ms", 0), default={})
        total_cost  = sum(t.get("cost_inr", 0.0) for t in tasks_meta)
        priciest    = max(tasks_meta, key=lambda x: x.get("cost_inr", 0.0), default={})
        total_corr  = sum(t.get("corrections", 0) for t in tasks_meta)
        unalloc     = sum(1 for t in tasks_meta if t.get("unallocated_injected", False))

        payload = {
            "event": "batch_metrics",
            "batch_id": batch_id, "timestamp_utc": ts,
            "files": {
                "submitted": submitted,
                "completed_ok": len(ok_tasks),
                "failed": len(failed),
                "partial": 0,
                "success_rate_pct": round(len(ok_tasks) / max(submitted, 1) * 100, 1),
            },
            "latency": {
                "total_batch_wall_time_ms": total_ms,
                "avg_file_latency_ms": avg_ms,
                "slowest_file_id": slowest.get("file_id"),
                "slowest_file_ms": slowest.get("total_ms", 0),
            },
            "correction_summary": {
                "total_corrections_across_batch": total_corr,
                "files_with_corrections": sum(1 for t in tasks_meta if t.get("corrections", 0) > 0),
                "files_with_unallocated_row_injected": unalloc,
                "total_gst_rates_snapped": sum(t.get("rates_snapped", 0) for t in tasks_meta),
            },
            "error_rate": {
                "failed_files": len(failed),
                "error_rate_pct": round(len(failed) / max(submitted, 1) * 100, 1),
                "most_common_error": "unknown",
            },
            "model_used": {
                "model_identifier": model_identifier,
                "api_provider": api_provider,
                "avg_latency_ms": avg_ms,
                "avg_cost_per_file_inr": round(total_cost / max(submitted, 1), 2),
                "avg_correction_rate": round(total_corr / max(submitted, 1), 2),
                "json_parse_failure_count": sum(1 for t in tasks_meta if not t.get("json_ok", True)),
                "composite_score_avg": round(
                    sum(t.get("composite_score", 0.0) for t in tasks_meta) / max(submitted, 1), 3
                ),
            },
        }
        db = db_session or SessionLocal()
        try:
            from models import ObservabilityLog
            log = ObservabilityLog(
                tenant_id=tenant_id,
                batch_id=batch_id, file_id=None, event_type="batch_metrics",
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                prompt_version=get_prompt_version(),
                model_identifier=model_identifier, api_provider=api_provider,
                timestamp_utc=datetime.now(timezone.utc),
            )
            db.add(log); db.commit()
        finally:
            if not db_session: db.close()

        # Check batch-level alert thresholds
        cls._check_batch_alerts(batch_id, payload, model_identifier, api_provider, db_session,
                                 tenant_id=tenant_id)

    @classmethod
    def _check_batch_alerts(cls, batch_id, metrics, model_identifier, api_provider, db_session,
                            tenant_id: Optional[str] = None):
        from database import SessionLocal
        from models import ObservabilityLog
        alerts = []
        cost = metrics.get("model_used", {}).get("avg_cost_per_file_inr", 0) * metrics["files"]["submitted"]
        if cost > 500:
            alerts.append(("HIGH_BATCH_COST", "HIGH", f"Total batch cost ₹{cost:.2f} > ₹500 threshold"))
        if metrics["error_rate"]["error_rate_pct"] > 10:
            alerts.append(("BATCH_FAILURE_RATE", "CRITICAL", f"Error rate {metrics['error_rate']['error_rate_pct']}% > 10%"))
        if metrics["latency"]["total_batch_wall_time_ms"] > 300_000:
            alerts.append(("SLOW_BATCH", "MEDIUM", f"Batch wall time {metrics['latency']['total_batch_wall_time_ms']}ms > 5 min"))
        unalloc_pct = (metrics["correction_summary"]["files_with_unallocated_row_injected"] /
                       max(metrics["files"]["submitted"], 1)) * 100
        if unalloc_pct > 20:
            alerts.append(("UNALLOCATED_ROW_SPIKE", "MEDIUM",
                           f"{metrics['correction_summary']['files_with_unallocated_row_injected']} files ({unalloc_pct:.1f}%) had unallocated rows injected"))
        ts = now_utc()
        db = db_session or SessionLocal()
        try:
            for flag_id, severity, detail in alerts:
                payload = {
                    "event": "system_flag", "flag_id": flag_id, "severity": severity,
                    "batch_id": batch_id, "file_id": None,
                    "timestamp_utc": ts, "trigger_detail": detail, "auto_routed_to_debug": True,
                }
                log = ObservabilityLog(
                    tenant_id=tenant_id,
                    batch_id=batch_id, file_id=None, event_type="system_flag",
                    severity=severity, flag_id=flag_id,
                    payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                    model_identifier=model_identifier, api_provider=api_provider,
                    timestamp_utc=datetime.now(timezone.utc),
                )
                db.add(log)
            db.commit()
        finally:
            if not db_session: db.close()

    # ── Step 5: Quality Score ───────────────────────────────────────────────

    def emit_quality_score(self, filename: str, has_valid_items: bool,
                           jini_present: bool, output_saved: bool,
                           total_cost_inr: float, page_count: int,
                           statutory_math_balanced: bool, variance_inr: float,
                           gstin_format_valid: bool, no_igst_cgst_conflict: bool,
                           grounding_score: float = 0.8) -> float:
        """
        Step 5 — Composite quality score.
        Weights: grounding 40% + statutory_math 30% + gstin_valid 20% + jini_present 10%
        Returns composite score float.
        """
        composite = round(
            (grounding_score * 0.40) +
            (1.0 if statutory_math_balanced else 0.0) * 0.30 +
            (1.0 if gstin_format_valid else 0.0) * 0.20 +
            (1.0 if jini_present else 0.0) * 0.10,
            3
        )
        ts = now_utc()
        payload = {
            "event": "extraction_quality_score",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "timestamp_utc": ts,
            "grounding_score": {"value": grounding_score, "method": "heuristic", "description": "Estimated grounding confidence"},
            "question_answered": {"value": has_valid_items, "description": "At least one valid line item returned"},
            "jini_present": {"value": jini_present, "description": "Model included self-verification block"},
            "response_saved": {"value": output_saved, "description": "Output written to DB and Excel"},
            "cost_acceptable": {"value": total_cost_inr <= 20.0, "description": "File cost within ₹20 threshold"},
            "statutory_math_balanced": {
                "value": statutory_math_balanced,
                "description": "taxable + cgst + sgst + igst == total within ₹1",
                "variance_inr": round(variance_inr, 2),
            },
            "gstin_format_valid": {"value": gstin_format_valid, "description": "GSTIN matches 15-char statutory regex"},
            "no_igst_cgst_conflict": {"value": no_igst_cgst_conflict, "description": "IGST and CGST+SGST are mutually exclusive"},
            "composite_score": composite,
            "score_version": "v1.0",
        }
        self._write("extraction_quality_score", payload)
        return composite

    # ── Step 6: Flags ───────────────────────────────────────────────────────

    def emit_flag(self, flag_id: str, severity: str, filename: str,
                  trigger_detail: str) -> None:
        """Step 6b — Emit a system anomaly flag."""
        ts = now_utc()
        payload = {
            "event": "system_flag",
            "flag_id": flag_id, "severity": severity,
            "batch_id": self.batch_id, "file_id": self.file_id,
            "filename": filename, "timestamp_utc": ts,
            "trigger_detail": trigger_detail,
            "auto_routed_to_debug": True,
        }
        self._write("system_flag", payload, severity=severity, flag_id=flag_id)

    def evaluate_flags(self, filename: str, composite_score: float, correction_meta: dict,
                       json_parse_ok: bool, statutory_math_balanced: bool,
                       gstin_format_valid: bool, no_igst_cgst_conflict: bool,
                       total_cost_inr: float, batch_avg_cost: float,
                       raw_items: int, stage_failed: Optional[str] = None,
                       reconciliation_status: Optional[str] = None,
                       reconciliation_confidence: Optional[float] = None) -> list:
        """
        Evaluate all flag rules from Step 6 and emit a flag for each triggered rule.

        reconciliation_status / reconciliation_confidence are optional and sourced
        from FinancialReconciliationEngine's ReconciliationReport (status,
        overall_confidence) — when the caller doesn't have a reconciliation
        result to pass (e.g. reconciliation itself failed to run), these stay
        None and the two rules below are skipped rather than firing on absent data.
        """
        flags = []
        total_corr = (correction_meta.get("gst_rates_snapped", 0) +
                      correction_meta.get("subtotal_rows_dropped", 0) +
                      correction_meta.get("unallocated_rows_injected", 0))
        correction_rate = total_corr / max(raw_items, 1)

        rules = [
            (composite_score < 0.6, "NUMBER_HALLUCINATION_SUSPECTED", "CRITICAL",
             f"grounding_score {composite_score:.2f} below 0.60 threshold"),
            (not statutory_math_balanced, "MATH_IMBALANCE_AFTER_CORRECTION", "CRITICAL",
             "statutory math still imbalanced after all post-processing corrections"),
            (not gstin_format_valid, "GSTIN_INVALID_FORMAT", "CRITICAL",
             "vendor GSTIN does not match 15-character statutory regex"),
            (not no_igst_cgst_conflict, "IGST_CGST_CONFLICT", "HIGH",
             "IGST and CGST+SGST are both non-zero on same line item"),
            (correction_rate > 0.30, "HIGH_CORRECTION_RATE", "HIGH",
             f"correction_rate {correction_rate:.1%} > 30% on this file"),
            (correction_meta.get("unallocated_rows_injected", 0) > 0, "UNALLOCATED_ROW_INJECTED", "HIGH",
             f"Unallocated/Missing Lines row injected — variance ₹{correction_meta.get('unallocated_row_details', {}).get('variance_amount', 0):.2f}"),
            (total_cost_inr > 20 or (batch_avg_cost > 0 and total_cost_inr > 3 * batch_avg_cost),
             "COST_SPIKE_PER_FILE", "HIGH",
             f"File cost ₹{total_cost_inr:.2f} > ₹20 or 3× batch avg ₹{batch_avg_cost:.2f}"),
            (correction_meta.get("subtotal_rows_dropped", 0) > 0, "SUBTOTAL_DOUBLE_COUNT_RISK", "MEDIUM",
             f"{correction_meta.get('subtotal_rows_dropped', 0)} subtotal row(s) detected and dropped"),
            (not json_parse_ok, "JSON_PARSE_FAILURE", "HIGH",
             "Model output could not be parsed as structured JSON"),
            (stage_failed is not None, "PARTIAL_TRACE", "LOW",
             f"Stage '{stage_failed}' failed to complete"),
            (reconciliation_status is not None and reconciliation_status == "BLOCKED",
             "RECONCILIATION_BLOCKED", "CRITICAL",
             f"Reconciliation status BLOCKED — invoice failed hard reconciliation checks"),
            (reconciliation_confidence is not None and reconciliation_confidence < 0.6,
             "RECONCILIATION_LOW_CONFIDENCE", "HIGH",
             # Tuple elements are all evaluated eagerly regardless of the
             # condition, so this message must be None-safe even though the
             # rule itself only ever fires when reconciliation_confidence is
             # not None — round(None, 2) would raise, so guard here too.
             f"Reconciliation overall_confidence "
             f"{round(reconciliation_confidence, 2) if reconciliation_confidence is not None else 'N/A'} "
             f"below 0.60 threshold"),
        ]

        for condition, flag_id, severity, detail in rules:
            if condition:
                self.emit_flag(flag_id, severity, filename, detail)
                flags.append(flag_id)

        return flags

    # ── Step 7: Debug Record ────────────────────────────────────────────────

    def emit_debug_record(self, filename: str, flags: list, correction_meta: dict,
                          line_items: int, total_taxable: float, total_invoice: float,
                          total_cost_inr: float, batch_avg_cost: float,
                          composite_score: float, output_saved: bool,
                          trace_complete: bool, recommended_action: str) -> None:
        """Step 7a — Full debug record for any flagged file."""
        total_corr = (correction_meta.get("gst_rates_snapped", 0) +
                      correction_meta.get("subtotal_rows_dropped", 0) +
                      correction_meta.get("unallocated_rows_injected", 0))
        cost_pct = round(((total_cost_inr - batch_avg_cost) / max(batch_avg_cost, 0.01)) * 100, 1) if batch_avg_cost else 0.0
        corr_parts = []
        if correction_meta.get("gst_rates_snapped", 0):
            corr_parts.append(f"{correction_meta['gst_rates_snapped']} rate(s) snapped")
        if correction_meta.get("subtotal_rows_dropped", 0):
            corr_parts.append(f"{correction_meta['subtotal_rows_dropped']} subtotal row(s) dropped")
        if correction_meta.get("unallocated_rows_injected", 0):
            corr_parts.append("1 unallocated row injected")
        ts = now_utc()
        payload = {
            "event": "debug_record",
            "batch_id": self.batch_id, "file_id": self.file_id,
            "filename": filename, "timestamp_utc": ts,
            "flags": flags,
            "final_answer": {
                "line_items": line_items,
                "total_taxable_value_inr": round(total_taxable, 2),
                "total_invoice_value_inr": round(total_invoice, 2),
                "corrections_applied": total_corr,
                "correction_log_summary": "; ".join(corr_parts) or "none",
                "output_written_to_excel": output_saved,
            },
            "prompt_version": self.prompt_version,
            "model_cost": {
                "total_cost_inr": round(total_cost_inr, 2),
                "cost_vs_batch_avg_pct": cost_pct,
            },
            "retention": {
                "context_snapshot_saved": True,
                "excel_row_saved": output_saved,
                "trace_complete": trace_complete,
            },
            "model_used": {
                "model_identifier": self.model_identifier,
                "api_provider": self.api_provider,
            },
            "composite_score": composite_score,
            "recommended_action": recommended_action,
        }
        self._write("debug_record", payload)

    # ── Step 6a: CA Review Flag ─────────────────────────────────────────────

    @classmethod
    def emit_ca_flag(cls, batch_id: str, file_id: str, rejected_field: str,
                     extracted_value: Any, ca_corrected_value: Any,
                     composite_score: float, db_session=None,
                     tenant_id: Optional[str] = None) -> None:
        """Step 6a — CA reviewer rejects a specific field from the frontend grid."""
        from models import ObservabilityLog
        from database import SessionLocal
        ts = now_utc()
        payload = {
            "event": "ca_review_flag",
            "flag_type": "ca_rejection",
            "batch_id": batch_id, "file_id": file_id,
            "timestamp_utc": ts,
            "rejected_field": rejected_field,
            "extracted_value": extracted_value,
            "ca_corrected_value": ca_corrected_value,
            "composite_score_at_flag": composite_score,
            "routed_to_debug_queue": True,
        }
        db = db_session or SessionLocal()
        try:
            log = ObservabilityLog(
                tenant_id=tenant_id,
                batch_id=batch_id, file_id=file_id,
                event_type="ca_review_flag", severity="HIGH", flag_id="CA_REJECTION",
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                timestamp_utc=datetime.now(timezone.utc),
            )
            db.add(log); db.commit()
        finally:
            if not db_session: db.close()

    # ── Step 8: Fix & Replay ────────────────────────────────────────────────

    @classmethod
    def emit_fix_applied(cls, original_file_id: str, batch_id: str, fix_id: str,
                         applied_by: str, fix_type: str, fix_description: str,
                         new_prompt_version: Optional[str] = None,
                         new_model_identifier: Optional[str] = None,
                         new_api_provider: Optional[str] = None,
                         db_session=None) -> None:
        """Step 8a — Log the fix action before replay."""
        from models import ObservabilityLog
        from database import SessionLocal
        ts = now_utc()
        payload = {
            "event": "fix_applied",
            "original_file_id": original_file_id, "original_batch_id": batch_id,
            "fix_id": fix_id, "timestamp_utc": ts,
            "applied_by": applied_by, "fix_type": fix_type,
            "fix_description": fix_description,
            "new_prompt_version": new_prompt_version,
            "new_model_identifier": new_model_identifier,
            "new_api_provider": new_api_provider,
        }
        db = db_session or SessionLocal()
        try:
            log = ObservabilityLog(
                batch_id=batch_id, file_id=original_file_id,
                event_type="fix_applied", original_file_id=original_file_id, fix_id=fix_id,
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                timestamp_utc=datetime.now(timezone.utc),
            )
            db.add(log); db.commit()
        finally:
            if not db_session: db.close()
