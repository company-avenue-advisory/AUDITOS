"""
gstr2b_drive_verify.py — Targeted Drive-verify service for GSTR-2B
reconciliation Section 13.1, Bucket A (`not_in_books`).

Bucket A means: the supplier filed the invoice in GSTR-2B, but we have no
matching entry in our Purchase Register. Before escalating to the client,
check whether the source invoice PDF actually exists somewhere in the
client's own Drive (uploaded but never booked) — if it does, this is an
internal "entry missing in Tally" fix for the accountant, not something to
bother the client about. See services/gstr2b_excel_export.py's docstring
and memory/project_gstr2b_client_trigger.md for the confirmed workflow.

Design principles (matching the rest of this reconciliation layer):
  - Delta-only: only the unmatched gap set (not_in_books rows) is ever
    checked, never a full Drive re-sync — cost and time stay proportional
    to the gap, not the whole register.
  - Deterministic, not LLM-guessed: a candidate PDF counts as a match only
    if its extracted text contains BOTH the supplier's GSTIN and the
    invoice number — filenames are proven unreliable (see
    drive_classifier.py's docstring) and a single-field match is too weak
    (GSTIN alone often appears twice on any invoice — buyer AND seller;
    invoice number alone can collide on short numbers).
  - Dependency-injected (list_children_fn / download_fn / extract_text_fn),
    same pattern as drive_classifier.walk_and_classify — testable against
    fixtures without live Drive credentials, reusable in production against
    the real GoogleDriveConnector.
"""

import logging
import os
import re
from datetime import date, datetime
from typing import Callable, List, Optional

from services.drive_classifier import DocumentType, walk_and_classify_purchase
from services.drive_path_resolver import TenantDrivePath, resolve_month_folder_id

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """Strip whitespace/punctuation for a loose but deterministic match
    against raw extracted PDF text — same normalization spirit as
    gstr2b_reconciler's normalize_inv/normalize_gstin, kept local since this
    compares against unstructured document text, not another structured
    record."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _parse_2b_date(inv_date: str) -> Optional[date]:
    """GSTR-2B dates are DD-MM-YYYY (see gstr2b_reconciler.parse_gstr2b)."""
    try:
        return datetime.strptime((inv_date or "").strip(), "%d-%m-%Y").date()
    except ValueError:
        return None


def _candidate_month_folder_ids(
    list_children_fn: Callable[[str], List[dict]],
    cfg: TenantDrivePath,
    inv_date: Optional[date],
) -> List[str]:
    """
    The supplier booked the invoice on inv_date, but the client may have
    received/uploaded it into a later month folder — late receipt is far
    more common than early, so this checks the invoice's own month first,
    then the following month, and stops there (this is a targeted check on
    a bounded gap set, not an open-ended search).
    """
    if inv_date is None:
        return []
    months_to_check = [inv_date]
    if inv_date.month == 12:
        months_to_check.append(inv_date.replace(year=inv_date.year + 1, month=1))
    else:
        months_to_check.append(inv_date.replace(month=inv_date.month + 1))

    ids = []
    for m in months_to_check:
        folder_id = resolve_month_folder_id(
            list_children_fn, cfg, m, root_folder_id=cfg.purchase_root_folder_id,
        )
        if folder_id:
            ids.append(folder_id)
    return ids


def _text_matches_invoice(text: str, gstin: str, inv_no: str) -> bool:
    """True only if BOTH the supplier's GSTIN and the invoice number appear
    in the extracted text — see module docstring for why either field alone
    is too weak a signal."""
    if not gstin or not inv_no:
        return False
    norm_text = _normalize(text)
    return _normalize(gstin) in norm_text and _normalize(inv_no) in norm_text


def verify_gap_row_in_drive(
    list_children_fn: Callable[[str], List[dict]],
    download_fn: Callable[[str, str], str],
    extract_text_fn: Callable[[str], str],
    cfg: TenantDrivePath,
    gap_row: dict,
) -> bool:
    """
    Checks one `not_in_books` gap row against the client's Purchase Drive
    tree. Returns True if a PDF matching this invoice's GSTIN + invoice
    number was found.

    gap_row is one entry from gstr2b_reconciler.reconcile()'s "extra" list —
    field names confirmed from that module: supplier_inv, gst_no,
    invoice_date (DD-MM-YYYY), with 2b_inv_no/2b_gstin as the same values
    under their canonical-schema aliases (see output_schema.py's
    GSTR2B_RECONCILIATION_VIEW candidates).

    download_fn(file_id, file_name) -> local temp file path
    extract_text_fn(local_path) -> raw text
    """
    if not cfg.purchase_root_folder_id:
        return False

    gstin = gap_row.get("gst_no") or gap_row.get("2b_gstin") or ""
    inv_no = gap_row.get("supplier_inv") or gap_row.get("2b_inv_no") or ""
    if not gstin or not inv_no:
        return False

    inv_date = _parse_2b_date(gap_row.get("invoice_date") or "")
    folder_ids = _candidate_month_folder_ids(list_children_fn, cfg, inv_date)
    if not folder_ids:
        return False

    for folder_id in folder_ids:
        files = walk_and_classify_purchase(list_children_fn, folder_id)
        for f in files:
            if f.document_type != DocumentType.INVOICE:
                continue
            try:
                local_path = download_fn(f.id, f.name)
                text = extract_text_fn(local_path)
            except Exception as e:
                logger.warning(f"[gstr2b_drive_verify] Could not read {f.name} ({f.id}): {e}")
                continue
            if _text_matches_invoice(text, gstin, inv_no):
                logger.info(
                    f"[gstr2b_drive_verify] Gap invoice {inv_no} (GSTIN {gstin}) "
                    f"matched to Drive file '{f.name}' ({f.id})"
                )
                return True

    return False


def make_drive_checker(
    connector,
    cfg: TenantDrivePath,
    tmp_dir: str,
) -> Callable[[dict], bool]:
    """
    Builds the `drive_checker` callback expected by
    services.gstr2b_excel_export.write_gstr2b_reconciliation_excel — wires a
    real GoogleDriveConnector (services/google_drive.py) plus local
    download/text-extraction into verify_gap_row_in_drive's injected-function
    shape. This is the piece that was intentionally left unwired when the
    Excel export was built (see gstr2b_excel_export.py's docstring) — the
    targeted Drive-verify service itself.
    """
    import fitz  # PyMuPDF — same library credit_note_ingest.py already uses for text extraction

    def _lister(folder_id: str) -> List[dict]:
        # Same adapter shape already used in production by google_drive_sync.py.
        return connector.list_files(file_types=None, folder_id=folder_id)

    def _download(file_id: str, file_name: str) -> str:
        local_path = os.path.join(tmp_dir, f"{file_id}_{file_name}")
        connector.download_file(file_id, file_name, local_path)
        return local_path

    def _extract_text(local_path: str) -> str:
        doc = fitz.open(local_path)
        try:
            return "\n".join(p.get_text() for p in doc)
        finally:
            doc.close()

    def _checker(gap_row: dict) -> bool:
        return verify_gap_row_in_drive(
            list_children_fn=_lister,
            download_fn=_download,
            extract_text_fn=_extract_text,
            cfg=cfg,
            gap_row=gap_row,
        )

    return _checker
