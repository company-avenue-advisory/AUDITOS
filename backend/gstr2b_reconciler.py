"""
gstr2b_reconciler.py
====================
Core GSTR-2B reconciliation engine.

Parses the GSTR-2B JSON downloaded from the GST portal and matches it
against invoice line items extracted from PDFs.

Match key: normalize(GSTIN) + normalize(Invoice Number)

Statuses:
  matched        — GSTIN + InvNo match, amounts within ₹2 tolerance
  mismatch       — GSTIN + InvNo match, amount differs > ₹2
  missing_in_2b  — In books (PDFs), NOT found in GSTR-2B → ITC at risk
  not_in_books   — In GSTR-2B, NOT found in books → missed booking
"""

import re
import json
from typing import Any


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_inv(s: str) -> str:
    """Normalize invoice number for fuzzy matching: uppercase, strip spaces/dashes/slashes."""
    if not s:
        return ""
    return re.sub(r"[\s\-/\\]", "", str(s).strip().upper())


def normalize_gstin(s: str) -> str:
    """Normalize GSTIN: uppercase, strip spaces."""
    if not s:
        return ""
    return str(s).strip().upper().replace(" ", "")


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# ── GSTR-2B Parser ────────────────────────────────────────────────────────────

def parse_gstr2b(raw: dict) -> list[dict]:
    """
    Flatten a GSTR-2B JSON into a list of invoice-level records.

    Supports two common JSON shapes:
      Shape A (portal full download):
        data.docdata.b2b[].ctin / .inv[].inum / .inv[].itms[]
      Shape B (simplified / third-party exports):
        b2b[].ctin / .inv[] ...

    Returns a list of dicts, each representing ONE invoice from 2B:
      {
        "gstin":      "29XXXXX...",
        "inv_no":     "INV/2024/001",
        "inv_date":   "01-04-2024",
        "taxable_val":  10000.0,
        "igst":         1800.0,
        "cgst":          900.0,
        "sgst":          900.0,
        "total_val":   11800.0,
        "_norm_key":  "29XXXXX...||INV2024001",   # for matching
      }
    """
    records = []

    # Navigate to the b2b array — try multiple known paths
    b2b_list = (
        _dig(raw, "data", "docdata", "b2b")
        or _dig(raw, "docdata", "b2b")
        or _dig(raw, "b2b")
        or []
    )

    for supplier in b2b_list:
        gstin = normalize_gstin(supplier.get("ctin") or supplier.get("gstin") or "")
        inv_list = supplier.get("inv") or supplier.get("invoices") or []

        for inv in inv_list:
            inv_no   = str(inv.get("inum") or inv.get("inv_no") or inv.get("invNo") or "").strip()
            inv_date = str(inv.get("dt")   or inv.get("inv_date") or "").strip()
            total_val = safe_float(inv.get("val") or inv.get("total_val"))

            # Aggregate taxable + tax amounts from items
            taxable = 0.0
            igst = cgst = sgst = 0.0
            items = inv.get("itms") or inv.get("items") or []
            for itm in items:
                det = itm.get("itm_det") or itm  # handle flat or nested
                taxable += safe_float(det.get("txval") or det.get("taxable_val"))
                igst    += safe_float(det.get("igst")  or det.get("iamt"))
                cgst    += safe_float(det.get("cgst")  or det.get("camt"))
                sgst    += safe_float(det.get("sgst")  or det.get("samt"))

            # If items missing, fall back to invoice-level amounts
            if taxable == 0 and total_val > 0:
                taxable = safe_float(
                    inv.get("txval") or inv.get("taxable_val") or total_val
                )

            if not inv_no:
                continue  # skip records without an invoice number

            records.append({
                "gstin":       gstin,
                "inv_no":      inv_no,
                "inv_date":    inv_date,
                "taxable_val": round(taxable, 2),
                "igst":        round(igst,    2),
                "cgst":        round(cgst,    2),
                "sgst":        round(sgst,    2),
                "total_val":   round(total_val or (taxable + igst + cgst + sgst), 2),
                "_norm_key":   f"{gstin}||{normalize_inv(inv_no)}",
            })

    return records


def _dig(d: dict, *keys):
    """Safely dig into nested dicts. Returns None if any key is missing."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# ── Reconciliation Engine ─────────────────────────────────────────────────────

AMOUNT_TOLERANCE = 2.0   # ₹2 rounding tolerance

def reconcile(books_items: list[dict], gstr2b_records: list[dict]) -> dict:
    """
    Match books_items (extracted from PDFs) against gstr2b_records.

    Args:
        books_items:    List of invoice dicts from the PDF extraction
                        (keys: supplier_inv, gst_no, amount, igst, cgst, sgst, total_amount, ...)
        gstr2b_records: List of dicts from parse_gstr2b()

    Returns:
        {
            "rows":    [...],   # each book item annotated with status
            "extra":   [...],   # 2B records not found in books
            "summary": {...},   # aggregate counts + amounts
        }
    """
    # Build lookup: norm_key → 2B record  (keep first if duplicates)
    lookup_2b: dict[str, dict] = {}
    for rec in gstr2b_records:
        k = rec["_norm_key"]
        if k not in lookup_2b:
            lookup_2b[k] = rec

    used_2b_keys: set[str] = set()
    annotated_rows = []

    for item in books_items:
        gstin  = normalize_gstin(item.get("gst_no") or "")
        inv_no = normalize_inv(item.get("supplier_inv") or "")
        norm_key = f"{gstin}||{inv_no}"

        books_total = safe_float(item.get("total_amount"))
        books_taxable = safe_float(item.get("amount"))

        if norm_key in lookup_2b:
            used_2b_keys.add(norm_key)
            rec = lookup_2b[norm_key]
            diff = abs(books_total - rec["total_val"])

            if diff <= AMOUNT_TOLERANCE:
                status = "matched"
            else:
                status = "mismatch"

            row = {**item,
                   "recon_status":    status,
                   "2b_inv_no":       rec["inv_no"],
                   "2b_gstin":        rec["gstin"],
                   "2b_taxable_val":  rec["taxable_val"],
                   "2b_igst":         rec["igst"],
                   "2b_cgst":         rec["cgst"],
                   "2b_sgst":         rec["sgst"],
                   "2b_total_val":    rec["total_val"],
                   "diff_amount":     round(books_total - rec["total_val"], 2),
                   }
        else:
            # In books but not in 2B
            status = "missing_in_2b"
            row = {**item,
                   "recon_status":    status,
                   "2b_inv_no":       None,
                   "2b_gstin":        None,
                   "2b_taxable_val":  None,
                   "2b_igst":         None,
                   "2b_cgst":         None,
                   "2b_sgst":         None,
                   "2b_total_val":    None,
                   "diff_amount":     None,
                   }

        annotated_rows.append(row)

    # 2B records not found in books
    extra_rows = []
    for rec in gstr2b_records:
        if rec["_norm_key"] not in used_2b_keys:
            extra_rows.append({
                "recon_status":   "not_in_books",
                "supplier_inv":   rec["inv_no"],
                "invoice_date":   rec["inv_date"],
                "gst_no":         rec["gstin"],
                "party_ac_name":  None,
                "amount":         rec["taxable_val"],
                "igst":           rec["igst"],
                "cgst":           rec["cgst"],
                "sgst":           rec["sgst"],
                "total_amount":   rec["total_val"],
                "2b_inv_no":      rec["inv_no"],
                "2b_gstin":       rec["gstin"],
                "2b_taxable_val": rec["taxable_val"],
                "2b_igst":        rec["igst"],
                "2b_cgst":        rec["cgst"],
                "2b_sgst":        rec["sgst"],
                "2b_total_val":   rec["total_val"],
                "diff_amount":    None,
            })

    # Summary
    all_rows = annotated_rows + extra_rows
    summary = _build_summary(all_rows)

    return {
        "rows":    annotated_rows,
        "extra":   extra_rows,
        "summary": summary,
    }


def _build_summary(all_rows: list[dict]) -> dict:
    counts  = {"matched": 0, "mismatch": 0, "missing_in_2b": 0, "not_in_books": 0}
    amounts = {"matched": 0.0, "mismatch": 0.0, "missing_in_2b": 0.0, "not_in_books": 0.0}

    for r in all_rows:
        s = r.get("recon_status", "")
        if s in counts:
            counts[s] += 1
            amounts[s] += safe_float(r.get("total_amount") or r.get("2b_total_val"))

    itc_at_risk = round(
        amounts["missing_in_2b"]
        + amounts.get("mismatch", 0.0),
        2,
    )

    return {
        "counts":        counts,
        "amounts":       {k: round(v, 2) for k, v in amounts.items()},
        "itc_at_risk":   itc_at_risk,
        "matched_itc":   round(amounts["matched"], 2),
        "total_rows":    len(all_rows),
    }
