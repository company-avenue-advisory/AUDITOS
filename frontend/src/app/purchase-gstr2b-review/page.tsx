"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  GitCompareArrows,
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
  gstin: string;
  status: string;
  created_at: string | null;
  reviewed_at: string | null;
}

interface Rule364 {
  cap: number;
  total_claimed: number;
  excess: number;
  breached: boolean;
}

interface ReconSummary {
  counts: { matched: number; mismatch: number; missing_in_2b: number; not_in_books: number };
  amounts: { matched: number; mismatch: number; missing_in_2b: number; not_in_books: number };
  itc_at_risk: number;
  matched_itc: number;
  total_rows: number;
  fuzzy_matched_count?: number;
  rule_36_4?: Rule364;
}

interface ReviewDetail {
  id: string;
  tenant_id: string;
  period: string;
  gstin: string;
  status: string;
  recon_summary: ReconSummary;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  created_at: string | null;
}

export default function PurchaseGstr2bReviewPage() {
  const [reviews, setReviews] = useState<ReviewListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [notes, setNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");

  const [period, setPeriod] = useState("");
  const [gstin, setGstin] = useState("");
  const [gstr2bFile, setGstr2bFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const canDecide = ["owner", "auditor"].includes(
    (typeof window !== "undefined" ? localStorage.getItem("user_role") : "") || ""
  );

  const loadList = () => {
    setListLoading(true);
    fetch(`${API_BASE_URL}/api/purchase/gstr2b-reviews`, { headers: authHdr() })
      .then((r) => r.json())
      .then((d) => setReviews(Array.isArray(d) ? d : []))
      .catch(() => setError("Couldn't load GSTR-2B reviews."))
      .finally(() => setListLoading(false));
  };

  useEffect(() => {
    loadList();
  }, []);

  const loadDetail = (id: string) => {
    setSelectedId(id);
    setDetailLoading(true);
    setNotes("");
    fetch(`${API_BASE_URL}/api/purchase/gstr2b-reviews/${id}`, { headers: authHdr() })
      .then((r) => r.json())
      .then((d) => setDetail(d))
      .catch(() => setError("Couldn't load review detail."))
      .finally(() => setDetailLoading(false));
  };

  const handleGenerate = async () => {
    if (!period || !gstin || !gstr2bFile) {
      setError("Enter a period, GSTIN, and choose a GSTR-2B JSON file.");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      const form = new FormData();
      form.append("period", period);
      form.append("gstin", gstin);
      form.append("gstr2b_file", gstr2bFile);
      const res = await fetch(`${API_BASE_URL}/api/purchase/gstr2b-reviews/generate`, {
        method: "POST",
        headers: authHdr(),
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Generate failed.");
      }
      const d = await res.json();
      setGstr2bFile(null);
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
      const res = await fetch(`${API_BASE_URL}/api/purchase/gstr2b-reviews/${selectedId}/${action}`, {
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
        <GitCompareArrows size={20} style={{ color: "var(--accent)" }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>GSTR-2B review</h1>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>
        Books reconciled against a GSTR-2B statement, waiting on a decision before anything feeds a GSTR-3B ITC claim.
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
              type="text"
              placeholder="27AADCO0061H1ZQ"
              value={gstin}
              onChange={(e) => setGstin(e.target.value.toUpperCase())}
              style={{
                width: "100%",
                padding: "8px 10px",
                marginBottom: 8,
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "var(--bg-card)",
                color: "var(--text-primary)",
                fontSize: 13,
                fontFamily: "monospace",
              }}
            />
            <input
              ref={fileRef}
              type="file"
              accept=".json"
              onChange={(e) => setGstr2bFile(e.target.files?.[0] || null)}
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
                  <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>{r.gstin}</div>
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
                  <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>{detail.gstin}</div>
                </div>
                <StatusBadge status={detail.status} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 16 }}>
                <MetricCard label="Matched" value={detail.recon_summary.counts.matched} color="var(--green)" />
                <MetricCard label="Mismatch" value={detail.recon_summary.counts.mismatch} color="var(--amber)" />
                <MetricCard label="Missing in 2B" value={detail.recon_summary.counts.missing_in_2b} color="var(--red)" />
                <MetricCard label="Not in books" value={detail.recon_summary.counts.not_in_books} color="var(--blue)" />
              </div>

              <div className="glass" style={{ borderRadius: "var(--radius-md)", padding: "14px 18px", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  {detail.recon_summary.rule_36_4?.breached ? (
                    <AlertTriangle size={16} style={{ color: "var(--red)" }} />
                  ) : (
                    <Check size={16} style={{ color: "var(--green)" }} />
                  )}
                  <span style={{ fontSize: 14, fontWeight: 600 }}>ITC summary</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8, fontSize: 13 }}>
                  <div>
                    <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Matched ITC</div>
                    <div style={{ fontWeight: 600 }}>{detail.recon_summary.matched_itc.toLocaleString()}</div>
                  </div>
                  <div>
                    <div style={{ color: "var(--text-muted)", fontSize: 11 }}>ITC at risk</div>
                    <div style={{ fontWeight: 600, color: detail.recon_summary.itc_at_risk > 0 ? "var(--amber)" : undefined }}>
                      {detail.recon_summary.itc_at_risk.toLocaleString()}
                    </div>
                  </div>
                  {detail.recon_summary.rule_36_4 && (
                    <>
                      <div>
                        <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Rule 36(4) cap</div>
                        <div style={{ fontWeight: 600 }}>{detail.recon_summary.rule_36_4.cap.toLocaleString()}</div>
                      </div>
                      <div>
                        <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Excess claimed</div>
                        <div style={{ fontWeight: 600, color: detail.recon_summary.rule_36_4.excess > 0 ? "var(--red)" : undefined }}>
                          {detail.recon_summary.rule_36_4.excess.toLocaleString()}
                        </div>
                      </div>
                    </>
                  )}
                  {typeof detail.recon_summary.fuzzy_matched_count === "number" && detail.recon_summary.fuzzy_matched_count > 0 && (
                    <div>
                      <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Fuzzy matched</div>
                      <div style={{ fontWeight: 600 }}>{detail.recon_summary.fuzzy_matched_count}</div>
                    </div>
                  )}
                </div>
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
