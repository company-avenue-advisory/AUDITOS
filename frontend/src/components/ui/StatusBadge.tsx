"use client";

import React from "react";

/**
 * One shared status-pill component for every review-gate / reconciliation
 * status across the app (Sales period review, Purchase GSTR-2B review,
 * GSTR-2B line-item recon) - previously each page redefined its own
 * color/label mapping inline (see reconciliation/page.tsx), which is how
 * the accent-color drift between pages happened in the first place.
 */

const STATUS_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  PASS:                 { color: "var(--green)", bg: "var(--green-soft)", label: "Pass" },
  matched:              { color: "var(--green)", bg: "var(--green-soft)", label: "Matched" },
  APPROVED:             { color: "var(--green)", bg: "var(--green-soft)", label: "Approved" },

  CLIENT_SHEET_ERROR:   { color: "var(--red)", bg: "var(--red-soft)", label: "Client sheet error" },
  mismatch:             { color: "var(--amber)", bg: "var(--amber-soft)", label: "Mismatch" },
  UNRESOLVED_CONFLICT:  { color: "var(--amber)", bg: "var(--amber-soft)", label: "Unresolved" },
  PENDING_REVIEW:       { color: "var(--amber)", bg: "var(--amber-soft)", label: "Pending review" },

  MISSING_SOURCE_PDF:   { color: "var(--accent)", bg: "var(--accent-soft)", label: "Missing source" },
  CLIENT_MISSING:       { color: "var(--blue)", bg: "var(--blue-soft)", label: "Client missing" },
  missing_in_2b:        { color: "var(--red)", bg: "var(--red-soft)", label: "Missing in 2B" },
  not_in_books:         { color: "var(--blue)", bg: "var(--blue-soft)", label: "Not in books" },
  UNVERIFIABLE_NO_GSTIN:{ color: "var(--red)", bg: "var(--red-soft)", label: "No GSTIN" },

  REJECTED:             { color: "var(--red)", bg: "var(--red-soft)", label: "Rejected" },

  // GSTIN registry / B2B-B2C resolution (see RuleGST005, gstin-check page)
  active:               { color: "var(--green)", bg: "var(--green-soft)", label: "Active" },
  Active:               { color: "var(--green)", bg: "var(--green-soft)", label: "Active" },
  inactive:             { color: "var(--red)", bg: "var(--red-soft)", label: "B2C" },
  Cancelled:            { color: "var(--red)", bg: "var(--red-soft)", label: "Cancelled" },
  Suspended:            { color: "var(--amber)", bg: "var(--amber-soft)", label: "Suspended" },
  needs_review:         { color: "var(--amber)", bg: "var(--amber-soft)", label: "Needs review" },
  unknown:              { color: "var(--text-secondary)", bg: "var(--bg-card)", label: "Unknown" },

  // Drive Sync job / Celery task statuses
  completed:            { color: "var(--green)", bg: "var(--green-soft)", label: "Completed" },
  SUCCESS:              { color: "var(--green)", bg: "var(--green-soft)", label: "Done" },
  failed:               { color: "var(--red)", bg: "var(--red-soft)", label: "Failed" },
  FAILURE:              { color: "var(--red)", bg: "var(--red-soft)", label: "Error" },
  in_progress:          { color: "var(--accent)", bg: "var(--accent-soft)", label: "In progress" },
  STARTED:              { color: "var(--accent)", bg: "var(--accent-soft)", label: "Running" },
  PENDING:              { color: "var(--amber)", bg: "var(--amber-soft)", label: "Queued" },
  SKIPPED:              { color: "var(--text-secondary)", bg: "var(--bg-card)", label: "Skipped" },
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || { color: "var(--text-secondary)", bg: "var(--bg-card)", label: status };
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 11,
        fontWeight: 600,
        color: style.color,
        background: style.bg,
        padding: "3px 10px",
        borderRadius: "var(--radius-sm)",
        whiteSpace: "nowrap",
      }}
    >
      {style.label}
    </span>
  );
}
