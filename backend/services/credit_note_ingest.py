"""
Shared credit-note storage logic used by BOTH ingestion entry points -
Drive sync (google_drive_sync.py) and manual zip/PDF upload (main.py) -
so GSTIN resolution and SalesLineItem construction live in exactly one
place rather than being duplicated (and drifting) across both.
"""
import logging
from uuid import uuid4
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_gstin_for_tenant(db, tenant_id: str, original_invoice_no: str) -> Optional[str]:
    """
    Finds the buyer's GSTIN from their own regular invoice (credit notes
    never print it themselves - verified across all 14 real credit notes
    processed this session), scoped to this tenant so a GSTIN from a
    different tenant's invoice can never leak across. Returns None (not a
    guess) if the original invoice isn't in this tenant's own records.
    """
    from models import SalesLineItem, InvoiceTask, BatchJob
    if not original_invoice_no:
        return None
    row = (
        db.query(SalesLineItem.party_gstin)
        .join(InvoiceTask, InvoiceTask.id == SalesLineItem.task_id)
        .join(BatchJob, BatchJob.id == InvoiceTask.batch_id)
        .filter(
            SalesLineItem.invoice_no == original_invoice_no,
            SalesLineItem.party_gstin.isnot(None),
            BatchJob.tenant_id == tenant_id,
        )
        .first()
    )
    return row[0] if row else None


def ingest_credit_note_pdf(db, tenant_id: str, batch_id: str, local_path: str, filename: str) -> Optional[str]:
    """
    Reads a credit-note PDF, extracts it deterministically, resolves the
    buyer GSTIN against this tenant's own past invoices, and stores it as
    a SalesLineItem (voucher_type="Credit Note") under the given batch.

    Returns the new task_id, or None if the file isn't actually a credit
    note (extract_credit_note found no "Credit Note Number") - callers
    should treat None as a failure to log/flag, not silently ignore.

    Does NOT create the BatchJob itself or handle Drive dedup tracking -
    those are caller-specific (a scheduled Drive sync run vs. a one-shot
    manual upload have different batch/dedup semantics); this function
    only owns the part that's identical either way: parse -> resolve
    GSTIN -> store.
    """
    import fitz
    from invoice_processor import extract_credit_note
    from models import InvoiceTask, SalesLineItem, TaskStatus

    doc = fitz.open(local_path)
    full_text = "\n".join(p.get_text() for p in doc)
    cn = extract_credit_note(full_text)
    if not cn:
        logger.error(f"[credit_note_ingest] {filename} classified as credit_note but 'Credit Note Number' not found in text")
        return None

    party_gstin = resolve_gstin_for_tenant(db, tenant_id, cn["original_invoice_no"])
    if not party_gstin:
        logger.warning(
            f"[credit_note_ingest] Credit note {cn['credit_note_no']}: could not resolve buyer GSTIN "
            f"via original invoice {cn['original_invoice_no']!r} - stored without GSTIN, will need "
            f"manual GSTIN/place-of-supply resolution before this can be filed."
        )

    task_id = str(uuid4())
    task = InvoiceTask(id=task_id, batch_id=batch_id, file_name=filename,
                        status=TaskStatus.PENDING, invoice_type="sales")
    db.add(task)
    db.commit()

    db.add(SalesLineItem(
        task_id=task_id,
        voucher_date=cn["date"],
        voucher_type="Credit Note",
        invoice_no=cn["credit_note_no"],
        party_ledger_name=cn["party_name"],
        party_gstin=party_gstin,
        particulars=f"Credit Note - {cn['reason']} (against {cn['original_invoice_no']})",
        hsn=cn["hsn"],
        taxable_value=cn["taxable"],
        cgst_amount=cn["cgst"],
        sgst_amount=cn["sgst"],
        igst_amount=cn["igst"],
        total_invoice_value=cn["total"],
        narration=cn["reason"],
    ))
    task.status = TaskStatus.COMPLETED
    db.commit()

    logger.info(f"[credit_note_ingest] Processed credit note {cn['credit_note_no']} ({filename})")
    return task_id
