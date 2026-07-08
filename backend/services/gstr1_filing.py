"""
Orchestrates GSTR-1 filing generation from OS-extracted SalesLineItem rows,
gated by sales_reconciliation.py's output, and split across a tenant's
multiple GST registrations (OneStack files under two: Maharashtra
27AADCO0061H1ZQ for MH/OMH invoice numbers, Haryana 06AADCO0061H1ZU for
HR/OHR). The actual per-section JSON building (b2b/b2cl/b2cs/cdnr/cdnur/
hsn/doc) is unchanged, existing code in gstr1_generator.py - this module
only decides WHICH items go into WHICH registration's filing, and WHICH
items don't go in at all.

Reconciliation-status gating policy (confirmed with the user 2026-07-08):
  - PASS, CLIENT_SHEET_ERROR, CLIENT_MISSING -> included normally. A
    CLIENT_SHEET_ERROR means our data is CONFIRMED correct (that's what
    the status means - we checked, the client is wrong) - it is not a
    reason to hold our own correct data out of a filing.
  - UNRESOLVED_CONFLICT -> included (our data did come from an actual
    parsed PDF), but flagged in the output so a human knows there's an
    unresolved discrepancy against the client's sheet worth a second look.
  - MISSING_SOURCE_PDF, UNVERIFIABLE_NO_GSTIN -> excluded entirely (there
    is nothing usable to file), but surfaced as a clear skipped-list in
    the output rather than silently dropped.
"""
import os
import sys

# Bare "from services.X import Y" below needs backend/ itself on
# sys.path, not just the project root - matches the bootstrap already in
# invoice_processor.py, needed here because this module (unlike its
# services/ siblings) imports another services/ module by bare name.
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.sales_reconciliation import ReconEntry, ReconStatus

_EXCLUDE_STATUSES = {ReconStatus.MISSING_SOURCE_PDF, ReconStatus.UNVERIFIABLE_NO_GSTIN}
_FLAG_STATUSES = {ReconStatus.UNRESOLVED_CONFLICT}


@dataclass
class FilingFilterResult:
    included: list = field(default_factory=list)          # SalesLineItem rows to file
    flagged_doc_nos: set = field(default_factory=set)      # unresolved, included anyway
    skipped: List[dict] = field(default_factory=list)      # [{"doc_no", "status", "note"}]


def filter_items_for_filing(items, recon_entries: List[ReconEntry]) -> FilingFilterResult:
    """
    Splits OS-extracted line items into what goes into a filing vs. what
    doesn't, per the gating policy above. Items with no matching
    reconciliation entry at all (reconciliation never ran, or ran against
    a different period) are included by default - reconciliation being
    unavailable is not the same as reconciliation having flagged a
    problem, and must not silently block a filing.
    """
    status_by_doc = {e.doc_no: e.status for e in recon_entries}
    result = FilingFilterResult()

    by_doc: Dict[str, list] = defaultdict(list)
    for item in items:
        by_doc[str(item.invoice_no or "").strip()].append(item)

    for doc_no, rows in by_doc.items():
        status = status_by_doc.get(doc_no)
        if status in _EXCLUDE_STATUSES:
            entry = next((e for e in recon_entries if e.doc_no == doc_no), None)
            result.skipped.append({
                "doc_no": doc_no,
                "status": status.value,
                "note": entry.note if entry else "",
            })
            continue
        result.included.extend(rows)
        if status in _FLAG_STATUSES:
            result.flagged_doc_nos.add(doc_no)

    return result


def _registration_prefix(invoice_no: str) -> str:
    """Letters-only prefix of an invoice number, e.g. 'OMH26061001' -> 'OMH'."""
    return "".join(ch for ch in str(invoice_no or "") if not ch.isdigit())


import re

_ORIGINAL_INVOICE_RE = re.compile(r'\(against ([A-Za-z]*\d+)\)')


def _routing_prefix(item) -> str:
    """
    The prefix used to determine which registration an item belongs to.
    Credit notes are always "CR"-prefixed (CR26061001 etc) regardless of
    which registration their ORIGINAL invoice was under - "CR" itself
    never maps to a registration. credit_note_ingest.py embeds the
    original invoice number in particulars ("Credit Note - {reason}
    (against {original_invoice_no})"), so for credit notes we route by
    that original invoice's prefix instead.
    """
    prefix = _registration_prefix(item.invoice_no)
    if prefix == "CR":
        m = _ORIGINAL_INVOICE_RE.search(str(getattr(item, "particulars", "") or ""))
        if m:
            return _registration_prefix(m.group(1))
    return prefix


def split_items_by_registration(items, registration_map: Dict[str, str]) -> Dict[str, list]:
    """
    Splits items by which GST registration they were invoiced under,
    based on invoice-number prefix (or, for credit notes, their original
    invoice's prefix - see _routing_prefix). registration_map maps
    prefix -> GSTIN, e.g. {"MH": "27AADCO0061H1ZQ", "OMH": "27AADCO0061H1ZQ",
          "HR": "06AADCO0061H1ZU", "OHR": "06AADCO0061H1ZU"}.

    Items whose prefix isn't in registration_map are returned under the
    key None, so callers can see (and investigate) anything unexpected
    rather than have it silently vanish into one registration or another.
    """
    by_gstin: Dict[Optional[str], list] = defaultdict(list)
    for item in items:
        prefix = _routing_prefix(item)
        gstin = registration_map.get(prefix)
        by_gstin[gstin].append(item)
    return dict(by_gstin)


def generate_gstr1_filings(items, recon_entries: List[ReconEntry],
                            registration_map: Dict[str, str]) -> Dict[str, dict]:
    """
    Full pipeline: filter by reconciliation status, split by registration,
    generate the GSTR-1 JSON for each registration via the existing
    gstr1_generator.generate_gstr1_json. Returns one dict per GSTIN:
        {
          "gstin": ...,
          "gstr1_json": {...},          # from gstr1_generator
          "flagged_unresolved": [...],  # doc_nos included but disputed
          "skipped": [...],             # docs excluded, with reason
        }
    Items whose invoice-number prefix doesn't match any known
    registration are returned under the "UNKNOWN_REGISTRATION" key with
    gstr1_json=None, rather than silently dropped or guessed into a
    registration they may not belong to.
    """
    from services.gstr1_generator import generate_gstr1_json

    filtered = filter_items_for_filing(items, recon_entries)
    by_registration = split_items_by_registration(filtered.included, registration_map)

    results = {}
    for gstin, reg_items in by_registration.items():
        reg_doc_nos = {str(i.invoice_no or "").strip() for i in reg_items}
        key = gstin or "UNKNOWN_REGISTRATION"
        results[key] = {
            "gstin": gstin,
            "gstr1_json": generate_gstr1_json(reg_items, firm_gstin=gstin) if gstin else None,
            "flagged_unresolved": sorted(filtered.flagged_doc_nos & reg_doc_nos),
            "skipped": [s for s in filtered.skipped if s["doc_no"] in reg_doc_nos],
        }

    # any skipped doc's registration is unknowable (it was excluded before
    # the registration split), so surface all of them under every result
    # missing one is worse than a bit of duplication for visibility
    all_skipped = filtered.skipped
    for r in results.values():
        r["all_skipped_this_period"] = all_skipped

    return results


# OneStack's real registration prefix mapping, confirmed against 197 real
# June 2026 invoices this session - kept here as the default for
# convenience, but callers can always pass their own registration_map for
# a different tenant.
ONESTACK_REGISTRATION_MAP = {
    "MH": "27AADCO0061H1ZQ", "OMH": "27AADCO0061H1ZQ",
    "HR": "06AADCO0061H1ZU", "OHR": "06AADCO0061H1ZU",
}
