"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  FileSpreadsheet,
  Upload,
  Loader2,
  Check,
  X,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import StatusBadge from "../../components/ui/StatusBadge";
import MetricCard from "../../components/ui/MetricCard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHdr(): Record<string, string> {
  const t = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return t ? { Authorization: `Bearer ${t}` } : {};
}

interface ReviewListItem {
  id: string;
  period: string;
  status: string;
  created_at: string | null;
  reviewed_at: string | null;
}

interface NeedsAttentionItem {
  doc_no: string;
  status: string;
  note: string;
}

interface TotalsMatch {
  os_net_taxable: number;
  client_net_taxable: number;
  gstr1_net_taxable: number | null;
  matches: boolean;
  note: string;
}

interface ReconSummary {
  counts: Record<string, number>;
  needs_attention: NeedsAttentionItem[];
  totals_match?: TotalsMatch;
}

interface FilingSummaryEntry {
  has_data: boolean;
  total_taxable: number;
  total_tax: number;
  total_invoices: number;
  sections_with_data: string[];
  flagged_unresolved: string[];
  skipped: { doc_no: string; status: string; note: string }[];
}

interface ReviewDetail {
  id: string;
  tenant_id: string;
  period: string;
  status: string;
  recon_summary: ReconSummary;
  filings_summary: Record<string, FilingSummaryEntry>;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  created_at: string | null;
}

export default function SalesPeriodReviewPage() {
  const [reviews, setReviews] = useState<ReviewListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [notes, setNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");

  const [period, setPeriod] = useState("");
  const [clientSheet, setClientSheet] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const canDecide = ["owner", "auditor"].includes(
    (typeof window !== "undefined" ? localStorage.getItem("user_role") : "") || ""
  );

  const loadList = () => {
    setListLoading(true);
    fetch(`${API_BASE_URL}/api/sales/period-reviews`, { headers: authHdr() })
      .then((r) => r.json())
      .then((d) => setReviews(Array.isArray(d) ? d : []))
      .catch(() => setError("Couldn't load period reviews."))
      .finally(() => setListLoading(false));
  };

  useEffect(() => {
    loadList();
  }, []);

  const loadDetail = (id: string) => {
    setSelectedId(id);
    setDetailLoading(true);
    setNotes("");
    fetch(`${API_BASE_URL}/api/sales/period-reviews/${id}`, { headers: authHdr() })
      .then((r) => r.json())
      .then((d) => setDetail(d))
      .catch(() => setError("Couldn't load review detail."))
      .finally(() => setDetailLoading(false));
  };

  const handleGenerate = async () => {
    if (!period || !clientSheet) {
      setError("Enter a period and choose a client sheet.");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      const form = new FormData();
      form.append("period", period);
      form.append("client_sheet", clientSheet);
      const res = await fetch(`${API_BASE_URL}/api/sales/period-reviews/generate`, {
        method: "POST",
        headers: authHdr(),
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Generate failed.");
      }
      const d = await res.json();
      setClientSheet(null);
      if (fileRef.current) fileRef.current.value = "";
      loadList();
      loadDetail(d.id);
    } catch (e: any) {
      setError(e.message || "Generate failed.");
    } finally {
      setGenerating(false);
    }
  };

  const decide = async (action: "approve" | "reject") => {
    if (!selectedId) return;
    if (action === "reject" && !notes.trim()) {
      setError("A rejection reason is required.");
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/api/sales/period-reviews/${selectedId}/${action}`, {
        method: "POST",
        headers: { ...authHdr(), "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes || null }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `${action} failed.`);
      }
      const d = await res.json();
      setDetail(d);
      loadList();
    } catch (e: any) {
      setError(e.message || `${action} failed.`);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div style={{ flex: 1, padding: "32px 40px", maxWidth: 1200 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <FileSpreadsheet size={20} style={{ color: "var(--accent)" }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Sales period review</h1>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>
        Reconciliation + GSTR-1 filing generated for a period, waiting on a decision before anything reaches a client or the GST portal.
      </p>

      {error && (
        <div
          className="glass"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderRadius: "var(--radius-sm)",
            padding: "10px 14px",
            marginBottom: 16,
            color: "var(--red)",
            fontSize: 13,
          }}
        >
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 24 }}>
        {/* ── Left: generate form + list ── */}
        <div style={{ width: 320, flexShrink: 0 }}>
          <div className="glass" style={{ borderRadius: "var(--radius-md)", padding: 16, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Generate a review</div>
            <input
              type="text"
              placeholder="2026-06"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 10px",
                marginBottom: 8,
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                fontSize: 13,
              }}
            />
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setClientSheet(e.target.files?.[0] || null)}
              style={{ width: "100%", fontSize: 12, marginBottom: 10, color: "var(--text-secondary)" }}
            />
            <button
              className="btn-primary"
              onClick={handleGenerate}
              disabled={generating}
              style={{ width: "100%", padding: "10px", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 13 }}
            >
              {generating ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {generating ? "Generating..." : "Generate"}
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Reviews</div>
            <button onClick={loadList} className="btn-ghost" style={{ padding: "4px 8px", border: "none", background: "none" }}>
              <RefreshCw size={13} />
            </button>
          </div>

          {listLoading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</div>
          ) : reviews.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No reviews yet.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {reviews.map((r) => (
                <div
                  key={r.id}
                  onClick={() => loadDetail(r.id)}
                  className="glass"
                  style={{
                    borderRadius: "var(--radius-sm)",
                    padding: "10px 12px",
                    cursor: "pointer",
                    borderColor: selectedId === r.id ? "var(--accent)" : undefined,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{r.period}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right: detail ── */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!selectedId ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: 40, textAlign: "center" }}>
              Select a review from the list, or generate a new one.
            </div>
          ) : detailLoading || !detail ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700 }}>{detail.period}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    Generated {detail.created_at ? new Date(detail.created_at).toLocaleString() : "-"}
                  </div>
                </div>
                <StatusBadge status={detail.status} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 16 }}>
                <MetricCard
                  label="Total documents"
                  value={Object.values(detail.recon_summary.counts || {}).reduce((a, b) => a + b, 0)}
                />
                <MetricCard label="Passed" value={detail.recon_summary.counts?.PASS || 0} color="var(--green)" />
                <MetricCard
                  label="Needs attention"
                  value={detail.recon_summary.needs_attention?.length || 0}
                  color="var(--amber)"
                />
              </div>

              {detail.recon_summary.totals_match && (
                <div
                  className="glass"
                  style={{
                    borderRadius: "var(--radius-md)",
                    padding: "14px 18px",
                    marginBottom: 16,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    {detail.recon_summary.totals_match.matches ? (
                      <Check size={16} style={{ color: "var(--green)" }} />
                    ) : (
                      <AlertTriangle size={16} style={{ color: "var(--red)" }} />
                    )}
                    <span style={{ fontSize: 14, fontWeight: 600 }}>
                      {detail.recon_summary.totals_match.matches
                        ? "Totals match across all three sheets"
                        : "Totals mismatch - needs a look"}
                    </span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, fontSize: 13 }}>
                    <div>
                      <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Our records</div>
                      <div style={{ fontWeight: 600 }}>{detail.recon_summary.totals_match.os_net_taxable.toLocaleString()}</div>
                    </div>
                    <div>
                      <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Client sheet</div>
                      <div style={{ fontWeight: 600 }}>{detail.recon_summary.totals_match.client_net_taxable.toLocaleString()}</div>
                    </div>
                    <div>
                      <div style={{ color: "var(--text-muted)", fontSize: 11 }}>GSTR-1 filing</div>
                      <div style={{ fontWeight: 600 }}>
                        {detail.recon_summary.totals_match.gstr1_net_taxable !== null
                          ? detail.recon_summary.totals_match.gstr1_net_taxable.toLocaleString()
                          : "-"}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {detail.recon_summary.needs_attention?.length > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                    Needs attention
                  </div>
                  <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", overflow: "hidden", marginBottom: 16 }}>
                    {detail.recon_summary.needs_attention.map((item, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "10px 12px",
                          background: "var(--bg-card)",
                          borderBottom: i < detail.recon_summary.needs_attention.length - 1 ? "1px solid var(--border)" : "none",
                        }}
                      >
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>{item.doc_no}</div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{item.note}</div>
                        </div>
                        <StatusBadge status={item.status} />
                      </div>
                    ))}
                  </div>
                </>
              )}

              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                Filing summary by registration
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginBottom: 24 }}>
                {Object.entries(detail.filings_summary || {}).map(([gstin, f]) => (
                  <div key={gstin} className="glass" style={{ borderRadius: "var(--radius-md)", padding: "14px 16px" }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>{gstin}</div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                      <span style={{ color: "var(--text-secondary)" }}>Invoices</span>
                      <span>{f.total_invoices}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                      <span style={{ color: "var(--text-secondary)" }}>Taxable value</span>
                      <span>{f.total_taxable.toLocaleString()}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                      <span style={{ color: "var(--text-secondary)" }}>Tax</span>
                      <span>{f.total_tax.toLocaleString()}</span>
                    </div>
                    {f.flagged_unresolved?.length > 0 && (
                      <div style={{ marginTop: 8, fontSize: 11, color: "var(--amber)" }}>
                        {f.flagged_unresolved.length} flagged unresolved
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {detail.status === "PENDING_REVIEW" && canDecide && (
                <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>Add a note before you decide</div>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Optional context for this decision"
                    style={{
                      width: "100%",
                      minHeight: 60,
                      marginBottom: 12,
                      padding: "8px 10px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-card)",
                      color: "var(--text-primary)",
                      fontSize: 13,
                      resize: "vertical",
                    }}
                  />
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn-ghost"
                      onClick={() => decide("reject")}
                      disabled={actionLoading}
                      style={{ flex: 1, padding: "10px", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 13 }}
                    >
                      <X size={14} /> Reject
                    </button>
                    <button
                      className="btn-primary"
                      onClick={() => decide("approve")}
                      disabled={actionLoading}
                      style={{ flex: 1, padding: "10px", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 13 }}
                    >
                      {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Approve
                    </button>
                  </div>
                </div>
              )}

              {detail.status !== "PENDING_REVIEW" && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                  {detail.status === "APPROVED" ? "Approved" : "Rejected"} {detail.reviewed_at ? `on ${new Date(detail.reviewed_at).toLocaleString()}` : ""}
                  {detail.review_notes ? ` — "${detail.review_notes}"` : ""}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
