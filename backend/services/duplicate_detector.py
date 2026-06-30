"""
Duplicate invoice detection for AuditOS.

A duplicate is defined as two or more line items sharing the same
(invoice_no, party_gstin, voucher_date) after normalisation.

Two scopes are checked:
  - within_batch  : duplicates inside the current batch (same file uploaded twice,
                    or two files that extracted the same invoice number)
  - cross_batch   : the same invoice appeared in a *different* batch for this
                    user/tenant — the classic "uploaded last month's PDF again" case.

Returns a structured dict so the caller (API endpoint) can decide what to surface.
"""

from collections import defaultdict
from typing import List


def _norm(val: str) -> str:
    return str(val or "").strip().upper()


def _invoice_key(item) -> tuple:
    """Canonical key for deduplication: (invoice_no, party_gstin, date)."""
    return (
        _norm(getattr(item, "invoice_no", "") or ""),
        _norm(getattr(item, "party_gstin", "") or ""),
        _norm(getattr(item, "voucher_date", "") or ""),
    )


def _item_summary(item, filename: str) -> dict:
    return {
        "invoice_no":          str(item.invoice_no or ""),
        "party_gstin":         str(item.party_gstin or ""),
        "party_ledger_name":   str(getattr(item, "party_ledger_name", "") or ""),
        "voucher_date":        str(item.voucher_date or ""),
        "total_invoice_value": float(getattr(item, "total_invoice_value", 0) or 0),
        "filename":            filename,
        "task_id":             str(item.task_id),
    }


def detect_within_batch(tasks) -> List[dict]:
    """
    Find invoices that appear more than once inside the same batch.
    Each returned entry describes one duplicate group.
    """
    seen: dict = defaultdict(list)
    for task in tasks:
        fname = getattr(task, "file_name", "") or ""
        for item in (getattr(task, "sales_items", None) or []):
            key = _invoice_key(item)
            if key[0]:  # skip rows with no invoice_no
                seen[key].append(_item_summary(item, fname))
        for item in (getattr(task, "purchase_items", None) or []):
            key = _invoice_key(item)
            if key[0]:
                seen[key].append(_item_summary(item, fname))

    duplicates = []
    for key, occurrences in seen.items():
        if len(occurrences) > 1:
            duplicates.append({
                "invoice_no":    key[0],
                "party_gstin":   key[1],
                "voucher_date":  key[2],
                "occurrences":   occurrences,
                "count":         len(occurrences),
                "scope":         "within_batch",
                "risk":          "high",
                "message":       f"Invoice {key[0]} appears {len(occurrences)} times in this batch.",
            })

    return duplicates


def detect_cross_batch(db, current_batch_id: str, user_id: str, tenant_id: str = None):
    """
    Find invoices from the current batch that also exist in other batches
    for the same user/tenant.

    Uses raw ORM queries to avoid full table scans on large datasets.
    Only checks invoice_no + party_gstin (date omitted intentionally —
    the same invoice_no + GSTIN should never appear in two different periods).
    """
    from models import SalesLineItem, PurchaseLineItem, InvoiceTask, BatchJob

    # Collect (invoice_no, party_gstin) pairs from current batch
    current_tasks = db.query(InvoiceTask).filter(
        InvoiceTask.batch_id == current_batch_id
    ).all()
    current_task_ids = [t.id for t in current_tasks]

    if not current_task_ids:
        return []

    current_keys: dict = defaultdict(list)  # (inv_no, gstin) → [item summary]
    for task in current_tasks:
        fname = getattr(task, "file_name", "") or ""
        for item in (getattr(task, "sales_items", None) or []):
            inv = _norm(item.invoice_no or "")
            gstin = _norm(item.party_gstin or "")
            if inv:
                current_keys[(inv, gstin)].append(_item_summary(item, fname))
        for item in (getattr(task, "purchase_items", None) or []):
            inv = _norm(item.invoice_no or "")
            gstin = _norm(item.party_gstin or "")
            if inv:
                current_keys[(inv, gstin)].append(_item_summary(item, fname))

    if not current_keys:
        return []

    # Find other batches for same user/tenant
    other_batches_q = db.query(BatchJob).filter(
        BatchJob.id != current_batch_id,
        BatchJob.user_id == user_id,
    )
    if tenant_id:
        other_batches_q = other_batches_q.filter(BatchJob.tenant_id == tenant_id)
    other_batch_ids = [b.id for b in other_batches_q.all()]

    if not other_batch_ids:
        return []

    other_task_ids = [
        t.id for t in db.query(InvoiceTask).filter(
            InvoiceTask.batch_id.in_(other_batch_ids)
        ).all()
    ]
    if not other_task_ids:
        return []

    # Build batch_id lookup for task_id
    task_to_batch = {
        t.id: t.batch_id
        for t in db.query(InvoiceTask).filter(InvoiceTask.id.in_(other_task_ids)).all()
    }

    duplicates = []
    inv_nos = list({k[0] for k in current_keys.keys()})

    # Check sales
    for item in db.query(SalesLineItem).filter(
        SalesLineItem.task_id.in_(other_task_ids),
        SalesLineItem.invoice_no.isnot(None),
    ).all():
        inv = _norm(item.invoice_no or "")
        gstin = _norm(item.party_gstin or "")
        key = (inv, gstin)
        if key in current_keys and inv:
            other_batch = task_to_batch.get(item.task_id, "")
            duplicates.append({
                "invoice_no":   inv,
                "party_gstin":  gstin,
                "voucher_date": _norm(item.voucher_date or ""),
                "occurrences":  current_keys[key] + [_item_summary(item, "")],
                "count":        len(current_keys[key]) + 1,
                "scope":        "cross_batch",
                "other_batch_id": other_batch,
                "risk":         "critical",
                "message":      f"Invoice {inv} was also found in batch {other_batch[:8]}… — possible re-upload.",
            })

    # Check purchase (same check)
    for item in db.query(PurchaseLineItem).filter(
        PurchaseLineItem.task_id.in_(other_task_ids),
        PurchaseLineItem.invoice_no.isnot(None),
    ).all():
        inv = _norm(item.invoice_no or "")
        gstin = _norm(item.party_gstin or "")
        key = (inv, gstin)
        if key in current_keys and inv:
            other_batch = task_to_batch.get(item.task_id, "")
            duplicates.append({
                "invoice_no":   inv,
                "party_gstin":  gstin,
                "voucher_date": _norm(item.voucher_date or ""),
                "occurrences":  current_keys[key] + [_item_summary(item, "")],
                "count":        len(current_keys[key]) + 1,
                "scope":        "cross_batch",
                "other_batch_id": other_batch,
                "risk":         "critical",
                "message":      f"Invoice {inv} was also found in a previous batch — possible re-upload.",
            })

    # De-duplicate the duplicates list (same invoice_no+gstin can match multiple items)
    seen_keys: set = set()
    unique = []
    for d in duplicates:
        k = (d["invoice_no"], d["party_gstin"], d.get("other_batch_id", ""))
        if k not in seen_keys:
            seen_keys.add(k)
            unique.append(d)
    return unique


def detect_all(db, tasks, current_batch_id: str, user_id: str, tenant_id: str = None) -> dict:
    within = detect_within_batch(tasks)
    cross  = detect_cross_batch(db, current_batch_id, user_id, tenant_id)

    critical = [d for d in cross  if d["risk"] == "critical"]
    high     = [d for d in within if d["risk"] == "high"]

    return {
        "within_batch":        within,
        "cross_batch":         cross,
        "total_duplicates":    len(within) + len(cross),
        "critical_count":      len(critical),
        "high_count":          len(high),
        "has_duplicates":      bool(within or cross),
    }
