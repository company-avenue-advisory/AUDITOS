"""
gstr2b_trigger_engine.py — Outbound-messaging trigger logic for GSTR-2B
reconciliation gaps (Section 13.1/13.2), on top of the Gstr2bGapTrigger
table in models.py.

Confirmed rules (memory/project_gstr2b_client_trigger.md, 2026-07-17):
  Bucket A (not_in_books, Drive=No only — Drive=Yes is an internal
    Tally-booking fix, never client-facing): client request, gated behind
    accountant review by default. A firm can flip Tenant.bucket_a_require_review
    off to auto-approve instead, same as Bucket B's policy toggle (Notion
    §13.1 task: "Firm settings: outbound policy toggles (A-request gate
    on/off, B-auto-send on/off)").
  Bucket B (missing_in_2b): auto-email vendor-followup, behind a firm
    policy toggle (Tenant.auto_vendor_followup_enabled), audit-logged,
    idempotent.
  mismatch: internal accountant-review flag only — no outbound trigger,
    not tracked in this table.
  Idempotency: a still-unresolved gap re-triggers once per month (not just
    once ever) until resolved. Applies to both buckets.

Two-phase design matching the rest of this reconciliation layer:
  sync_gap_triggers()  — call every time reconciliation runs for a period.
    Upserts a Gstr2bGapTrigger row per open gap, and resolves any prior-open
    trigger whose gap no longer appears (invoice got booked / 2B caught up).
  run_due_triggers()   — call on a schedule (or manually). Sends whatever is
    currently due (approved Bucket A rows, policy-enabled Bucket B rows,
    respecting the monthly re-trigger gate) via an injected send_fn, same
    dependency-injection pattern as gstr2b_drive_verify's list_children_fn —
    defaults to an audit-log-only stub until a real email provider is wired
    in (see default_send_fn).
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy.orm import Session

from models import Gstr2bGapTrigger, Tenant

logger = logging.getLogger(__name__)

RETRIGGER_INTERVAL = timedelta(days=30)

SendFn = Callable[[Gstr2bGapTrigger, Tenant], None]


def default_send_fn(trigger: Gstr2bGapTrigger, tenant: Tenant) -> None:
    """
    Audit-log-only stub — no real email provider is wired in yet (see
    memory: send mechanism deferred until SMTP/SendGrid/etc. is chosen).
    Raises nothing; run_due_triggers still records last_triggered_at/
    trigger_count so the monthly cycle and audit trail behave exactly as
    they will once a real sender replaces this.
    """
    to = tenant.client_contact_email or "(no contact email configured)"
    kind = "client request" if trigger.bucket == "not_in_books" else "vendor follow-up"
    logger.info(
        f"[gstr2b_trigger_engine] STUB SEND — {kind} for invoice "
        f"{trigger.invoice_no} (counterparty GSTIN {trigger.counterparty_gstin}, "
        f"₹{trigger.amount}) would go to {to} for tenant {tenant.id} "
        f"(trigger {trigger.id}, attempt #{trigger.trigger_count + 1})"
    )


def _gap_rows(annotated_recon_result: dict):
    """
    Yields (bucket, row) for every row that is a trigger *candidate* under
    the confirmed rules — Bucket A only for Drive=No rows (Drive=Yes stays
    an internal Tally task, see module docstring), Bucket B for every
    missing_in_2b row.
    """
    for row in annotated_recon_result.get("extra", []):
        if row.get("recon_status") == "not_in_books" and row.get("in_drive") == "No":
            yield "not_in_books", row
    for row in annotated_recon_result.get("rows", []):
        if row.get("recon_status") == "missing_in_2b":
            yield "missing_in_2b", row


def sync_gap_triggers(
    db: Session,
    tenant_id: str,
    registration_gstin: str,
    period: str,
    annotated_recon_result: dict,
) -> None:
    """
    Upserts one Gstr2bGapTrigger row per currently-open gap (from an
    already Drive-annotated recon result — see
    gstr2b_excel_export.annotate_recon_result), and resolves any
    previously-open trigger for this (tenant, registration_gstin) whose gap
    no longer appears in this run.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    # Default True (accountant-gated) if the tenant row is somehow missing —
    # fail toward requiring a human, never toward silent auto-send.
    bucket_a_require_review = tenant.bucket_a_require_review if tenant else True
    bucket_a_initial_status = "pending_review" if bucket_a_require_review else "approved"

    open_keys = set()

    for bucket, row in _gap_rows(annotated_recon_result):
        counterparty_gstin = row.get("gst_no") or ""
        invoice_no = row.get("supplier_inv") or ""
        if not counterparty_gstin or not invoice_no:
            continue
        open_keys.add((counterparty_gstin, invoice_no, bucket))

        existing = db.query(Gstr2bGapTrigger).filter(
            Gstr2bGapTrigger.tenant_id == tenant_id,
            Gstr2bGapTrigger.registration_gstin == registration_gstin,
            Gstr2bGapTrigger.counterparty_gstin == counterparty_gstin,
            Gstr2bGapTrigger.invoice_no == invoice_no,
            Gstr2bGapTrigger.bucket == bucket,
        ).first()

        amount = row.get("total_amount") or row.get("2b_total_val") or row.get("amount")

        if existing:
            existing.period = period
            existing.amount = amount
            if existing.status == "resolved":
                # Gap reopened (e.g. a booked entry was reversed) — put it
                # back in front of a human/policy gate rather than silently
                # re-arming the old approval.
                existing.status = bucket_a_initial_status if bucket == "not_in_books" else "queued"
                existing.resolved_at = None
        else:
            db.add(Gstr2bGapTrigger(
                tenant_id=tenant_id,
                period=period,
                registration_gstin=registration_gstin,
                counterparty_gstin=counterparty_gstin,
                invoice_no=invoice_no,
                bucket=bucket,
                amount=amount,
                status=bucket_a_initial_status if bucket == "not_in_books" else "queued",
            ))

    still_open = db.query(Gstr2bGapTrigger).filter(
        Gstr2bGapTrigger.tenant_id == tenant_id,
        Gstr2bGapTrigger.registration_gstin == registration_gstin,
        Gstr2bGapTrigger.status.notin_(["resolved", "rejected"]),
    ).all()
    for trigger in still_open:
        key = (trigger.counterparty_gstin, trigger.invoice_no, trigger.bucket)
        if key not in open_keys:
            trigger.status = "resolved"
            trigger.resolved_at = datetime.utcnow()

    db.commit()


def approve_trigger(db: Session, trigger_id: str, reviewed_by: str) -> Gstr2bGapTrigger:
    """Accountant approves a Bucket A pending_review row so it becomes eligible to send."""
    trigger = db.query(Gstr2bGapTrigger).filter(Gstr2bGapTrigger.id == trigger_id).first()
    if not trigger:
        raise ValueError(f"No trigger with id {trigger_id}")
    if trigger.bucket != "not_in_books":
        raise ValueError("Only not_in_books (Bucket A) triggers require approval")
    if trigger.status != "pending_review":
        raise ValueError(f"Trigger {trigger_id} is not pending review (status={trigger.status})")
    trigger.status = "approved"
    trigger.reviewed_by = reviewed_by
    trigger.reviewed_at = datetime.utcnow()
    db.commit()
    return trigger


def reject_trigger(db: Session, trigger_id: str, reviewed_by: str) -> Gstr2bGapTrigger:
    """Accountant rejects a Bucket A pending_review row — no client contact this cycle."""
    trigger = db.query(Gstr2bGapTrigger).filter(Gstr2bGapTrigger.id == trigger_id).first()
    if not trigger:
        raise ValueError(f"No trigger with id {trigger_id}")
    if trigger.status != "pending_review":
        raise ValueError(f"Trigger {trigger_id} is not pending review (status={trigger.status})")
    trigger.status = "rejected"
    trigger.reviewed_by = reviewed_by
    trigger.reviewed_at = datetime.utcnow()
    db.commit()
    return trigger


def _is_due(trigger: Gstr2bGapTrigger, now: datetime) -> bool:
    if trigger.last_triggered_at is None:
        return True
    return now - trigger.last_triggered_at >= RETRIGGER_INTERVAL


def run_due_triggers(
    db: Session,
    tenant_id: str,
    send_fn: Optional[SendFn] = None,
) -> dict:
    """
    Sends whatever is currently due for this tenant:
      - Bucket A: status == "approved"
      - Bucket B: status in ("queued", "sent") and Tenant.auto_vendor_followup_enabled
    both gated by the monthly re-trigger interval (_is_due). Returns a
    summary dict of what was sent/skipped for the caller (API response /
    Celery task log) to report.
    """
    send_fn = send_fn or default_send_fn
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise ValueError(f"No tenant with id {tenant_id}")

    now = datetime.utcnow()
    sent, skipped = [], []

    candidates = db.query(Gstr2bGapTrigger).filter(
        Gstr2bGapTrigger.tenant_id == tenant_id,
        Gstr2bGapTrigger.status.in_(["approved", "queued", "sent"]),
    ).all()

    for trigger in candidates:
        if trigger.bucket == "missing_in_2b" and not tenant.auto_vendor_followup_enabled:
            skipped.append({"id": trigger.id, "reason": "auto_vendor_followup disabled"})
            continue
        if trigger.bucket == "not_in_books" and trigger.status not in ("approved", "sent"):
            skipped.append({"id": trigger.id, "reason": f"status={trigger.status}, not approved"})
            continue
        if not _is_due(trigger, now):
            skipped.append({"id": trigger.id, "reason": "not due (sent within last 30 days)"})
            continue

        try:
            send_fn(trigger, tenant)
        except Exception as e:
            logger.warning(f"[gstr2b_trigger_engine] send_fn failed for trigger {trigger.id}: {e}")
            skipped.append({"id": trigger.id, "reason": f"send failed: {e}"})
            continue

        trigger.status = "sent"
        trigger.last_triggered_at = now
        trigger.trigger_count += 1
        sent.append({"id": trigger.id, "bucket": trigger.bucket, "invoice_no": trigger.invoice_no})

    db.commit()
    return {"sent": sent, "skipped": skipped}
