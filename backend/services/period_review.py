"""
The human review gate between reconciliation/filing generation (Phases
4-5) and anything actually reaching a GST portal. Nothing built in those
earlier phases persisted its output because no real consumer existed yet
- this module (backed by the SalesPeriodReview table) is that consumer.

Lifecycle: PENDING_REVIEW -> APPROVED or REJECTED. Both are terminal -
neither transition can be repeated or reversed through this module
(create a new period review to re-run reconciliation if something needs
correcting, rather than mutating a decided one - keeps the audit trail
honest: a review record always reflects what a human actually approved
or rejected at the time, not a later edit).
"""
import os
import sys

# Bare "from models import X" below needs backend/ itself on sys.path,
# not just the project root the test harness adds - same bootstrap as
# gstr1_filing.py, needed for the same reason (this module is imported
# via the "backend.services.X" convention in tests).
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import json
from datetime import datetime
from typing import List, Optional

from models import SalesPeriodReview


class ReviewStateError(Exception):
    """Raised when an approve/reject is attempted on a review that's
    already been decided - the whole point of a review gate is that a
    decision, once made, is a fact, not something silently overwritten."""


def build_recon_summary(recon_entries: List) -> dict:
    """
    Turns sales_reconciliation.py's ReconEntry list into the compact
    shape a reviewer actually needs: counts per status, plus the doc_nos
    that need a human's attention (everything except a clean PASS).
    """
    counts: dict = {}
    needs_attention = []
    for e in recon_entries:
        counts[e.status.value] = counts.get(e.status.value, 0) + 1
        if e.status.value != "PASS":
            needs_attention.append({"doc_no": e.doc_no, "status": e.status.value, "note": e.note})
    return {"counts": counts, "needs_attention": needs_attention}


def build_filings_summary(filings: dict) -> dict:
    """
    Turns gstr1_filing.generate_gstr1_filings' output into a compact
    per-registration summary - not the full nested GSTN JSON, which stays
    available via the "gstr1_json" key for whoever actually files it.
    """
    summary = {}
    for gstin, result in filings.items():
        gj = result.get("gstr1_json")
        summary[gstin] = {
            "has_data": gj is not None,
            "total_taxable": gj["_summary"]["total_taxable"] if gj else 0.0,
            "total_tax": gj["_summary"]["total_tax"] if gj else 0.0,
            "total_invoices": gj["_summary"]["total_invoices"] if gj else 0,
            "sections_with_data": gj["_summary"]["sections_with_data"] if gj else [],
            "flagged_unresolved": result.get("flagged_unresolved", []),
            "skipped": result.get("skipped", []),
        }
    return summary


def create_period_review(db, tenant_id: str, period: str,
                          recon_entries: List, filings: dict) -> SalesPeriodReview:
    """
    Persists a new PENDING_REVIEW record from this period's reconciliation
    + filing-generation output. Always creates a new row rather than
    upserting an existing (tenant, period) pair - re-running reconciliation
    for a period that already has a decided review should produce a new,
    separate review to approve/reject, not silently mutate history.
    """
    review = SalesPeriodReview(
        tenant_id=tenant_id,
        period=period,
        status="PENDING_REVIEW",
        recon_summary_json=json.dumps(build_recon_summary(recon_entries)),
        filings_summary_json=json.dumps(build_filings_summary(filings)),
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def approve_period_review(db, review_id: str, user_id: str, notes: Optional[str] = None) -> SalesPeriodReview:
    review = db.query(SalesPeriodReview).filter(SalesPeriodReview.id == review_id).first()
    if not review:
        raise ValueError(f"SalesPeriodReview {review_id} not found")
    if review.status != "PENDING_REVIEW":
        raise ReviewStateError(
            f"Review {review_id} is already {review.status} - cannot approve a decided review. "
            f"Create a new period review if this period needs to be re-reconciled."
        )
    review.status = "APPROVED"
    review.reviewed_by = user_id
    review.reviewed_at = datetime.utcnow()
    review.review_notes = notes
    db.commit()
    db.refresh(review)
    return review


def reject_period_review(db, review_id: str, user_id: str, notes: str) -> SalesPeriodReview:
    if not notes or not notes.strip():
        raise ValueError("A rejection reason is required - notes cannot be blank.")
    review = db.query(SalesPeriodReview).filter(SalesPeriodReview.id == review_id).first()
    if not review:
        raise ValueError(f"SalesPeriodReview {review_id} not found")
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


def get_review_detail(review: SalesPeriodReview) -> dict:
    """Deserializes a SalesPeriodReview row into an API-ready dict."""
    return {
        "id": review.id,
        "tenant_id": review.tenant_id,
        "period": review.period,
        "status": review.status,
        "recon_summary": json.loads(review.recon_summary_json) if review.recon_summary_json else {},
        "filings_summary": json.loads(review.filings_summary_json) if review.filings_summary_json else {},
        "reviewed_by": review.reviewed_by,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "review_notes": review.review_notes,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }
