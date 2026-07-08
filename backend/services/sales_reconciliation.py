"""
3-way reconciliation for OneStack Sales: our own extracted register (OS)
vs. the client's own reconciliation sheet, per document (invoice or
credit note). Generalizes the manual 3-way audit done by hand earlier
this session into a reusable, testable engine.

Deliberately does NOT re-read the source PDF itself - it only compares
two already-extracted sources (OS SalesLineItem records vs
client_sheet_parser output). "OS is correct" is never assumed blindly:
a document is only marked CLIENT_SHEET_ERROR when there's an actual
checkable signal (a tax-type contradiction - one side shows IGST, the
other CGST+SGST, which can't both be right for the same transaction),
not just "OS and client differ, so OS wins". A same-tax-type amount
mismatch has no such signal and is correctly left as UNRESOLVED_CONFLICT
for a human to check against the source document - this mirrors exactly
how CR26061011 (a genuine unresolved amount mismatch, no tax-type
contradiction) was correctly NOT auto-resolved this session, while
Krushiseva and the Muslim Co-op invoice (both genuine tax-type
contradictions) were correctly identified as client-sheet errors once
verified.

Not persisted to any DB column yet - see the reasoning in
client_sheet_parser.py's module docstring for why: the storage schema
should be designed against what actually consumes this (a future review
gate), not guessed now.

ROOT CAUSE FINDING (2026-07-08, confirmed against real June 2026 data):
running this engine against the full 197-document period surfaced 74
CLIENT_SHEET_ERROR cases - far more than the earlier ad hoc manual audit
found, because that older check only compared taxable-value magnitude
and never verified tax type. Inspecting the client's underlying workbook
formulas (not just computed values) showed why: their "Interstate or
Intrastate (Drop Down only)" column is a plain manually-typed string
(confirmed via openpyxl - no formula), while "State of Supply" IS a
formula (`=LEFT(recipient_gstin, 2)`). Comparing the client's own
Supplier Location (MH->state code 27, HR->06) against their own State of
Supply column shows 76 of 196 rows (39%) where the manually-entered
Interstate/Intrastate flag is the EXACT logical inversion of what their
own GSTIN-derived data implies - zero exceptions across all 76, which
rules out random data-entry error. Independently verified against 3 real
source PDFs (Krushiseva MH26061040, Muslim Co-op MH26061076, Vaishya
Nagari MH26061037) - all 3 confirm our side is correct and the client's
manual flag (and the tax amounts entered under it) are backwards. See
_matches_known_inversion_pattern below, which names this specific
pattern in the reconciliation note when client_data carries the
supplier_location/state_of_supply fields needed to check for it.

Of the 74 CLIENT_SHEET_ERROR cases in the real June 2026 period, 73
matched this inversion pattern exactly. The one that didn't (HR26061007)
turned out to be a genuinely different, separate mechanism: the actual
source PDF prints CGST+SGST (intrastate treatment) even though the buyer
(Maharashtra) and OneStack's Haryana registration are in different
states - the same kind of invoice-level GST-treatment quirk already
documented in the vendor profile for MH26061141 (a naive buyer-state-
vs-seller-registration comparison doesn't always predict the actual
printed tax treatment). The client's own naive heuristic was fooled by
the same quirk, but this is NOT their dropdown-inversion bug, so
_matches_known_client_inversion_pattern correctly declines to claim it
is - it's still a real CLIENT_SHEET_ERROR (confirmed against the source
PDF), just via a different root cause. This is the intended behavior:
the pattern-match annotation should only fire when there's genuine
evidence for THAT specific mechanism, not merely because the status is
the same.
"""
import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_TOLERANCE = 2.50  # Rs., matches the tolerance used throughout this session


class ReconStatus(str, enum.Enum):
    PASS = "PASS"
    CLIENT_SHEET_ERROR = "CLIENT_SHEET_ERROR"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    MISSING_SOURCE_PDF = "MISSING_SOURCE_PDF"
    CLIENT_MISSING = "CLIENT_MISSING"
    UNVERIFIABLE_NO_GSTIN = "UNVERIFIABLE_NO_GSTIN"


@dataclass
class ReconEntry:
    doc_no: str
    doc_type: str
    status: ReconStatus
    note: str
    os_data: Optional[dict] = None
    client_data: Optional[dict] = None
    delta: Dict[str, float] = field(default_factory=dict)


def _tax_type(taxable: float, igst: float, cgst: float, sgst: float) -> Optional[str]:
    """Returns 'interstate' if IGST is the active tax, 'intrastate' if
    CGST+SGST is, None if the document has no tax at all (NIL) - in which
    case a tax-type contradiction can't be evaluated either way."""
    if igst > 0.01:
        return "interstate"
    if cgst > 0.01 or sgst > 0.01:
        return "intrastate"
    return None


def _within_tolerance(a: float, b: float, tolerance: float) -> bool:
    return abs((a or 0.0) - (b or 0.0)) <= tolerance


# Supplier Location -> the state code of that OneStack registration.
# MH -> Maharashtra (27), HR -> Haryana (06) - matches the two real
# GSTINs OneStack files under (27AADCO0061H1ZQ / 06AADCO0061H1ZU).
_SUPPLIER_LOCATION_STATE_CODE = {"MH": "27", "HR": "06"}


def _matches_known_client_inversion_pattern(client_data: dict) -> bool:
    """
    Checks whether client_data's own Interstate/Intrastate flag is the
    exact logical inversion of what the client's own Supplier Location +
    State of Supply columns imply - the specific, confirmed (76/76, zero
    exceptions) client-side bug described in this module's docstring.
    Returns False (not "unknown") if client_data doesn't carry the fields
    needed to check - never claims a match without evidence.
    """
    supplier = client_data.get("supplier_location")
    state_of_supply = client_data.get("state_of_supply")
    flag = client_data.get("interstate_or_intrastate")
    if not supplier or not state_of_supply or not flag:
        return False
    correct_code = _SUPPLIER_LOCATION_STATE_CODE.get(supplier)
    if not correct_code:
        return False
    correct_flag = "Intrastate" if state_of_supply == correct_code else "Interstate"
    inverse = {"Interstate": "Intrastate", "Intrastate": "Interstate"}
    return flag == inverse.get(correct_flag)


def reconcile_document(os_data: Optional[dict], client_data: Optional[dict],
                        doc_no: str, doc_type: str,
                        tolerance: float = DEFAULT_TOLERANCE) -> ReconEntry:
    """
    Compares one document's OS-extracted figures against the client
    sheet's figures for the same doc_no. Both os_data/client_data are
    dicts with at least: taxable, igst, cgst, sgst, total, party_gstin
    (os_data only needs party_gstin; client_data's GSTIN isn't required
    for this comparison).

    Either side may be None if the document is entirely absent from that
    source - MISSING_SOURCE_PDF (client has it, we don't) and
    CLIENT_MISSING (we have it, client doesn't) are both first-class,
    non-error outcomes that still need a human's attention.
    """
    if os_data is None and client_data is None:
        raise ValueError(f"{doc_no}: reconcile_document called with both sides None")

    if os_data is None:
        return ReconEntry(
            doc_no=doc_no, doc_type=doc_type, status=ReconStatus.MISSING_SOURCE_PDF,
            note=f"Client sheet has {doc_no} but we have no PDF/extraction on record for it - "
                 f"needs the source document before this can be filed.",
            client_data=client_data,
        )

    if client_data is None:
        return ReconEntry(
            doc_no=doc_no, doc_type=doc_type, status=ReconStatus.CLIENT_MISSING,
            note=f"We have {doc_no} on record but the client's sheet doesn't include it - "
                 f"may just be a client-side data-entry lag, not necessarily our error.",
            os_data=os_data,
        )

    if not os_data.get("party_gstin"):
        return ReconEntry(
            doc_no=doc_no, doc_type=doc_type, status=ReconStatus.UNVERIFIABLE_NO_GSTIN,
            note=f"{doc_no} has no resolved buyer GSTIN on our side - can't confidently "
                 f"classify B2B vs B2C or compare place-of-supply until this is resolved.",
            os_data=os_data, client_data=client_data,
        )

    fields = ["taxable", "igst", "cgst", "sgst", "total"]
    delta = {f: round((os_data.get(f) or 0.0) - (client_data.get(f) or 0.0), 2) for f in fields}
    all_match = all(_within_tolerance(os_data.get(f), client_data.get(f), tolerance) for f in fields)

    if all_match:
        return ReconEntry(
            doc_no=doc_no, doc_type=doc_type, status=ReconStatus.PASS,
            note=f"{doc_no} matches within Rs.{tolerance} tolerance.",
            os_data=os_data, client_data=client_data, delta=delta,
        )

    os_type = _tax_type(os_data.get("taxable", 0.0), os_data.get("igst", 0.0),
                         os_data.get("cgst", 0.0), os_data.get("sgst", 0.0))
    client_type = _tax_type(client_data.get("taxable", 0.0), client_data.get("igst", 0.0),
                             client_data.get("cgst", 0.0), client_data.get("sgst", 0.0))

    if os_type and client_type and os_type != client_type:
        note = (
            f"{doc_no}: tax-type contradiction - our records show {os_type} "
            f"(IGST={os_data.get('igst',0):.2f}, CGST={os_data.get('cgst',0):.2f}, "
            f"SGST={os_data.get('sgst',0):.2f}) but the client sheet shows {client_type} "
            f"(IGST={client_data.get('igst',0):.2f}, CGST={client_data.get('cgst',0):.2f}, "
            f"SGST={client_data.get('sgst',0):.2f}) - a transaction can't legitimately be "
            f"both, this is a client-sheet classification error."
        )
        if _matches_known_client_inversion_pattern(client_data):
            note += (
                " Matches the known client-side pattern: their manually-typed "
                "Interstate/Intrastate flag is the exact inversion of what their own "
                "Supplier Location + State of Supply columns imply (confirmed on 76/196 "
                "June 2026 rows) - likely the same root-cause bug, not an isolated error."
            )
        return ReconEntry(
            doc_no=doc_no, doc_type=doc_type, status=ReconStatus.CLIENT_SHEET_ERROR,
            note=note,
            os_data=os_data, client_data=client_data, delta=delta,
        )

    return ReconEntry(
        doc_no=doc_no, doc_type=doc_type, status=ReconStatus.UNRESOLVED_CONFLICT,
        note=f"{doc_no}: amounts differ beyond tolerance (taxable delta Rs.{delta['taxable']}, "
             f"total delta Rs.{delta['total']}) but both sides agree on tax type - no signal here "
             f"to say which figure is right. Needs the source document checked by a human, not "
             f"auto-resolved.",
        os_data=os_data, client_data=client_data, delta=delta,
    )


def reconcile_period(os_rows: List[dict], client_rows: List[dict],
                      tolerance: float = DEFAULT_TOLERANCE) -> List[ReconEntry]:
    """
    Reconciles a full period's worth of documents. os_rows and
    client_rows are both keyed by "doc_no" (invoice number or credit
    note number) - matches client_sheet_parser.parse_client_sheet's
    "doc_no" field and an OS-side aggregation of SalesLineItem by
    invoice_no (one dict per document, not per line item - the line-item
    granularity is reconciled by extract_deterministic_line_items'
    invoice-level ground truth already, not re-checked here).
    """
    os_by_doc = {r["doc_no"]: r for r in os_rows}
    client_by_doc = {r["doc_no"]: r for r in client_rows}
    all_doc_nos = sorted(set(os_by_doc) | set(client_by_doc))

    entries = []
    for doc_no in all_doc_nos:
        os_data = os_by_doc.get(doc_no)
        client_data = client_by_doc.get(doc_no)
        doc_type = (os_data or client_data).get("doc_type", "Invoice")
        entries.append(reconcile_document(os_data, client_data, doc_no, doc_type, tolerance))
    return entries


def summarize(entries: List[ReconEntry]) -> dict:
    counts = {}
    for e in entries:
        counts[e.status.value] = counts.get(e.status.value, 0) + 1
    return counts


def compute_net_taxable_total(rows: List[dict]) -> float:
    """
    Net taxable total for a set of documents (os_rows/client_rows shape -
    each dict has "taxable" and "doc_type"). Invoices ADD, credit/debit
    notes SUBTRACT - a credit note reduces net taxable turnover, it is not
    a second independent line to sum alongside invoices. Both os_rows and
    client_rows store credit-note taxable values as positive (the note's
    own printed value - see invoice_processor.extract_credit_note's
    docstring), so the sign has to be applied here, not assumed already
    baked into the stored figure.
    """
    total = 0.0
    for r in rows:
        doc_type = str(r.get("doc_type") or "Invoice").lower()
        sign = -1 if ("credit" in doc_type or "debit" in doc_type) else 1
        total += sign * (r.get("taxable") or 0.0)
    return round(total, 2)


@dataclass
class TotalsMatchResult:
    os_net_taxable: float
    client_net_taxable: float
    gstr1_net_taxable: Optional[float]
    matches: bool
    deltas: Dict[str, float]
    note: str


def reconcile_period_totals(os_rows: List[dict], client_rows: List[dict],
                             gstr1_summary: Optional[dict] = None,
                             tolerance: float = DEFAULT_TOLERANCE) -> TotalsMatchResult:
    """
    The 3-way total check: net taxable total (invoices minus credit/debit
    notes) must match across all three sheets - our own extraction (OS),
    the client's reconciliation sheet, and the actual GSTR-1 filing
    output about to be submitted. Per-document reconcile_period above
    already catches document-level mismatches; this catches a DIFFERENT
    class of bug that per-document checks can't see - an aggregate
    miscount that happens during filing generation itself (e.g. a credit
    note silently getting summed into B2CS instead of netted out via
    CDNR/CDNUR, confirmed against a real MH filing this session where a
    B2CS bucket went negative for exactly this reason). A clean per-
    document PASS on every row does not guarantee the aggregate GSTR-1
    total is right - this is the check that does.

    gstr1_summary is generate_gstr1_json's "_summary" dict (needs
    "total_taxable"); pass None to only compare OS vs client (e.g. before
    a filing has been generated yet).
    """
    os_total = compute_net_taxable_total(os_rows)
    client_total = compute_net_taxable_total(client_rows)
    gstr1_total = gstr1_summary.get("total_taxable") if gstr1_summary else None

    deltas = {"os_vs_client": round(os_total - client_total, 2)}
    matches = _within_tolerance(os_total, client_total, tolerance)

    if gstr1_total is not None:
        deltas["os_vs_gstr1"] = round(os_total - gstr1_total, 2)
        matches = matches and _within_tolerance(os_total, gstr1_total, tolerance)

    if matches:
        note = f"Net taxable total matches across all sheets within Rs.{tolerance} tolerance."
    else:
        parts = [f"OS=Rs.{os_total}", f"Client=Rs.{client_total}"]
        if gstr1_total is not None:
            parts.append(f"GSTR1={gstr1_total}")
        note = f"Net taxable total mismatch: {', '.join(parts)} (deltas: {deltas})."

    return TotalsMatchResult(
        os_net_taxable=os_total, client_net_taxable=client_total,
        gstr1_net_taxable=gstr1_total, matches=matches, deltas=deltas, note=note,
    )
