"""
Review queue prioritization (Bootstrap Task 4).

Deterministic, explainable weighted scoring over signals the pipeline
already computes elsewhere in the codebase -- this module does not
extract, validate, or reconcile anything itself, it only ranks tasks
that have already been through those existing systems:

  - confidence            -> ObservabilityLog "extraction_quality_score" (composite_score)
  - reconciliation_status -> InvoiceTask.recon_status (FinancialReconciliationEngine)
  - validation_status     -> InvoiceTask.validation_status (Bootstrap Task 4 addition,
                              same statutory-math/GSTIN/IGST-CGST checks already run
                              in async_tasks.py)
  - is_duplicate           -> services/duplicate_detector.py (existing module, reused
                              here, not reimplemented)
  - manual_flag_count      -> count of existing UserAnnotation rows for the task
                              (a task a reviewer has already touched once warrants
                              a second look before being considered settled)
  - total_invoice_value    -> already present in the sales/purchase line-item dicts
                              the /api/jobs/{batch_id} endpoint already builds

No AI/ML here by design (per Bootstrap Task 4's explicit scope: capture the
data first, build learning later) -- every weight below is a fixed constant,
easy to read and tune, not fit from data.
"""
from typing import Any, Dict, List, Optional

# Higher score = review sooner. Weights are relative, not absolute --
# tune by adjusting these constants, not the scoring logic itself.
WEIGHT_CONFIDENCE      = 40.0   # scaled by (1 - confidence)
WEIGHT_RECON_BLOCKED   = 35.0
WEIGHT_RECON_NEEDS_REVIEW = 15.0
WEIGHT_VALIDATION_FAILED  = 20.0
WEIGHT_DUPLICATE       = 25.0
WEIGHT_MANUAL_FLAG     = 8.0    # per existing correction/annotation on this task, capped
MANUAL_FLAG_CAP        = 3
WEIGHT_HIGH_VALUE      = 15.0
# Materiality threshold in INR above which an invoice is treated as
# "high value" for prioritization purposes. A fixed placeholder default,
# not derived from any specific client's actual materiality policy --
# tune per-deployment if/when that becomes a real requirement.
HIGH_VALUE_THRESHOLD_INR = 100_000.0

# Confidence value used when no extraction_quality_score is available at
# all -- treated as neutral (neither confidently good nor confidently bad),
# not as a false-confident 1.0 or a false-alarm 0.0.
UNKNOWN_CONFIDENCE = 0.5


def compute_priority_score(
    confidence: Optional[float],
    recon_status: Optional[str],
    validation_status: Optional[str],
    is_duplicate: bool,
    manual_flag_count: int,
    total_invoice_value: float,
) -> float:
    """Pure function: given already-computed signals, return a single
    non-negative priority score. Higher = review sooner. No DB access,
    no side effects -- deliberately easy to unit test in isolation."""
    conf = confidence if confidence is not None else UNKNOWN_CONFIDENCE
    score = (1.0 - conf) * WEIGHT_CONFIDENCE

    if recon_status == "BLOCKED":
        score += WEIGHT_RECON_BLOCKED
    elif recon_status == "NEEDS_REVIEW":
        score += WEIGHT_RECON_NEEDS_REVIEW

    if validation_status == "FAILED":
        score += WEIGHT_VALIDATION_FAILED

    if is_duplicate:
        score += WEIGHT_DUPLICATE

    score += min(manual_flag_count, MANUAL_FLAG_CAP) * WEIGHT_MANUAL_FLAG

    if total_invoice_value and total_invoice_value >= HIGH_VALUE_THRESHOLD_INR:
        score += WEIGHT_HIGH_VALUE

    return round(score, 2)


def sort_tasks_by_priority(tasks_details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Attaches a priority_score to each task_info dict (in place) and returns
    the list re-ordered highest-priority-first. Every input field is read
    defensively (.get with a default) so this works whether or not the
    caller has already populated the newer Task 4 fields
    (validation_status, is_duplicate, manual_flag_count) -- callers that
    haven't wired those yet simply get a score computed from whatever
    signals are present, never a crash.
    """
    for t in tasks_details:
        t["priority_score"] = compute_priority_score(
            confidence=t.get("composite_score"),
            recon_status=t.get("recon_status"),
            validation_status=t.get("validation_status"),
            is_duplicate=bool(t.get("is_duplicate", False)),
            manual_flag_count=int(t.get("manual_flag_count", 0) or 0),
            total_invoice_value=float(t.get("total_invoice_value", 0.0) or 0.0),
        )
    return sorted(tasks_details, key=lambda t: t["priority_score"], reverse=True)
