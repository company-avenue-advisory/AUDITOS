"""
Sheet-first ingestion mode.

The ordinary Drive-sync pipeline (google_drive_sync.py) is PDF-first: every
invoice PDF is independently extracted (LLM or deterministic regex), and
the client's own Excel sheet - when one exists - is only used afterward as
a cross-check (see sales_reconciliation.py). Some clients' sheets (e.g.
OneStack's monthly masterdata workbook) are reliable enough, and updated
promptly enough, that re-extracting every PDF from scratch every month is
wasted work: the sheet already has the right HSN/amounts for the vast
majority of rows.

This module builds SalesLineItem-shaped records FROM the sheet directly,
trusting its own HSN/amounts as ground truth, and only falls back to a
real PDF extraction for two cases where the sheet genuinely cannot supply
the data itself:
  1. A PDF found in Drive whose own document number has no matching row
     anywhere in the sheet at all - a genuine gap in the client's tracker.
  2. A Credit Note / Debit Note row - OneStack's masterdata sheet's own
     per-bucket formula columns don't compute for these rows (confirmed
     against the real workbook), so the sheet cannot be trusted as the
     HSN source for them even though it IS trusted for regular invoices.
     If a matching PDF exists, its own particulars line (see
     invoice_processor.extract_credit_note's HSN bucket allocation) is
     the ground truth for these rows instead.

Nothing here silently drops or auto-adds a row: a gap PDF with no doc_no
match is flagged as MISSING_FROM_SHEET, not invented into the sheet; a
CN/DN row with no matching PDF still gets stored (using the sheet's own
top-level totals with NOT_SPECIFIED_HSN, matching what happens today) so
the row isn't lost, but is left for a human to confirm the bucket via
sales_period_review's existing review gate.
"""
import logging
from typing import Callable, List, Optional
from uuid import uuid4

from services.client_sheet_parser import sections_to_line_items, NOT_SPECIFIED_HSN
from services.drive_classifier import ClassifiedFile, DocumentType

logger = logging.getLogger(__name__)


def doc_no_from_pdf_text(full_text: str) -> Optional[str]:
    """
    Cheaply recovers a PDF's own document number (invoice or credit note)
    via the existing deterministic regexes - no LLM call, just enough to
    match this one PDF against a sheet row by doc_no. Tries credit note
    first since extract_credit_note's own "Credit Note Number" check is
    how the rest of the pipeline already tells the two apart.
    """
    from invoice_processor import _extract_invoice_header, extract_credit_note

    cn = extract_credit_note(full_text)
    if cn:
        return cn.get("credit_note_no")
    header = _extract_invoice_header(full_text)
    return header.get("invoice_no") or None


def find_gap_files(classified_files: List[ClassifiedFile], sheet_doc_nos: set,
                    text_reader: Callable[[ClassifiedFile], Optional[str]]) -> List[ClassifiedFile]:
    """
    Returns the subset of classified_files (INVOICE/CREDIT_NOTE only) whose
    own document number has no matching row anywhere in the client sheet -
    genuine gaps the sheet can't fill in for itself.

    text_reader(classified_file) -> the PDF's extracted text, or None if it
    couldn't be read. Injected so this is testable without live Drive/PDF
    I/O, matching drive_classifier.walk_and_classify's list_children_fn
    dependency-injection pattern.
    """
    gaps = []
    for f in classified_files:
        if f.document_type not in (DocumentType.INVOICE, DocumentType.CREDIT_NOTE):
            continue
        text = text_reader(f)
        doc_no = doc_no_from_pdf_text(text) if text else None
        if not doc_no or doc_no not in sheet_doc_nos:
            gaps.append(f)
    return gaps


def find_credit_note_pdf_for_row(row: dict, classified_files: List[ClassifiedFile],
                                  text_reader: Callable[[ClassifiedFile], Optional[str]]) -> Optional[ClassifiedFile]:
    """
    Finds the Drive PDF (if any) matching a Credit/Debit Note sheet row's
    own doc_no - that PDF, not the sheet's own bucket columns, is the HSN
    source for these rows (see module docstring).
    """
    target = str(row.get("doc_no") or "").strip()
    if not target:
        return None
    for f in classified_files:
        if f.document_type != DocumentType.CREDIT_NOTE:
            continue
        text = text_reader(f)
        if text and doc_no_from_pdf_text(text) == target:
            return f
    return None


def build_line_items_from_sheet_row(row: dict) -> List[dict]:
    """
    Converts one client-sheet row into 1+ SalesLineItem-shaped dicts
    (hsn/taxable_value/cgst_amount/sgst_amount/igst_amount/total_invoice_value
    plus the shared invoice header fields), trusting the sheet's own
    figures directly. Falls back to a single NOT_SPECIFIED_HSN line using
    the row's own top-level totals when no per-bucket breakdown is usable
    (a Credit/Debit Note row with no matching PDF, or an Invoice row with
    every section bucket at zero) - never fabricates a number.
    """
    common = {
        "voucher_date": row.get("doc_date"),
        "voucher_type": row.get("doc_type"),
        "invoice_no": row.get("doc_no"),
        "party_ledger_name": row.get("party_name"),
        "party_gstin": row.get("party_gstin"),
        "place_of_supply": row.get("state_of_supply"),
    }

    sections = sections_to_line_items(row)
    if not sections:
        return [{
            **common,
            "particulars": f"{row.get('doc_type') or 'Invoice'} (from client sheet, no bucket breakdown)",
            "hsn": NOT_SPECIFIED_HSN,
            "taxable_value": row.get("taxable") or 0.0,
            "cgst_amount": row.get("cgst") or 0.0,
            "sgst_amount": row.get("sgst") or 0.0,
            "igst_amount": row.get("igst") or 0.0,
            "total_invoice_value": row.get("total") or 0.0,
            "narration": "sheet-first: client sheet totals, no per-bucket breakdown available",
        }]

    return [{
        **common,
        "particulars": f"From client sheet - HSN {item['hsn']}",
        "hsn": item["hsn"],
        "taxable_value": item["taxable"],
        "cgst_amount": item["cgst"],
        "sgst_amount": item["sgst"],
        "igst_amount": item["igst"],
        "total_invoice_value": item["total"],
        "narration": "sheet-first: from client sheet bucket breakdown",
    } for item in sections]


def build_line_items_for_credit_note_pdf(row: dict, full_text: str) -> Optional[List[dict]]:
    """
    Builds a line item for a Credit/Debit Note row using ITS OWN PDF
    (extract_credit_note, which reads the particulars line for the correct
    HSN bucket - see invoice_processor.py) instead of the sheet's
    unreliable bucket columns for these rows. Returns None if the PDF
    text doesn't actually parse as a credit note (caller should fall back
    to build_line_items_from_sheet_row's sheet-totals-only path).
    """
    from invoice_processor import extract_credit_note

    cn = extract_credit_note(full_text)
    if not cn:
        return None
    return [{
        "voucher_date": cn["date"],
        "voucher_type": row.get("doc_type") or "Credit Note",
        "invoice_no": cn["credit_note_no"],
        "party_ledger_name": cn["party_name"] or row.get("party_name"),
        "party_gstin": row.get("party_gstin"),
        "place_of_supply": row.get("state_of_supply"),
        "particulars": f"Credit Note - {cn['reason']} (against {cn['original_invoice_no']})",
        "hsn": cn["hsn"],
        "taxable_value": cn["taxable"],
        "cgst_amount": cn["cgst"],
        "sgst_amount": cn["sgst"],
        "igst_amount": cn["igst"],
        "total_invoice_value": cn["total"],
        "narration": "sheet-first: credit note HSN read from its own PDF, sheet bucket columns not trusted for CN/DN rows",
    }]


def plan_sheet_first_ingestion(client_rows: List[dict], classified_files: List[ClassifiedFile],
                                text_reader: Callable[[ClassifiedFile], Optional[str]]) -> dict:
    """
    Pure planning pass (no DB writes) over one period's client sheet rows
    + classified Drive files: decides, for every row and every gap file,
    exactly which line items to store and why. Callers (a Celery task, an
    API endpoint) turn "line_items" into SalesLineItem rows under
    whatever InvoiceTask/BatchJob bookkeeping they use; kept separate so
    the actual decision logic here is fully unit-testable without a DB.

    Returns:
      {
        "line_items": [{"source_doc_no": ..., "items": [...]}, ...],
        "gap_files": [ClassifiedFile, ...],   # in Drive, no matching sheet row
      }
    """
    sheet_doc_nos = {r["doc_no"] for r in client_rows if r.get("doc_no")}
    line_item_groups = []

    for row in client_rows:
        doc_type = str(row.get("doc_type") or "").strip().lower()
        if "credit" in doc_type or "debit" in doc_type:
            pdf = find_credit_note_pdf_for_row(row, classified_files, text_reader)
            items = build_line_items_for_credit_note_pdf(row, text_reader(pdf)) if pdf else None
            if items is None:
                items = build_line_items_from_sheet_row(row)
        else:
            items = build_line_items_from_sheet_row(row)
        line_item_groups.append({"source_doc_no": row.get("doc_no"), "items": items})

    gap_files = find_gap_files(classified_files, sheet_doc_nos, text_reader)
    return {"line_items": line_item_groups, "gap_files": gap_files}


def ingest_gap_invoice_pdf(db, tenant_id: str, batch_id: str, local_path: str, filename: str,
                            model_config: Optional[dict] = None) -> Optional[str]:
    """
    Runs the full extraction pipeline on a gap invoice PDF (one with no
    matching row in the client sheet at all - see find_gap_files) and
    stores the result as SalesLineItem rows, since the sheet has nothing
    to offer for a document it doesn't know about.
    """
    from invoice_processor import process_pdf
    from models import InvoiceTask, SalesLineItem, TaskStatus

    task_id = str(uuid4())
    task = InvoiceTask(id=task_id, batch_id=batch_id, file_name=filename,
                        status=TaskStatus.PENDING, invoice_type="sales")
    db.add(task)
    db.commit()

    try:
        res = process_pdf(local_path, model_config or {}, "sales")
    except Exception as e:
        logger.error(f"[sheet_first_ingestion] Gap-fill extraction failed for {filename}: {e}")
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        db.commit()
        return None

    for item in (res.sales_items or []):
        db.add(SalesLineItem(
            task_id=task_id, voucher_date=item.voucher_date, voucher_type=item.voucher_type,
            invoice_no=item.invoice_no, party_ledger_name=item.party_ledger_name,
            party_gstin=item.party_gstin, place_of_supply=item.place_of_supply,
            particulars=item.particulars, hsn=item.hsn, qty=item.qty, rate=item.rate,
            taxable_value=item.taxable_value, discount=item.discount, advances=item.advances,
            cgst_amount=item.cgst_amount, sgst_amount=item.sgst_amount, igst_amount=item.igst_amount,
            total_invoice_value=item.total_invoice_value, gstr1_category=item.gstr1_category,
            narration=(f"sheet-first: PDF gap-fill, not found in client sheet. {item.narration or ''}").strip(),
        ))
    task.status = TaskStatus.COMPLETED
    db.commit()
    return task_id


def store_sheet_first_plan(db, tenant_id: str, batch_id: str, plan: dict,
                            model_config: Optional[dict] = None) -> dict:
    """
    Persists plan_sheet_first_ingestion's output: one InvoiceTask per
    sheet document (its line items stored as SalesLineItem rows using the
    sheet's own figures), plus a full extraction run for every gap file
    (credit notes via the existing credit_note_ingest.py path, invoices
    via ingest_gap_invoice_pdf above). Returns counts for the caller to
    report back to whoever triggered this.
    """
    from models import InvoiceTask, SalesLineItem, TaskStatus

    stored_line_items = 0
    for group in plan["line_items"]:
        doc_no = group["source_doc_no"] or "unknown"
        if not group["items"]:
            continue
        task_id = str(uuid4())
        task = InvoiceTask(id=task_id, batch_id=batch_id, file_name=f"client-sheet:{doc_no}",
                            status=TaskStatus.PENDING, invoice_type="sales")
        db.add(task)
        db.commit()
        for item in group["items"]:
            db.add(SalesLineItem(task_id=task_id, **item))
            stored_line_items += 1
        task.status = TaskStatus.COMPLETED
        db.commit()

    gap_task_ids = []
    for f in plan["gap_files"]:
        if f.document_type == DocumentType.CREDIT_NOTE:
            from services.credit_note_ingest import ingest_credit_note_pdf
            task_id = ingest_credit_note_pdf(db, tenant_id, batch_id, f.id, f.name)
        else:
            task_id = ingest_gap_invoice_pdf(db, tenant_id, batch_id, f.id, f.name, model_config)
        if task_id:
            gap_task_ids.append(task_id)

    return {
        "sheet_documents_stored": len([g for g in plan["line_items"] if g["items"]]),
        "sheet_line_items_stored": stored_line_items,
        "gap_files_found": len(plan["gap_files"]),
        "gap_files_extracted": len(gap_task_ids),
    }
