"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { ClipboardCheck, GitCompareArrows, FileSpreadsheet } from "lucide-react";
import StatusBadge from "../ui/StatusBadge";
import MetricCard from "../ui/MetricCard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHdr(): Record<string, string> {
  const t = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return t ? { Authorization: `Bearer ${t}` } : {};
}

interface PendingItem {
  id: string;
  kind: "Sales" | "GSTR-2B";
  label: string;
  href: string;
  status: string;
}

/**
 * Accountant/auditor home - Phase 2 of the role-based dashboard rollout.
 * Shows only what this role actually acts on day to day: reviews waiting
 * for a decision. Deliberately omits system health, LLM cost, and raw
 * failure logs (see the plan agreed with the user 2026-07-09) - those are
 * developer-only content that the old single shared dashboard used to
 * show everyone regardless of role.
 */
export default function AccountantHome() {
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [needsAttention, setNeedsAttention] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE_URL}/api/sales/period-reviews`, { headers: authHdr() }).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE_URL}/api/purchase/gstr2b-reviews`, { headers: authHdr() }).then((r) => r.json()).catch(() => []),
    ]).then(([sales, gstr2b]) => {
      const salesPending: PendingItem[] = (Array.isArray(sales) ? sales : [])
        .filter((r: any) => r.status === "PENDING_REVIEW")
        .map((r: any) => ({ id: r.id, kind: "Sales" as const, label: `Sales - ${r.period}`, href: "/sales-period-review", status: r.status }));
      const gstr2bPending: PendingItem[] = (Array.isArray(gstr2b) ? gstr2b : [])
        .filter((r: any) => r.status === "PENDING_REVIEW")
        .map((r: any) => ({ id: r.id, kind: "GSTR-2B" as const, label: `GSTR-2B - ${r.period} (${r.gstin})`, href: "/purchase-gstr2b-review", status: r.status }));
      setPending([...salesPending, ...gstr2bPending]);
      setLoading(false);
    });
  }, []);

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "40px 24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <ClipboardCheck size={20} style={{ color: "var(--accent)" }} />
        <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0 }}>Accountant</p>
      </div>
      <h1 style={{ fontSize: 26, fontWeight: 600, margin: "0 0 24px" }}>Your work today</h1>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 28 }}>
        <MetricCard label="Awaiting your approval" value={pending.length} color={pending.length > 0 ? "var(--amber)" : undefined} />
        <MetricCard label="Sales reviews pending" value={pending.filter((p) => p.kind === "Sales").length} />
        <MetricCard label="GSTR-2B reviews pending" value={pending.filter((p) => p.kind === "GSTR-2B").length} />
      </div>

      <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>Pending review</p>
      {loading ? (
        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</div>
      ) : pending.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "24px 0" }}>Nothing waiting on you right now.</div>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", overflow: "hidden", marginBottom: 28 }}>
          {pending.map((item, i) => (
            <div
              key={item.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "12px 16px",
                background: "var(--bg-card)",
                borderBottom: i < pending.length - 1 ? "1px solid var(--border)" : "none",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {item.kind === "Sales" ? (
                  <FileSpreadsheet size={15} style={{ color: "var(--text-muted)" }} />
                ) : (
                  <GitCompareArrows size={15} style={{ color: "var(--text-muted)" }} />
                )}
                <span style={{ fontSize: 13, fontWeight: 500 }}>{item.label}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <StatusBadge status={item.status} />
                <Link href={item.href} className="btn-ghost" style={{ padding: "6px 12px", fontSize: 12, borderRadius: "var(--radius-sm)", textDecoration: "none" }}>
                  Review
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 12 }}>
        <Link href="/invoice-extractor" className="btn-ghost" style={{ padding: "10px 16px", fontSize: 13, borderRadius: "var(--radius-sm)", textDecoration: "none" }}>
          Upload new batch
        </Link>
        <Link href="/reconciliation" className="btn-ghost" style={{ padding: "10px 16px", fontSize: 13, borderRadius: "var(--radius-sm)", textDecoration: "none" }}>
          Run reconciliation
        </Link>
      </div>
    </div>
  );
}
