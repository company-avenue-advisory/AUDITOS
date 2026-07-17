"""
output_schema.py — Canonical field dictionary + Excel output views.

Single source of truth for every Excel/tabular output the system produces.

Design
------
The DB models (`SalesLineItem` / `PurchaseLineItem`) are the CANONICAL schema.
Every Excel output is a *named view* — an ordered projection of canonical fields
with an explicit display label. Nothing hardcodes its own column list or value
order anymore; a view defines both, so header and row can never drift apart.

Format-preserving
-----------------
Each view declares the EXACT label it currently emits, so adopting this module
changes nothing visible in produced files. The standardized ("canonical") label
lives on the field for the day we *choose* to standardize — see `Field.canonical_label`.
Until then, views keep the current labels (e.g. "Party Name", "CGST", "GSTR1 Category").

Views
-----
- SALES_REGISTER_VIEW / PURCHASE_REGISTER_VIEW  -> the Tally-ready registers
  (wired to prod via services/excel_sync.py)
- AUDIT_VIEW                                     -> the auditor QA workbook
  (label-canonical mirror of tools/batch_excel_export.py; that tool still
  computes its own derived values for now)
- The GSTR-2B reconciliation view is defined alongside that feature (Section 13);
  it reuses the purchase canonical fields plus recon-only columns.
"""

from dataclasses import dataclass
from typing import Any, Callable, List, Optional


# ---------------------------------------------------------------------------
# Canonical field registry — keys match DB columns where applicable.
# `canonical_label` is the STANDARDIZED label (the target once we standardize);
# views may override it with the current label to stay format-preserving.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    key: str                       # canonical key (DB column name where applicable)
    canonical_label: str           # standardized display label (future target)
    kind: str = "text"             # text | number | percent | meta | derived


CANONICAL: dict[str, Field] = {
    # --- core line-item fields (present on the DB models) ---
    "voucher_date":        Field("voucher_date", "Voucher Date"),
    "voucher_type":        Field("voucher_type", "Voucher Type"),
    "invoice_no":          Field("invoice_no", "Invoice No"),
    "party_ledger_name":   Field("party_ledger_name", "Party Ledger Name"),
    "party_gstin":         Field("party_gstin", "Party GSTIN"),
    "place_of_supply":     Field("place_of_supply", "Place of Supply"),
    "particulars":         Field("particulars", "Particulars"),
    "hsn":                 Field("hsn", "HSN/SAC"),
    "qty":                 Field("qty", "Qty", "number"),
    "rate":                Field("rate", "Rate", "number"),
    "taxable_value":       Field("taxable_value", "Taxable Value", "number"),
    "discount":            Field("discount", "Discount", "number"),
    "advances":            Field("advances", "Advances", "number"),
    "cgst_amount":         Field("cgst_amount", "CGST Amount", "number"),
    "sgst_amount":         Field("sgst_amount", "SGST Amount", "number"),
    "igst_amount":         Field("igst_amount", "IGST Amount", "number"),
    "total_invoice_value": Field("total_invoice_value", "Total Invoice Value", "number"),
    "gstr1_category":      Field("gstr1_category", "GSTR-1 Category"),
    "itc_eligibility":     Field("itc_eligibility", "ITC Eligibility"),
    "narration":           Field("narration", "Narration"),
    # --- completeness: computed by the audit/recon layers, not yet on the DB models ---
    "round_off":           Field("round_off", "Round Off", "number"),
    "cess_amount":         Field("cess_amount", "Cess Amount", "number"),
    # --- derived (computed at export time) ---
    "cgst_rate":           Field("cgst_rate", "CGST Rate (%)", "percent"),
    "sgst_rate":           Field("sgst_rate", "SGST Rate (%)", "percent"),
    "igst_rate":           Field("igst_rate", "IGST Rate (%)", "percent"),
    "total_tax":           Field("total_tax", "Total Tax", "number"),
    "advance_deducted":    Field("advance_deducted", "Advance Deducted", "number"),
    "tax_type":            Field("tax_type", "Tax Type"),
    "nature":              Field("nature", "Nature"),
    "status":              Field("status", "Status"),
    "note":                Field("note", "Note"),
    # --- meta / provenance ---
    "s_no":                Field("s_no", "S.No", "meta"),
    "file_name":           Field("file_name", "File Name", "meta"),
    "source_file":         Field("source_file", "Source File", "meta"),
    "processed_date":      Field("processed_date", "Processed Date", "meta"),
    "invoice_date":        Field("invoice_date", "Invoice Date", "meta"),
    # --- GSTR-2B reconciliation (Section 13 / services/gstr2b_reconciler.py) ---
    "recon_status":        Field("recon_status", "Recon Status"),
    "fuzzy_matched":       Field("fuzzy_matched", "Fuzzy Matched", "meta"),
    "diff_amount":         Field("diff_amount", "Diff Amount (Books - 2B)", "number"),
    "2b_inv_no":           Field("2b_inv_no", "2B Invoice No", "meta"),
    "2b_gstin":            Field("2b_gstin", "2B GSTIN", "meta"),
    "2b_taxable_val":      Field("2b_taxable_val", "2B Taxable Value", "number"),
    "2b_cgst":             Field("2b_cgst", "2B CGST", "number"),
    "2b_sgst":             Field("2b_sgst", "2B SGST", "number"),
    "2b_igst":             Field("2b_igst", "2B IGST", "number"),
    "2b_total_val":        Field("2b_total_val", "2B Total Value", "number"),
    # --- Section 13.1: post-reconciliation gap-investigation columns ---
    # These are NOT produced by gstr2b_reconciler.py itself — they're filled in
    # by the targeted Drive-verify step (Bucket A: not_in_books) that runs on
    # the unmatched gap set after reconciliation. Blank until that step runs.
    "in_drive":            Field("in_drive", "In Drive?", "meta"),
    "tally_entry_status":  Field("tally_entry_status", "Entry Missing in Tally", "meta"),
    "client_action":       Field("client_action", "Client Action / Status", "meta"),
}


# ---------------------------------------------------------------------------
# A view is an ordered list of columns. Each column names a canonical field and
# the EXACT label to emit (defaults to the canonical label). Values come from the
# ORM item's attribute (`attr`, defaults to `key`) unless `ctx_key` is set, in
# which case the value is taken from the per-row context dict (source file,
# processed timestamp, running S.No, etc.).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Column:
    key: str                        # canonical field key (must exist in CANONICAL)
    label: Optional[str] = None     # exact label to emit; None -> canonical label
    attr: Optional[str] = None      # ORM attribute name; None -> key
    ctx_key: Optional[str] = None   # if set, value comes from ctx[ctx_key], not the item
    candidates: Optional[List[str]] = None
    # ^ ordered fallback keys/attrs to try (first present wins). Needed for
    # reconciliation rows, which carry different field names depending on
    # which bucket they came from (books-sourced rows carry canonical AuditOS
    # keys like `invoice_no`/`taxable_value`; 2B-only `not_in_books` rows
    # carry only the reconciler's legacy names like `supplier_inv`/`amount`).

    def display_label(self) -> str:
        return self.label if self.label is not None else CANONICAL[self.key].canonical_label


def labels(view: List[Column]) -> List[str]:
    """Header row for a view — the exact labels, in order."""
    return [c.display_label() for c in view]


def _get(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def value_for(col: Column, item: Any, ctx: Optional[dict] = None) -> Any:
    """One cell value. Preserves the legacy `<value> or ""` blanking exactly.

    Works over both ORM objects (attribute access) and dicts (reconciliation
    rows). When `candidates` is set, tries each key in order and uses the
    first one that's present at all (not just truthy) — so a real `0.0`
    still blanks to "" like every other numeric field, but a genuinely
    absent key falls through to the next candidate instead of blanking early.
    """
    ctx = ctx or {}
    if col.ctx_key is not None:
        return ctx.get(col.ctx_key, "")
    for key in (col.candidates or [col.attr or col.key]):
        val = _get(item, key)
        if val is not None:
            return val or ""
    return ""


def row_for(view: List[Column], item: Any, ctx: Optional[dict] = None) -> List[Any]:
    """Full row for a view, in column order."""
    return [value_for(c, item, ctx) for c in view]


# ---------------------------------------------------------------------------
# VIEWS — labels below are the CURRENT (format-preserving) labels. Where they
# differ from the canonical label, it's noted; standardization is deferred.
# ---------------------------------------------------------------------------

# Sales Register (prod: services/excel_sync.py, SALES_COLUMNS) — 21 columns.
SALES_REGISTER_VIEW: List[Column] = [
    Column("voucher_date",        "Voucher Date"),
    Column("voucher_type",        "Voucher Type"),
    Column("invoice_no",          "Invoice No"),
    Column("party_ledger_name",   "Party Name"),        # canonical: "Party Ledger Name"
    Column("party_gstin",         "Party GSTIN"),
    Column("place_of_supply",     "Place of Supply"),
    Column("particulars",         "Particulars"),
    Column("hsn",                 "HSN"),               # canonical: "HSN/SAC"
    Column("qty",                 "Qty"),
    Column("rate",                "Rate"),
    Column("taxable_value",       "Taxable Value"),
    Column("discount",            "Discount"),
    Column("advances",            "Advances"),
    Column("cgst_amount",         "CGST"),              # canonical: "CGST Amount"
    Column("sgst_amount",         "SGST"),              # canonical: "SGST Amount"
    Column("igst_amount",         "IGST"),              # canonical: "IGST Amount"
    Column("total_invoice_value", "Total Invoice Value"),
    Column("gstr1_category",      "GSTR1 Category"),    # canonical: "GSTR-1 Category"
    Column("narration",           "Narration"),
    Column("processed_date",      "Processed Date", ctx_key="processed_date"),
    Column("source_file",         "Source File",    ctx_key="source_file"),
]

# Purchase Register (prod: services/excel_sync.py, PURCHASE_COLUMNS) — 19 columns.
PURCHASE_REGISTER_VIEW: List[Column] = [
    Column("voucher_date",        "Voucher Date"),
    Column("voucher_type",        "Voucher Type"),
    Column("invoice_no",          "Invoice No"),
    Column("party_ledger_name",   "Party Name"),        # canonical: "Party Ledger Name"
    Column("party_gstin",         "Party GSTIN"),
    Column("place_of_supply",     "Place of Supply"),
    Column("particulars",         "Particulars"),
    Column("hsn",                 "HSN"),               # canonical: "HSN/SAC"
    Column("qty",                 "Qty"),
    Column("rate",                "Rate"),
    Column("taxable_value",       "Taxable Value"),
    Column("cgst_amount",         "CGST"),              # canonical: "CGST Amount"
    Column("sgst_amount",         "SGST"),              # canonical: "SGST Amount"
    Column("igst_amount",         "IGST"),              # canonical: "IGST Amount"
    Column("total_invoice_value", "Total Invoice Value"),
    Column("itc_eligibility",     "ITC Eligibility"),
    Column("narration",           "Narration"),
    Column("processed_date",      "Processed Date", ctx_key="processed_date"),
    Column("source_file",         "Source File",    ctx_key="source_file"),
]

# Auditor QA workbook (tools/batch_excel_export.py, COLUMNS) — 25 columns.
# Label-canonical mirror only: that standalone tool still computes its own values
# (incl. derived rate %, status, notes). Kept here so the labels have one home.
AUDIT_VIEW: List[Column] = [
    Column("s_no",                "S.No"),
    Column("file_name",           "File Name"),
    Column("invoice_no",          "Invoice No"),
    Column("invoice_date",        "Invoice Date"),
    Column("party_ledger_name",   "Party Name"),        # canonical: "Party Ledger Name"
    Column("party_gstin",         "Party GSTIN"),
    Column("place_of_supply",     "Place of Supply"),
    Column("particulars",         "Particulars"),
    Column("hsn",                 "HSN/SAC"),
    Column("taxable_value",       "Taxable Value"),
    Column("cgst_rate",           "CGST Rate (%)"),
    Column("cgst_amount",         "CGST Amount"),
    Column("sgst_rate",           "SGST Rate (%)"),
    Column("sgst_amount",         "SGST Amount"),
    Column("igst_rate",           "IGST Rate (%)"),
    Column("igst_amount",         "IGST Amount"),
    Column("total_tax",           "Total Tax"),
    Column("round_off",           "Round Off"),
    Column("advance_deducted",    "Advance Deducted"),
    Column("total_invoice_value", "Total Invoice Value"),
    Column("gstr1_category",      "GSTR-1 Category"),
    Column("tax_type",            "Tax Type"),
    Column("nature",              "Nature"),
    Column("status",              "Status"),
    Column("note",                "Note"),
]

# GSTR-2B Reconciliation (Section 13) — one row per line from
# gstr2b_reconciler.reconcile()'s `rows` (books-sourced: matched / mismatch /
# missing_in_2b) and `extra` (2B-only: not_in_books). Uses `candidates` since
# the two sources name the same field differently (see Column.candidates doc).
GSTR2B_RECONCILIATION_VIEW: List[Column] = [
    Column("invoice_no",          "Invoice No",       candidates=["invoice_no", "supplier_inv", "2b_inv_no"]),
    Column("invoice_date",        "Invoice Date",     candidates=["voucher_date", "invoice_date"]),
    Column("party_ledger_name",   "Party Ledger Name",candidates=["party_ledger_name", "party_ac_name"]),
    Column("party_gstin",         "Party GSTIN",      candidates=["party_gstin", "gst_no", "2b_gstin"]),
    Column("particulars",         "Particulars",      candidates=["particulars"]),
    Column("taxable_value",       "Taxable Value (Books)", candidates=["taxable_value", "amount"]),
    Column("cgst_amount",         "CGST (Books)",     candidates=["cgst_amount", "cgst"]),
    Column("sgst_amount",         "SGST (Books)",     candidates=["sgst_amount", "sgst"]),
    Column("igst_amount",         "IGST (Books)",     candidates=["igst_amount", "igst"]),
    Column("total_invoice_value", "Total Value (Books)", candidates=["total_invoice_value", "total_amount"]),
    Column("2b_taxable_val",      "2B Taxable Value"),
    Column("2b_cgst",             "2B CGST"),
    Column("2b_sgst",             "2B SGST"),
    Column("2b_igst",             "2B IGST"),
    Column("2b_total_val",        "2B Total Value"),
    Column("diff_amount",         "Diff Amount (Books - 2B)"),
    Column("recon_status",        "Recon Status"),
    Column("fuzzy_matched",       "Fuzzy Matched"),
    Column("in_drive",            "In Drive?"),
    Column("tally_entry_status",  "Entry Missing in Tally"),
    Column("client_action",       "Client Action / Status"),
    Column("itc_eligibility",     "ITC Eligibility",  candidates=["itc_eligibility"]),
]
