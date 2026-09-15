"""
The human review gate between GSTR-2B reconciliation (gstr2b_reconciler.py)
and anything actually feeding a GSTR-3B ITC claim. Mirrors
services/period_review.py's shape and lifecycle (see that module's
docstring for the full reasoning) - same PENDING_REVIEW -> APPROVED/
REJECTED state machine, same "always create a new review, never mutate
a decided one" rule.

Scoped per (tenant, period, gstin) rather than just (tenant, period) -
see PurchaseGstr2bReview's docstring in models.py for why.
"""
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import json
from datetime import datetime
from typing import List, Optional

from models import PurchaseGstr2bReview


class ReviewStateError(Exception):
    """Raised when an approve/reject is attempted on a review that's
    already been decided - see services/period_review.py's identical
    class for the full reasoning (kept as a separate class, not shared,
    so Sales and Purchase review flows can evolve independently)."""


def month_matches_period(voucher_date: Optional[str], period: str) -> bool:
    """Identical convention to services/period_review.month_matches_period -
    period is 'YYYY-MM', voucher_date is 'DD-MM-YYYY'. Duplicated rather
    than imported to keep this module's only dependency on the Sales
    side at zero - Purchase review must keep working even if Sales code
    changes."""
    if not voucher_date:
        return False
    try:
        year, month = period.split("-")
        parts = str(voucher_date).strip().split("-")
        return len(parts) == 3 and parts[1] == month and parts[2] == year
    except (ValueError, IndexError):
        return False


def get_latest_review(db, tenant_id: str, period: str, gstin: str) -> Optional[PurchaseGstr2bReview]:
    return (
        db.query(PurchaseGstr2bReview)
        .filter(
            PurchaseGstr2bReview.tenant_id == tenant_id,
            PurchaseGstr2bReview.period == period,
            PurchaseGstr2bReview.gstin == gstin,
        )
        .order_by(PurchaseGstr2bReview.created_at.desc())
        .first()
    )


def create_review(db, tenant_id: str, period: str, gstin: str, recon_result: dict) -> PurchaseGstr2bReview:
    """
    Persists a new PENDING_REVIEW record from gstr2b_reconciler.reconcile()'s
    output. Always creates a new row rather than upserting an existing
    (tenant, period, gstin) triple - re-running reconciliation for a
    period that already has a decided review should produce a new,
    separate review, not silently mutate history (matches Sales'
    create_period_review - see that function's docstring).
    """
    review = PurchaseGstr2bReview(
        tenant_id=tenant_id,
        period=period,
        gstin=gstin,
        status="PENDING_REVIEW",
        recon_summary_json=json.dumps(recon_result.get("summary", {})),
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def generate_review_for_tenant(db, tenant_id: str, period: str, gstin: str,
                                gstr2b_json_path: str, skip_if_pending: bool = False):
    """
    Runs GSTR-2B parsing + reconciliation (gstr2b_reconciler.py) for a
    tenant/period/gstin against this tenant's own PurchaseLineItem
    records and persists the result as a new PENDING_REVIEW. Single code
    path used by both a manual "generate" endpoint and the scheduled
    Drive-drop ingestion chain, so the two never drift (same reasoning
    as generate_period_review_for_tenant in services/period_review.py).

    skip_if_pending=True (used by the scheduled chain) skips creating a
    new review if the latest one for this (tenant, period, gstin) is
    still PENDING_REVIEW.

    Returns (review, created).
    """
    from services.gstr2b_reconciler import parse_gstr2b, reconcile
    from models import PurchaseLineItem, InvoiceTask, BatchJob

    if skip_if_pending:
        latest = get_latest_review(db, tenant_id, period, gstin)
        if latest and latest.status == "PENDING_REVIEW":
            return latest, False

    with open(gstr2b_json_path, "r", encoding="utf-8") as f:
        raw_2b = json.load(f)
    gstr2b_records = parse_gstr2b(raw_2b)

    items = (
        db.query(PurchaseLineItem)
        .join(InvoiceTask, InvoiceTask.id == PurchaseLineItem.task_id)
        .join(BatchJob, BatchJob.id == InvoiceTask.batch_id)
        .filter(BatchJob.tenant_id == tenant_id)
        .all()
    )
    period_items = [i for i in items if month_matches_period(i.voucher_date, period)]
    books_items = [{c.name: getattr(i, c.name) for c in i.__table__.columns} for i in period_items]

    recon_result = reconcile(books_items, gstr2b_records)
    review = create_review(db, tenant_id, period, gstin, recon_result)
    return review, True


def approve_review(db, review_id: str, user_id: str, notes: Optional[str] = None) -> PurchaseGstr2bReview:
    review = db.query(PurchaseGstr2bReview).filter(PurchaseGstr2bReview.id == review_id).first()
    if not review:
        raise ValueError(f"PurchaseGstr2bReview {review_id} not found")
    if review.status != "PENDING_REVIEW":
        raise ReviewStateError(
            f"Review {review_id} is already {review.status} - cannot approve a decided review. "
            f"Create a new review if this period needs to be re-reconciled."
        )
    review.status = "APPROVED"
    review.reviewed_by = user_id
    review.reviewed_at = datetime.utcnow()
    review.review_notes = notes
    db.commit()
    db.refresh(review)
    return review


def reject_review(db, review_id: str, user_id: str, notes: str) -> PurchaseGstr2bReview:
    if not notes or not notes.strip():
        raise ValueError("A rejection reason is required - notes cannot be blank.")
    review = db.query(PurchaseGstr2bReview).filter(PurchaseGstr2bReview.id == review_id).first()
    if not review:
        raise ValueError(f"PurchaseGstr2bReview {review_id} not found")
    if review.status != "PENDING_REVIEW":
        raise ReviewStateError(
            f"Review {review_id} is already {review.status} - cannot reject a decided review."
        )
    review.status = "REJECTED"
    review.reviewed_by = user_id
    review.reviewed_at = datetime.utcnow()
    review.review_notes = notes
    db.commit()
    db.refresh(review)
    return review


def get_review_detail(review: PurchaseGstr2bReview) -> dict:
    """Deserializes a PurchaseGstr2bReview row into an API-ready dict."""
    return {
        "id": review.id,
        "tenant_id": review.tenant_id,
        "period": review.period,
        "gstin": review.gstin,
        "status": review.status,
        "recon_summary": json.loads(review.recon_summary_json) if review.recon_summary_json else {},
        "reviewed_by": review.reviewed_by,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "review_notes": review.review_notes,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }
