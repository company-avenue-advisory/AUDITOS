/**
 * gstValidator.ts — Deterministic Client-Side GST Compliance Engine
 * ==================================================================
 * Pure TypeScript validation with zero backend dependency.
 * Runs entirely in the browser for instant feedback.
 *
 * Checks:
 *   1. Invoice Number — present, max 16 chars, valid characters
 *   2. Invoice Date — present
 *   3. GSTIN — 15-char statutory format with regex validation
 *   4. IRN — 64-char hex if present
 *   5. Math Balance — (Taxable + CGST + SGST + IGST) == Total, ₹1 tolerance
 *   6. Tax type exclusivity — cannot have both IGST and (CGST+SGST) simultaneously
 *   7. Place of Supply — present
 */

export interface ValidatedItem {
  supplier_inv: string;
  invoice_date: string;
  gst_no: string;
  irn?: string;
  party_ac_name: string;
  place_of_supply: string;
  particulars: string;
  amount: number;
  sgst: number;
  cgst: number;
  igst: number;
  total_amount: number;
  hsn: string;
  narration: string;
  errors?: string[];
}

/** Severity levels for validation results */
export type ValidationSeverity = "error" | "warning";

export interface ValidationIssue {
  field: string;
  message: string;
  severity: ValidationSeverity;
}

/* ── Regex patterns ───────────────────────────────────────────────────────── */

/** Statutory GSTIN: 2-digit state + 5 alpha PAN + 4 digit + 1 alpha + entity + Z + check */
const GSTIN_PATTERN =
  /^(0[1-9]|[12]\d|3[0-8])[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/i;

/** IRN: exactly 64 hex characters */
const IRN_PATTERN = /^[a-fA-F0-9]{64}$/;

/** Invoice number: alphanumeric with -, /, max 16 chars after stripping spaces */
const INV_NO_PATTERN = /^[a-zA-Z0-9\-/]{1,16}$/;

/* ── Tolerance ────────────────────────────────────────────────────────────── */

/** ₹1 rounding tolerance for math balance check */
const MATH_TOLERANCE = 1.0;

/* ── Core validator ───────────────────────────────────────────────────────── */

/**
 * Run all validation checks on a single line item.
 * Returns an array of human-readable error strings.
 */
export function validateGstItem(item: ValidatedItem): string[] {
  const issues = validateGstItemDetailed(item);
  return issues
    .filter((i) => i.severity === "error")
    .map((i) => i.message);
}

/**
 * Detailed validation returning structured issues with field + severity.
 */
export function validateGstItemDetailed(item: ValidatedItem): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // ── 1. Invoice Number ──────────────────────────────────────────────────
  if (!item.supplier_inv || !item.supplier_inv.trim()) {
    issues.push({
      field: "supplier_inv",
      message: "Missing invoice number",
      severity: "error",
    });
  } else {
    const cleaned = item.supplier_inv.replace(/\s/g, "");
    if (!INV_NO_PATTERN.test(cleaned)) {
      issues.push({
        field: "supplier_inv",
        message:
          "Invoice No must be max 16 chars (alphanumeric, -, / only, no spaces)",
        severity: "error",
      });
    }
  }

  // ── 2. Invoice Date ────────────────────────────────────────────────────
  if (!item.invoice_date || !item.invoice_date.trim()) {
    issues.push({
      field: "invoice_date",
      message: "Missing invoice date",
      severity: "error",
    });
  }

  // ── 3. GSTIN ───────────────────────────────────────────────────────────
  if (!item.gst_no || !item.gst_no.trim()) {
    issues.push({
      field: "gst_no",
      message: "Missing supplier GSTIN",
      severity: "error",
    });
  } else {
    const trimmed = item.gst_no.trim();
    if (trimmed.length !== 15) {
      issues.push({
        field: "gst_no",
        message: `GSTIN must be exactly 15 characters (got ${trimmed.length})`,
        severity: "error",
      });
    } else if (!GSTIN_PATTERN.test(trimmed)) {
      issues.push({
        field: "gst_no",
        message: "GSTIN format invalid (expected 15 statutory characters)",
        severity: "error",
      });
    }
  }

  // ── 4. IRN ─────────────────────────────────────────────────────────────
  if (item.irn && item.irn.trim()) {
    if (!IRN_PATTERN.test(item.irn.trim())) {
      issues.push({
        field: "irn",
        message: "IRN format invalid (expected 64-character hex)",
        severity: "error",
      });
    }
  }

  // ── 5. Mathematical Balance Check ──────────────────────────────────────
  const amount = item.amount || 0;
  const sgst = item.sgst || 0;
  const cgst = item.cgst || 0;
  const igst = item.igst || 0;
  const total = item.total_amount || 0;

  const expectedTotal = amount + sgst + cgst + igst;
  const diff = Math.abs(expectedTotal - total);

  if (diff > MATH_TOLERANCE) {
    issues.push({
      field: "total_amount",
      message: `Math mismatch: ${expectedTotal.toFixed(2)} ≠ ${total.toFixed(2)} (₹${diff.toFixed(2)} variance, tolerance ₹${MATH_TOLERANCE})`,
      severity: "error",
    });
  }

  // ── 6. Tax type exclusivity warning ────────────────────────────────────
  if (igst > 0 && (sgst > 0 || cgst > 0)) {
    issues.push({
      field: "igst",
      message: "IGST and CGST/SGST are both present — typically mutually exclusive",
      severity: "warning",
    });
  }

  // ── 7. Place of Supply ─────────────────────────────────────────────────
  if (!item.place_of_supply || !item.place_of_supply.trim()) {
    issues.push({
      field: "place_of_supply",
      message: "Missing place of supply",
      severity: "warning",
    });
  }

  return issues;
}

/**
 * Quick check — does the item have any hard errors?
 */
export function hasErrors(item: ValidatedItem): boolean {
  return validateGstItem(item).length > 0;
}
