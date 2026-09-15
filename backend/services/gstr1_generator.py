"""
GSTR-1 JSON Generator — produces the filed-format JSON accepted by the
GSTN portal (NIC offline tool / GSP API).

Sections generated:
  b2b   — B2B invoices (registered buyers with GSTIN)
  b2cl  — B2CL invoices (inter-state to unregistered, value > ₹2.5L)
  b2cs  — B2CS consolidated (intra-state or inter-state ≤ ₹2.5L, unregistered)
  exp   — Export invoices
  cdnr  — Credit/Debit Notes for registered persons
  cdnur — Credit/Debit Notes for unregistered persons
  nil   — Nil-rated / exempted / non-GST consolidated
  hsn   — HSN-wise summary
  doc   — Document summary

Reference: GSTN GSTR-1 JSON schema v3.1
"""

import os
import re
from collections import defaultdict
from datetime import datetime
from typing import List, Optional

# Standard GST rates — used to snap calculated rates to nearest valid value
_GST_RATES = [0, 0.1, 0.25, 1, 1.5, 3, 5, 6, 7.5, 12, 18, 28]

# UQC codes accepted by GSTN (unit quantity codes)
_UQC_MAP = {
    "nos": "NOS", "no": "NOS", "pcs": "PCS", "pc": "PCS",
    "kgs": "KGS", "kg": "KGS", "gms": "GMS", "gm": "GMS",
    "mtr": "MTR", "m": "MTR", "ltr": "LTR", "l": "LTR",
    "box": "BOX", "doz": "DOZ", "pkt": "PKT", "set": "SET",
    "sqm": "SQM", "cbm": "CBM", "ton": "TON",
}

B2CL_THRESHOLD = 250000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snap_rate(rate_float: float) -> float:
    """Snap a calculated GST rate to the nearest standard rate."""
    if rate_float <= 0:
        return 0.0
    return min(_GST_RATES, key=lambda r: abs(r - rate_float))


def _derive_gst_rate(taxable: float, cgst: float, sgst: float, igst: float) -> float:
    """Calculate effective GST rate from amounts and snap to standard rate."""
    if taxable <= 0:
        return 0.0
    total_tax = (cgst or 0) + (sgst or 0) + (igst or 0)
    raw = (total_tax / taxable) * 100
    return _snap_rate(raw)


def _parse_date(date_str: Optional[str]) -> str:
    """
    Convert any date string to DD-MM-YYYY (GSTN format).
    Accepts: DD-MMM-YYYY, DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY.
    Returns '' on failure.
    """
    if not date_str:
        return ""
    s = str(date_str).strip()
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
                "%d %b %Y", "%d %B %Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    # Last resort — return as-is if already DD-MM-YYYY
    if re.match(r"\d{2}-\d{2}-\d{4}", s):
        return s
    return ""


def _derive_fp(dates: List[str]) -> str:
    """
    Derive filing period (MMYYYY) from a list of invoice dates.
    Uses the most frequent month, falling back to current month.
    """
    counts: dict = defaultdict(int)
    for d in dates:
        parsed = _parse_date(d)
        if parsed:
            try:
                dt = datetime.strptime(parsed, "%d-%m-%Y")
                counts[dt.strftime("%m%Y")] += 1
            except ValueError:
                pass
    if counts:
        return max(counts, key=lambda k: counts[k])
    return datetime.utcnow().strftime("%m%Y")


def _state_code_from_gstin(gstin: Optional[str]) -> str:
    """Extract 2-digit state code from GSTIN."""
    g = str(gstin or "").strip()
    if len(g) >= 2 and g[:2].isdigit():
        return g[:2]
    return ""


def _state_code_from_pos(pos: Optional[str]) -> str:
    """Extract 2-digit state code from place_of_supply string."""
    p = str(pos or "").strip()
    # "29-Karnataka" or "29" or "KARNATAKA"
    m = re.match(r"^(\d{2})", p)
    if m:
        return m.group(1)
    return ""


def _firm_state_code() -> str:
    gstin = os.getenv("FIRM_GSTIN", "")
    return gstin[:2] if len(gstin) >= 2 else "06"


def _pos_from_row(row, fallback: str) -> str:
    """
    Resolve POS state code for a line item row.
    Priority: place_of_supply field → buyer GSTIN state code → fallback (firm state).
    Handles rows where POS was not extracted at OCR time.
    """
    pos = _state_code_from_pos(row.place_of_supply)
    if pos:
        return pos
    gstin = str(row.party_gstin or "").strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return fallback


def _round2(v) -> float:
    return round(float(v or 0), 2)


def _cn_sign(item) -> int:
    """
    -1 for credit/debit notes, +1 otherwise. Their amounts are stored
    positive (the note's own value - see invoice_processor.extract_credit_note's
    docstring) but they reduce net turnover, so any aggregate built across
    items (envelope totals, HSN summary) must subtract them, not sum them
    in like a second independent sale - the same defect found in both
    generate_gstr1_json's summary totals and _build_hsn against a real MH
    filing this session (an accountant flagged the HSN sheet specifically:
    credit notes were missing from it entirely, silently overstating the
    filed taxable value under every HSN they touched).
    """
    vt = str(getattr(item, "voucher_type", "") or "").lower()
    return -1 if ("credit" in vt or "debit" in vt) else 1


# ---------------------------------------------------------------------------
# Invoice-level aggregation
# ---------------------------------------------------------------------------

def _resolve_category(item) -> str:
    """
    voucher_type is the authoritative signal for credit/debit notes -
    always routes them to CDNR/CDNUR here regardless of item.gstr1_category,
    which may be None (e.g. credit notes ingested via
    credit_note_ingest.py never call classify_gstr1_item) or stale from an
    older extraction path. Without this override, an unclassified item
    falls through to the "or 'B2CS'" default below and a credit note's
    amount gets silently summed into the B2CS consolidated total instead
    of its own CDNR/CDNUR section - which is exactly how a B2CS bucket
    ends up negative (credit notes reduce a customer's liability, they
    aren't "negative sales") and how a filed total stops matching the
    source PDFs (a credit note has its own reporting treatment, it isn't
    interchangeable with a negative B2CS delta).
    """
    voucher_type = str(getattr(item, "voucher_type", "") or "").lower()
    if "credit" in voucher_type or "debit" in voucher_type:
        has_gstin = len(str(item.party_gstin or "").strip()) >= 15
        return "CDNR" if has_gstin else "CDNUR"
    return str(item.gstr1_category or "B2CS").upper()


def _group_by_invoice(items) -> dict:
    """
    Group SalesLineItem rows by (invoice_no, party_gstin, gstr1_category).
    Returns a dict keyed by that tuple.
    """
    groups: dict = defaultdict(list)
    for item in items:
        key = (
            str(item.invoice_no or "").strip(),
            str(item.party_gstin or "").strip(),
            _resolve_category(item),
        )
        groups[key].append(item)
    return groups


def _invoice_totals(rows):
    """Aggregate taxable value, taxes, and total for a group of line items."""
    taxable = sum(_round2(r.taxable_value) for r in rows)
    cgst    = sum(_round2(r.cgst_amount)   for r in rows)
    sgst    = sum(_round2(r.sgst_amount)   for r in rows)
    igst    = sum(_round2(r.igst_amount)   for r in rows)
    total   = sum(_round2(r.total_invoice_value) for r in rows)
    if total == 0:
        total = _round2(taxable + cgst + sgst + igst)
    return taxable, cgst, sgst, igst, total


def _item_detail(taxable, cgst, sgst, igst, rate, num=1) -> dict:
    return {
        "num": num,
        "itm_det": {
            "txval":  _round2(taxable),
            "rt":     rate,
            "iamt":   _round2(igst),
            "camt":   _round2(cgst),
            "samt":   _round2(sgst),
            "csamt":  0.0,
        },
    }


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_b2b(groups: dict, firm_state: str) -> list:
    """
    B2B — one entry per customer GSTIN, invoices nested inside.
    """
    by_ctin: dict = defaultdict(list)
    for (inv_no, gstin, cat), rows in groups.items():
        if cat not in ("B2B",):
            continue
        taxable, cgst, sgst, igst, total = _invoice_totals(rows)
        rate = _derive_gst_rate(taxable, cgst, sgst, igst)
        pos  = _state_code_from_gstin(gstin) or _pos_from_row(rows[0], firm_state)
        idt  = _parse_date(rows[0].voucher_date)
        by_ctin[gstin].append({
            "inum":    inv_no,
            "idt":     idt,
            "val":     _round2(total),
            "pos":     pos,
            "rchrg":   "N",
            "inv_typ": "R",
            "itms":    [_item_detail(taxable, cgst, sgst, igst, rate)],
        })

    return [{"ctin": ctin, "inv": invs} for ctin, invs in by_ctin.items()]


def _build_b2cl(groups: dict, firm_state: str) -> list:
    """
    B2CL — inter-state, unregistered, invoice value > ₹2.5L.
    Grouped by place-of-supply state code.
    """
    by_pos: dict = defaultdict(list)
    for (inv_no, gstin, cat), rows in groups.items():
        if cat != "B2CL":
            continue
        taxable, cgst, sgst, igst, total = _invoice_totals(rows)
        rate = _derive_gst_rate(taxable, cgst, sgst, igst)
        pos  = _pos_from_row(rows[0], firm_state)
        idt  = _parse_date(rows[0].voucher_date)
        by_pos[pos].append({
            "inum": inv_no,
            "idt":  idt,
            "val":  _round2(total),
            "itms": [_item_detail(taxable, 0, 0, igst, rate)],
        })

    return [{"pos": pos, "inv": invs} for pos, invs in by_pos.items()]


def _build_b2cs(groups: dict, firm_state: str) -> list:
    """
    B2CS — consolidated by (supply_type, POS, rate). No per-invoice breakdown.
    """
    consolidated: dict = defaultdict(lambda: {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0})
    for (inv_no, gstin, cat), rows in groups.items():
        if cat != "B2CS":
            continue
        taxable, cgst, sgst, igst, total = _invoice_totals(rows)
        rate = _derive_gst_rate(taxable, cgst, sgst, igst)
        pos  = _pos_from_row(rows[0], firm_state)
        sply_tp = "INTER" if (pos != firm_state) else "INTRA"
        key = (sply_tp, pos, rate)
        consolidated[key]["txval"] += taxable
        consolidated[key]["iamt"]  += igst
        consolidated[key]["camt"]  += cgst
        consolidated[key]["samt"]  += sgst

    result = []
    for (sply_tp, pos, rate), vals in consolidated.items():
        result.append({
            "sply_tp": sply_tp,
            "pos":     pos,
            "typ":     "OE",
            "rt":      rate,
            "txval":   _round2(vals["txval"]),
            "iamt":    _round2(vals["iamt"]),
            "camt":    _round2(vals["camt"]),
            "samt":    _round2(vals["samt"]),
            "csamt":   0.0,
        })
    return result


def _build_exp(groups: dict) -> list:
    """
    EXP — export invoices. Grouped by export type (WOPAY/WPAY).
    """
    by_exp_typ: dict = defaultdict(list)
    for (inv_no, gstin, cat), rows in groups.items():
        if cat != "EXP":
            continue
        taxable, cgst, sgst, igst, total = _invoice_totals(rows)
        rate = _derive_gst_rate(taxable, cgst, sgst, igst)
        idt  = _parse_date(rows[0].voucher_date)
        # Determine if with-payment or without-payment of IGST
        exp_typ = "WOPAY" if igst == 0 else "WPAY"
        by_exp_typ[exp_typ].append({
            "inum":   inv_no,
            "idt":    idt,
            "val":    _round2(total),
            "sbpcode": "",
            "sbnum":   "",
            "sbdt":    "",
            "itms":   [{"txval": _round2(taxable), "rt": rate, "iamt": _round2(igst), "csamt": 0.0}],
        })

    return [{"exp_typ": exp_typ, "inv": invs} for exp_typ, invs in by_exp_typ.items()]


def _build_cdnr(groups: dict, firm_state: str) -> list:
    """CDNR — credit/debit notes for registered persons."""
    by_ctin: dict = defaultdict(list)
    for (inv_no, gstin, cat), rows in groups.items():
        if cat != "CDNR":
            continue
        taxable, cgst, sgst, igst, total = _invoice_totals(rows)
        rate = _derive_gst_rate(taxable, cgst, sgst, igst)
        pos  = _state_code_from_gstin(gstin) or firm_state
        idt  = _parse_date(rows[0].voucher_date)
        vtype = str(rows[0].voucher_type or "").lower()
        ntty = "D" if "debit" in vtype else "C"
        by_ctin[gstin].append({
            "ntty":    ntty,
            "nt_num":  inv_no,
            "nt_dt":   idt,
            "val":     _round2(total),
            "pos":     pos,
            "rchrg":   "N",
            "inv_typ": "R",
            "itms":    [_item_detail(taxable, cgst, sgst, igst, rate)],
        })

    return [{"ctin": ctin, "nt": notes} for ctin, notes in by_ctin.items()]


def _build_cdnur(groups: dict, firm_state: str) -> list:
    """CDNUR — credit/debit notes for unregistered persons."""
    entries = []
    for (inv_no, gstin, cat), rows in groups.items():
        if cat != "CDNUR":
            continue
        taxable, cgst, sgst, igst, total = _invoice_totals(rows)
        rate = _derive_gst_rate(taxable, cgst, sgst, igst)
        pos  = _pos_from_row(rows[0], firm_state)
        idt  = _parse_date(rows[0].voucher_date)
        vtype = str(rows[0].voucher_type or "").lower()
        ntty  = "D" if "debit" in vtype else "C"
        sply_tp = "INTER" if pos != firm_state else "INTRA"
        entries.append({
            "ntty":    ntty,
            "nt_num":  inv_no,
            "nt_dt":   idt,
            "val":     _round2(total),
            "pos":     pos,
            "typ":     sply_tp,
            "itms":    [_item_detail(taxable, cgst, sgst, igst, rate)],
        })
    return entries


def _build_nil(items) -> dict:
    """NIL — consolidated nil-rated, exempted, and non-GST supplies."""
    nil_intra = {"sply_ty": "INTRB2B", "expt_amt": 0.0, "nil_amt": 0.0, "ngsup_amt": 0.0}
    nil_inter = {"sply_ty": "INTRB2C", "expt_amt": 0.0, "nil_amt": 0.0, "ngsup_amt": 0.0}
    firm_state = _firm_state_code()

    for item in items:
        cat = str(item.gstr1_category or "").upper()
        if cat not in ("NIL", "EXEMPT", "NIL_EXEMPT"):
            continue
        taxable = _round2(item.taxable_value)
        pos = _pos_from_row(item, firm_state)
        target = nil_intra if pos == firm_state else nil_inter
        target["expt_amt"] += taxable

    return {"inv": [nil_intra, nil_inter]}


def _build_hsn(items) -> dict:
    """HSN summary — aggregated by HSN + GST rate. Credit/debit notes
    subtract from their HSN's totals rather than being omitted or summed
    in (see _cn_sign's docstring) - omitting them entirely (the pre-fix
    behavior) silently overstated every HSN bucket a credit note touched."""
    by_hsn: dict = defaultdict(lambda: {"qty": 0.0, "txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "val": 0.0, "desc": ""})

    for item in items:
        hsn = str(item.hsn or "").strip()
        if not hsn:
            continue
        sign    = _cn_sign(item)
        taxable = sign * _round2(item.taxable_value)
        cgst    = sign * _round2(item.cgst_amount)
        sgst    = sign * _round2(item.sgst_amount)
        igst    = sign * _round2(item.igst_amount)
        total   = sign * (_round2(item.total_invoice_value) or (abs(taxable) + abs(cgst) + abs(sgst) + abs(igst)))
        rate    = _derive_gst_rate(abs(taxable), abs(cgst), abs(sgst), abs(igst))
        key     = (hsn, rate)
        row     = by_hsn[key]
        row["qty"]   += sign * float(item.qty or 0)
        row["txval"] += taxable
        row["iamt"]  += igst
        row["camt"]  += cgst
        row["samt"]  += sgst
        row["val"]   += total
        if not row["desc"]:
            row["desc"] = str(item.particulars or "")[:30]

    data = []
    for num, ((hsn, rate), row) in enumerate(by_hsn.items(), 1):
        data.append({
            "num":    num,
            "hsn_sc": hsn,
            "desc":   row["desc"],
            "uqc":    "NOS",
            "qty":    _round2(row["qty"]),
            "val":    _round2(row["val"]),
            "txval":  _round2(row["txval"]),
            "rt":     rate,
            "iamt":   _round2(row["iamt"]),
            "camt":   _round2(row["camt"]),
            "samt":   _round2(row["samt"]),
            "csamt":  0.0,
        })
    return {"data": data}


def _build_doc_summary(items, b2b, b2cl, b2cs, exp, cdnr, cdnur) -> dict:
    """DOC — document summary (invoice counts by type)."""
    def _count_inv(section):
        if isinstance(section, list):
            return sum(len(e.get("inv", e.get("nt", []))) for e in section)
        return 0

    total_inv = _count_inv(b2b) + _count_inv(b2cl) + len(b2cs) + _count_inv(exp)
    total_cdn = _count_inv(cdnr) + len(cdnur)

    return {
        "docdet": [
            {
                "doc_num": 1,
                "doc_typ": "Invoices for outward supply",
                "docs": [{"num": 1, "to": total_inv, "totnum": total_inv, "cancel": 0, "net_issue": total_inv}],
            },
            {
                "doc_num": 2,
                "doc_typ": "Credit Note",
                "docs": [{"num": 1, "to": total_cdn, "totnum": total_cdn, "cancel": 0, "net_issue": total_cdn}],
            },
        ]
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_gstr1_json(items, firm_gstin: str = None) -> dict:
    """
    Generate a GSTR-1 filed-format JSON from a list of SalesLineItem ORM rows.

    Args:
        items:       List of SalesLineItem rows from the DB.
        firm_gstin:  Seller's GSTIN (15 chars). Falls back to FIRM_GSTIN env var.

    Returns:
        GSTR-1 JSON dict — ready to write to file or POST to GSP API.
    """
    if not firm_gstin:
        firm_gstin = os.getenv("FIRM_GSTIN", "")

    firm_state = firm_gstin[:2] if len(firm_gstin) >= 2 else "06"

    # Filing period from invoice dates
    all_dates = [str(i.voucher_date or "") for i in items if i.voucher_date]
    fp = _derive_fp(all_dates)

    groups = _group_by_invoice(items)

    b2b   = _build_b2b(groups, firm_state)
    b2cl  = _build_b2cl(groups, firm_state)
    b2cs  = _build_b2cs(groups, firm_state)
    exp   = _build_exp(groups)
    cdnr  = _build_cdnr(groups, firm_state)
    cdnur = _build_cdnur(groups, firm_state)
    nil   = _build_nil(items)
    hsn   = _build_hsn(items)
    doc   = _build_doc_summary(items, b2b, b2cl, b2cs, exp, cdnr, cdnur)

    # Summary totals for the envelope - NET of credit/debit notes (see
    # _cn_sign's docstring for why these must subtract, not sum).
    total_taxable = _round2(sum(_cn_sign(i) * float(i.taxable_value or 0) for i in items))
    total_igst    = _round2(sum(_cn_sign(i) * float(i.igst_amount  or 0) for i in items))
    total_cgst    = _round2(sum(_cn_sign(i) * float(i.cgst_amount  or 0) for i in items))
    total_sgst    = _round2(sum(_cn_sign(i) * float(i.sgst_amount  or 0) for i in items))
    total_tax     = _round2(total_igst + total_cgst + total_sgst)

    return {
        "gstin": firm_gstin,
        "fp":    fp,
        "gt":    _round2(sum(float(i.total_invoice_value or 0) for i in items)),
        "cur_gt": _round2(sum(float(i.total_invoice_value or 0) for i in items)),
        # Sections
        "b2b":   b2b,
        "b2cl":  b2cl,
        "b2cs":  b2cs,
        "exp":   exp,
        "cdnr":  cdnr,
        "cdnur": cdnur,
        "nil":   nil,
        "hsn":   hsn,
        "doc":   doc,
        # Summary (used by portal for validation)
        "_summary": {
            "filing_period":   fp,
            "total_invoices":  len(groups),
            "total_taxable":   total_taxable,
            "total_igst":      total_igst,
            "total_cgst":      total_cgst,
            "total_sgst":      total_sgst,
            "total_tax":       total_tax,
            "sections_with_data": [
                s for s, v in [("b2b", b2b), ("b2cl", b2cl), ("b2cs", b2cs),
                                ("exp", exp), ("cdnr", cdnr), ("cdnur", cdnur)]
                if v
            ],
        },
    }
