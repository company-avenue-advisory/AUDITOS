"use client";

import React from "react";

interface MetricCardProps {
  label: string;
  value: string | number;
  color?: string;
}

/** One shared metric-card component - label + big number - for summary
 * rows across the review-gate pages, instead of each page hand-rolling
 * its own version of the same card. */
export default function MetricCard({ label, value, color }: MetricCardProps) {
  return (
    <div
      className="glass"
      style={{
        borderRadius: "var(--radius-md)",
        padding: "16px",
      }}
    >
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || "var(--text-primary)" }}>{value}</div>
    </div>
  );
}
