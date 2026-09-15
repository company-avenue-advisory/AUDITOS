"""
gstr2b_reconciler.py — GSTR-2B Reconciliation Engine
=====================================================
Stateless, deterministic matching engine.

Parses the GSTR-2B JSON downloaded from the GST portal and matches it
against invoice line items extracted from PDFs.

Match key: normalize(GSTIN) + normalize(Invoice Number)

Enhanced features (v2):
  - Strips ALL punctuation and whitespace before key comparison
  - Aggregates multi-item invoice lines by (inum, ctin) before matching
  - ₹2 rounding tolerance for amount comparison

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

def _strip_all(s: str) -> str:
    """Remove ALL non-alphanumeric characters (spaces, punctuation, dashes, slashes)."""
    return re.sub(r"[^A-Z0-9]", "", str(s).strip().upper())


def normalize_inv(s: str) -> str:
    """Normalize invoice number: uppercase, strip ALL non-alphanumeric chars."""
    if not s:
        return ""
    return _strip_all(s)


def normalize_gstin(s: str) -> str:
    """Normalize GSTIN: uppercase, strip spaces and punctuation."""
    if not s:
        return ""
    return _strip_all(s)


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


# ── Field normalisation (handles both old manual JSON and AuditOS extraction) ─

def _normalise_item(item: dict) -> dict:
    """
    Map AuditOS PurchaseLineItem field names → legacy reconciler field names.
    Idempotent: if legacy keys already present they are kept.

    AuditOS extraction:  invoice_no, party_gstin, taxable_value, cgst_amount,
                         sgst_amount, igst_amount, total_invoice_value,
                         party_ledger_name, voucher_date, particulars,
                         itc_eligibility
    Legacy reconciler:   supplier_inv, gst_no, amount, cgst, sgst, igst,
                         total_amount, party_ac_name, invoice_date, particulars
    """
    out = dict(item)
    if "supplier_inv" not in out:
        out["supplier_inv"] = item.get("invoice_no") or item.get("supplier_inv") or ""
    if "gst_no" not in out:
        out["gst_no"] = item.get("party_gstin") or item.get("gst_no") or ""
    if "amount" not in out:
        out["amount"] = safe_float(item.get("taxable_value") or item.get("amount"))
    if "cgst" not in out:
        out["cgst"] = safe_float(item.get("cgst_amount") or item.get("cgst"))
    if "sgst" not in out:
        out["sgst"] = safe_float(item.get("sgst_amount") or item.get("sgst"))
    if "igst" not in out:
        out["igst"] = safe_float(item.get("igst_amount") or item.get("igst"))
    if "total_amount" not in out:
        out["total_amount"] = safe_float(
            item.get("total_invoice_value") or item.get("total_amount")
            or (out["amount"] + out["cgst"] + out["sgst"] + out["igst"])
        )
    if "party_ac_name" not in out:
        out["party_ac_name"] = item.get("party_ledger_name") or item.get("party_ac_name") or ""
    if "invoice_date" not in out:
        out["invoice_date"] = item.get("voucher_date") or item.get("invoice_date") or ""
    # Preserve ITC eligibility if present (from AuditOS purchase pipeline)
    out.setdefault("itc_eligibility", item.get("itc_eligibility") or "ITC_UNKNOWN")
    return out


# ── Aggregation Layer (v2) ────────────────────────────────────────────────────

def _aggregate_books_by_invoice(books_items: list[dict]) -> list[dict]:
    """
    Aggregate multi-line-item invoices into single invoice-level rows
    grouped by (normalized GSTIN, normalized Invoice Number).

    If a single invoice has 3 line items (e.g. Rentals, Electricity, Maintenance),
    this sums their taxable + tax amounts into one row for matching against the
    single 2B invoice-level record.

    The first occurrence's metadata (party name, date, particulars) is preserved.
    """
    groups: dict[str, dict] = {}

    for item in books_items:
        gstin   = normalize_gstin(item.get("gst_no") or "")
        inv_no  = normalize_inv(item.get("supplier_inv") or "")
        norm_key = f"{gstin}||{inv_no}"

        if norm_key not in groups:
            # First occurrence — clone metadata
            groups[norm_key] = {
                **item,
                "_agg_amount":       safe_float(item.get("amount")),
                "_agg_sgst":         safe_float(item.get("sgst")),
                "_agg_cgst":         safe_float(item.get("cgst")),
                "_agg_igst":         safe_float(item.get("igst")),
                "_agg_total_amount": safe_float(item.get("total_amount")),
                "_agg_count":        1,
                "_norm_key":         norm_key,
                "_original_items":   [item],
            }
        else:
            grp = groups[norm_key]
            grp["_agg_amount"]       += safe_float(item.get("amount"))
            grp["_agg_sgst"]         += safe_float(item.get("sgst"))
            grp["_agg_cgst"]         += safe_float(item.get("cgst"))
            grp["_agg_igst"]         += safe_float(item.get("igst"))
            grp["_agg_total_amount"] += safe_float(item.get("total_amount"))
            grp["_agg_count"]        += 1
            grp["_original_items"].append(item)

    return list(groups.values())


# ── Reconciliation Engine ─────────────────────────────────────────────────────

AMOUNT_TOLERANCE = 2.0   # ₹2 rounding tolerance
_FUZZY_MIN_OVERLAP = 4   # minimum normalized-invoice-number length to fuzzy-match on


def _fuzzy_invoice_match(norm_a: str, norm_b: str) -> bool:
    """
    True if two ALREADY-normalized (uppercase, non-alnum stripped)
    invoice numbers are different strings but plausibly the same
    document. Handles two real, common mismatches an exact-key match
    misses entirely:
      - truncation (one is a prefix/suffix of the other, e.g. a books
        entry "SI2024001" vs a 2B entry truncated to "2024001")
      - leading-zero differences (e.g. "0001" vs "1")

    Requires a minimum overlap length (_FUZZY_MIN_OVERLAP) for the
    substring case so short numbers can't false-positive against an
    unrelated invoice from the same vendor - fuzzy matching without a
    floor is exactly the failure mode competitor tooling flags too.
    Only ever called within an already-matching GSTIN + within-tolerance
    amount check (see reconcile()'s fuzzy pass) - invoice-number
    plausibility alone is never sufficient on its own.
    """
    if not norm_a or not norm_b or norm_a == norm_b:
        return False
    if len(norm_a) >= _FUZZY_MIN_OVERLAP and len(norm_b) >= _FUZZY_MIN_OVERLAP:
        if norm_a in norm_b or norm_b in norm_a:
            return True
    stripped_a, stripped_b = norm_a.lstrip("0"), norm_b.lstrip("0")
    if stripped_a and stripped_a == stripped_b:
        return True
    return False


def _matched_rows(agg: dict, rec: dict, agg_total: float, fuzzy: bool) -> list[dict]:
    """Builds the annotated row(s) for one aggregated books invoice that
    matched (exactly or fuzzily) against one 2B record."""
    diff = abs(agg_total - rec["total_val"])
    status = "matched" if diff <= AMOUNT_TOLERANCE else "mismatch"
    return [{
        **item,
        "recon_status":    status,
        "fuzzy_matched":   fuzzy,
        "2b_inv_no":       rec["inv_no"],
        "2b_gstin":        rec["gstin"],
        "2b_taxable_val":  rec["taxable_val"],
        "2b_igst":         rec["igst"],
        "2b_cgst":         rec["cgst"],
        "2b_sgst":         rec["sgst"],
        "2b_total_val":    rec["total_val"],
        "diff_amount":     round(agg_total - rec["total_val"], 2),
        "_agg_books_total": agg_total,
    } for item in agg["_original_items"]]


def reconcile(books_items: list[dict], gstr2b_records: list[dict]) -> dict:
    """
    Match books_items (extracted from PDFs) against gstr2b_records.

    Enhanced v2 flow, now with a v3 fuzzy fallback pass:
      1. Aggregate books items by (GSTIN, Invoice No) — multi-line items become one row.
      2. Build a lookup from 2B records by the same normalized key.
      3. Match aggregated books row against 2B invoice (exact key match).
      3b. Fuzzy fallback: for books rows that didn't exact-match, try the
          same GSTIN + a fuzzy invoice-number match (_fuzzy_invoice_match)
          + amount within tolerance, against 2B records the exact pass
          didn't already use. Recovers invoice-number truncation/leading-
          zero mismatches that would otherwise show up as both
          missing_in_2b AND not_in_books for what's really the same
          invoice.
      4. Return annotated rows (per-original-item, not aggregated) + extra 2B rows.

    Args:
        books_items:    List of invoice dicts from the PDF extraction
                        (keys: supplier_inv, gst_no, amount, igst, cgst, sgst, total_amount, ...)
        gstr2b_records: List of dicts from parse_gstr2b()

    Returns:
        {
            "rows":    [...],   # each book item annotated with status
            "extra":   [...],   # 2B records not found in books
            "summary": {...},   # aggregate counts + amounts + fuzzy_matched_count
        }
    """
    # Step 0: Normalise field names (handles AuditOS extraction output)
    books_items = [_normalise_item(i) for i in books_items]

    # Step 1: Aggregate books items by invoice
    aggregated = _aggregate_books_by_invoice(books_items)

    # Step 2: Build lookup from 2B: norm_key → 2B record (keep first if duplicates)
    lookup_2b: dict[str, dict] = {}
    for rec in gstr2b_records:
        k = rec["_norm_key"]
        if k not in lookup_2b:
            lookup_2b[k] = rec

    used_2b_keys: set[str] = set()
    annotated_rows: list[dict] = []
    unmatched_agg: list[dict] = []

    # Step 3: exact-key match
    for agg in aggregated:
        norm_key = agg["_norm_key"]
        if norm_key in lookup_2b:
            used_2b_keys.add(norm_key)
            rec = lookup_2b[norm_key]
            annotated_rows.extend(_matched_rows(agg, rec, round(agg["_agg_total_amount"], 2), fuzzy=False))
        else:
            unmatched_agg.append(agg)

    # Step 3b: fuzzy fallback for what the exact pass left unmatched
    remaining_2b = [rec for rec in gstr2b_records if rec["_norm_key"] not in used_2b_keys]
    still_unmatched: list[dict] = []
    for agg in unmatched_agg:
        gstin = agg["_norm_key"].split("||")[0]
        agg_inv_norm = normalize_inv(agg.get("supplier_inv") or "")
        agg_total = round(agg["_agg_total_amount"], 2)

        candidate = next((
            rec for rec in remaining_2b
            if rec["gstin"] == gstin
            and _fuzzy_invoice_match(agg_inv_norm, normalize_inv(rec["inv_no"]))
            and abs(agg_total - rec["total_val"]) <= AMOUNT_TOLERANCE
        ), None)

        if candidate:
            remaining_2b.remove(candidate)
            used_2b_keys.add(candidate["_norm_key"])
            annotated_rows.extend(_matched_rows(agg, candidate, agg_total, fuzzy=True))
        else:
            still_unmatched.append(agg)

    # Step 3c: anything still unmatched after both passes → missing_in_2b
    for agg in still_unmatched:
        for item in agg["_original_items"]:
            annotated_rows.append({
                **item,
                "recon_status":    "missing_in_2b",
                "fuzzy_matched":   False,
                "2b_inv_no":       None,
                "2b_gstin":        None,
                "2b_taxable_val":  None,
                "2b_igst":         None,
                "2b_cgst":         None,
                "2b_sgst":         None,
                "2b_total_val":    None,
                "diff_amount":     None,
            })

    # Step 4: 2B records not found in books (after both matching passes)
    extra_rows = []
    for rec in remaining_2b:
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
    summary["fuzzy_matched_count"] = sum(1 for r in annotated_rows if r.get("fuzzy_matched"))

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

    itc_at_risk = round(amounts["missing_in_2b"] + amounts.get("mismatch", 0.0), 2)

    # Rule 36(4): provisional ITC cap = 105% of matched GSTR-2B ITC
    # Only matched invoices form the base; excess books ITC is capped.
    matched_itc_base = round(amounts["matched"], 2)
    rule_36_4_cap    = round(matched_itc_base * 1.05, 2)
    total_books_itc  = round(
        amounts["matched"] + amounts["mismatch"] + amounts["missing_in_2b"], 2
    )
    rule_36_4_excess = round(max(0.0, total_books_itc - rule_36_4_cap), 2)

    return {
        "counts":           counts,
        "amounts":          {k: round(v, 2) for k, v in amounts.items()},
        "itc_at_risk":      itc_at_risk,
        "matched_itc":      matched_itc_base,
        "total_rows":       len(all_rows),
        "rule_36_4": {
            "cap":          rule_36_4_cap,
            "total_claimed":total_books_itc,
            "excess":       rule_36_4_excess,
            "breached":     rule_36_4_excess > 0,
        },
    }
