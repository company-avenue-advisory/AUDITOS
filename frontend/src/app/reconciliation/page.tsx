"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Upload,
  AlertTriangle,
  CheckCircle,
  Loader2,
  Download,
  RefreshCw,
  GitCompareArrows,
  ShieldAlert,
  TrendingDown,
  BookOpen,
  Database,
  Filter,
} from "lucide-react";

/* ─────────── Types ─────────── */
interface Rule364 {
  cap: number;
  total_claimed: number;
  excess: number;
  breached: boolean;
}

interface ReconcileSummary {
  counts: { matched: number; mismatch: number; missing_in_2b: number; not_in_books: number };
  amounts: { matched: number; mismatch: number; missing_in_2b: number; not_in_books: number };
  itc_at_risk: number;
  matched_itc: number;
  total_rows: number;
  rule_36_4?: Rule364;
}

interface ReconcileResult {
  rows: Record<string, unknown>[];
  extra: Record<string, unknown>[];
  summary: ReconcileSummary;
}

interface BatchMeta { id: string; status: string; created_at: string; total_files: number; }

/* ─────────── Config ─────────── */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHdr() {
  const t = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

const STATUS_FILTERS = ["all", "matched", "mismatch", "missing_in_2b", "not_in_books"] as const;
type StatusFilter = typeof STATUS_FILTERS[number];

/* ─────────── Component ─────────── */
export default function ReconciliationPage() {
  const [gstr2bFile, setGstr2bFile] = useState<File | null>(null);
  const [booksFile, setBooksFile] = useState<File | null>(null);
  const [reconResult, setReconResult] = useState<ReconcileResult | null>(null);
  const [reconLoading, setReconLoading] = useState(false);
  const [reconError, setReconError] = useState("");
  const [booksItems, setBooksItems] = useState<Record<string, unknown>[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // Batch-connect mode
  const [booksMode, setBooksMode] = useState<"upload" | "batch">("batch");
  const [recentBatches, setRecentBatches] = useState<BatchMeta[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<string>("");
  const [batchesLoading, setBatchesLoading] = useState(false);

  const gstr2bRef = useRef<HTMLInputElement>(null);
  const booksRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setBatchesLoading(true);
    fetch(`${API_BASE_URL}/api/jobs`, { headers: authHdr() })
      .then((r) => r.json())
      .then((d) => {
        const batches: BatchMeta[] = (d.jobs || [])
          .filter((b: any) => b.status === "COMPLETED")
          .slice(0, 10);
        setRecentBatches(batches);
        if (batches.length > 0) setSelectedBatchId(batches[0].id);
      })
      .catch(() => {})
      .finally(() => setBatchesLoading(false));
  }, []);

  /* ── File handlers ── */
  const onGstr2bChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.name.toLowerCase().endsWith(".json")) {
      setGstr2bFile(file);
      setReconError("");
      setReconResult(null);
    } else {
      setReconError("Please upload a valid JSON file.");
    }
  };

  const onBooksChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.name.toLowerCase().endsWith(".json")) {
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const items = Array.isArray(data) ? data : data.items || [];
        setBooksItems(items);
        setBooksFile(file);
        setReconError("");
      } catch {
        setReconError("Invalid JSON in books file.");
      }
    } else {
      setReconError("Upload a JSON file with your extracted invoice data.");
    }
  };

  /* ── Reconciliation ── */
  const startReconciliation = async () => {
    if (!gstr2bFile) return;
    if (booksMode === "upload" && !booksItems.length) return;
    if (booksMode === "batch" && !selectedBatchId) return;
    setReconLoading(true);
    setReconError("");
    setStatusFilter("all");

    try {
      const text = await gstr2bFile.text();
      let parsed: unknown;
      try { parsed = JSON.parse(text); }
      catch { throw new Error("Invalid GSTR-2B JSON file."); }

      let res: Response;
      if (booksMode === "batch") {
        res = await fetch(`${API_BASE_URL}/api/reconcile/from-batch/${selectedBatchId}`, {
          method: "POST",
          headers: authHdr(),
          body: JSON.stringify({ gstr2b: parsed }),
        });
      } else {
        res = await fetch(`${API_BASE_URL}/api/reconcile`, {
          method: "POST",
          headers: authHdr(),
          body: JSON.stringify({ items: booksItems, gstr2b: parsed }),
        });
      }
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || "Reconciliation failed.");
      }
      const data: ReconcileResult = await res.json();
      setReconResult(data);
    } catch (e: unknown) {
      setReconError(e instanceof Error ? e.message : "Failed to run reconciliation.");
    } finally {
      setReconLoading(false);
    }
  };

  const exportReconciliation = async () => {
    if (!gstr2bFile) return;
    if (booksMode === "upload" && !booksItems.length) return;
    try {
      const text = await gstr2bFile.text();
      const res = await fetch(`${API_BASE_URL}/api/reconcile/export`, {
        method: "POST",
        headers: authHdr(),
        body: JSON.stringify({
          items: booksMode === "batch" ? [] : booksItems,
          gstr2b: JSON.parse(text),
        }),
      });
      if (!res.ok) throw new Error("Export failed.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), {
        href: url,
        download: "gstr2b_reconciliation.xlsx",
      });
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Download failed.";
      setReconError(msg);
    }
  };

  /* ── Metric card config ── */
  const metricCards = reconResult
    ? [
        {
          label: "Matched",
          count: reconResult.summary.counts.matched,
          val: reconResult.summary.amounts.matched,
          col: "#22c55e",
          bg: "var(--green-soft)",
          icon: CheckCircle,
        },
        {
          label: "Amount Mismatch",
          count: reconResult.summary.counts.mismatch,
          val: reconResult.summary.amounts.mismatch,
          col: "#f59e0b",
          bg: "var(--amber-soft)",
          icon: AlertTriangle,
        },
        {
          label: "Missing in 2B (ITC Risk)",
          count: reconResult.summary.counts.missing_in_2b,
          val: reconResult.summary.amounts.missing_in_2b,
          col: "#ef4444",
          bg: "var(--red-soft)",
          icon: ShieldAlert,
        },
        {
          label: "Not Booked (in 2B)",
          count: reconResult.summary.counts.not_in_books,
          val: reconResult.summary.amounts.not_in_books,
          col: "#60a5fa",
          bg: "var(--blue-soft)",
          icon: BookOpen,
        },
      ]
    : [];

  return (
    <main style={{ minHeight: "100vh", padding: "48px 24px 80px" }}>
      <div
        style={{
          maxWidth: 1160,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 32,
        }}
      >
        {/* ══ HEADER ══ */}
        <header
          className="animate-fade-up"
          style={{ textAlign: "center", paddingBottom: 8 }}
        >
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: "rgba(99,102,241,0.12)",
              border: "1px solid rgba(99,102,241,0.25)",
              borderRadius: 99,
              padding: "5px 14px",
              fontSize: 12,
              color: "#a5b4fc",
              fontWeight: 500,
              marginBottom: 20,
              letterSpacing: "0.02em",
            }}
          >
            <GitCompareArrows size={12} />
            GSTR-2B Cross-Reference Engine
          </div>

          <h1
            style={{
              fontSize: "clamp(32px, 5vw, 48px)",
              fontWeight: 800,
              letterSpacing: "-0.04em",
              lineHeight: 1.05,
              margin: 0,
            }}
          >
            <span className="shimmer-text">Reconciliation</span>
          </h1>
          <p
            style={{
              marginTop: 16,
              color: "var(--text-secondary)",
              fontSize: 15,
              fontWeight: 400,
              maxWidth: 560,
              margin: "16px auto 0",
              lineHeight: 1.6,
            }}
          >
            Upload your GSTR-2B JSON from the GST portal and your extracted
            invoice data to verify compliance, identify ITC at risk, and
            generate audit reports.
          </p>
        </header>

        {/* ══ UPLOAD SECTION ══ */}
        <section
          className="glass animate-fade-up"
          style={{
            borderRadius: "var(--radius-xl)",
            overflow: "hidden",
            padding: "28px 32px",
            animationDelay: "0.1s",
          }}
        >
          <div style={{ marginBottom: 20 }}>
            <h2
              style={{
                fontSize: 17,
                fontWeight: 700,
                color: "var(--text-primary)",
                letterSpacing: "-0.02em",
                marginBottom: 4,
              }}
            >
              Upload Data Sources
            </h2>
            <p
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                margin: 0,
              }}
            >
              Provide both data sources to start the reconciliation engine.
            </p>
          </div>

          {reconError && (
            <div
              style={{
                background: "var(--red-soft)",
                border: "1px solid rgba(239,68,68,0.25)",
                borderRadius: "var(--radius-md)",
                padding: "12px 16px",
                marginBottom: 16,
                display: "flex",
                gap: 10,
                alignItems: "center",
                fontSize: 13,
                color: "#fca5a5",
              }}
            >
              <AlertTriangle
                size={14}
                style={{ color: "var(--red)", flexShrink: 0 }}
              />{" "}
              {reconError}
            </div>
          )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 16,
              marginBottom: 24,
            }}
          >
            {/* Books source — batch connect or JSON upload */}
            <div className="glass" style={{ borderRadius: "var(--radius-md)", padding: "20px", display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Mode toggle */}
              <div style={{ display: "flex", gap: 6, background: "rgba(0,0,0,0.25)", borderRadius: 8, padding: 3 }}>
                {(["batch", "upload"] as const).map((mode) => (
                  <button key={mode} onClick={() => setBooksMode(mode)} style={{ flex: 1, padding: "6px 10px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, background: booksMode === mode ? "var(--accent)" : "transparent", color: booksMode === mode ? "#fff" : "var(--text-muted)", transition: "all 0.15s" }}>
                    {mode === "batch" ? "Use Batch" : "Upload JSON"}
                  </button>
                ))}
              </div>

              {booksMode === "batch" ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Database size={16} style={{ color: "var(--accent)", flexShrink: 0 }} />
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>Select Extracted Batch</span>
                  </div>
                  {batchesLoading ? (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading batches…</div>
                  ) : recentBatches.length === 0 ? (
                    <div style={{ fontSize: 12, color: "#f59e0b" }}>No completed batches found. Run the extractor first.</div>
                  ) : (
                    <select value={selectedBatchId} onChange={(e) => setSelectedBatchId(e.target.value)} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px", color: "var(--text-primary)", fontSize: 12, cursor: "pointer" }}>
                      {recentBatches.map((b) => (
                        <option key={b.id} value={b.id}>{b.id.slice(0,8)}… · {new Date(b.created_at).toLocaleDateString("en-IN")} · {b.total_files ?? "?"} files</option>
                      ))}
                    </select>
                  )}
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Purchase items from this batch will be used as your books.</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, cursor: "pointer" }} onClick={() => booksRef.current?.click()}>
                  <input type="file" accept=".json" ref={booksRef} style={{ display: "none" }} onChange={onBooksChange} />
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.25)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <Upload size={16} style={{ color: "var(--accent)" }} />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>{booksFile ? booksFile.name : "Books Data (JSON)"}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{booksItems.length > 0 ? `${booksItems.length} items loaded` : "Exported invoice items"}</div>
                  </div>
                </div>
              )}
            </div>

            {/* GSTR-2B upload */}
            <div
              className="glass"
              style={{
                borderRadius: "var(--radius-md)",
                padding: "20px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                cursor: "pointer",
                transition: "border-color 0.15s ease",
              }}
              onClick={() => gstr2bRef.current?.click()}
            >
              <input
                type="file"
                accept=".json"
                ref={gstr2bRef}
                style={{ display: "none" }}
                onChange={onGstr2bChange}
              />
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "rgba(245,158,11,0.12)",
                  border: "1px solid rgba(245,158,11,0.25)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Upload
                  size={18}
                  style={{ color: "var(--amber)" }}
                />
              </div>
              <div style={{ textAlign: "center" }}>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    marginBottom: 2,
                  }}
                >
                  {gstr2bFile ? gstr2bFile.name : "GSTR-2B JSON"}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                  }}
                >
                  From GST portal download
                </div>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <button
              id="start-reconciliation-btn"
              className="btn-primary"
              onClick={startReconciliation}
              disabled={!gstr2bFile || reconLoading || (booksMode === "upload" && !booksItems.length) || (booksMode === "batch" && !selectedBatchId)}
              style={{
                padding: "12px 24px",
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: (!gstr2bFile || reconLoading) ? "not-allowed" : "pointer",
                opacity: (!gstr2bFile || reconLoading) ? 0.6 : 1,
              }}
            >
              {reconLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              <span>Run Reconciliation</span>
            </button>

            {reconResult && (
              <button
                id="export-recon-btn"
                className="btn-ghost"
                onClick={exportReconciliation}
                style={{
                  padding: "12px 24px",
                  fontSize: 13,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  background: "var(--green-soft)",
                  color: "#86efac",
                  border: "1px solid rgba(34,197,94,0.25)",
                }}
              >
                <Download size={14} />
                <span style={{ fontWeight: 600 }}>
                  Export Audit Report
                </span>
              </button>
            )}
          </div>
        </section>

        {/* ══ METRIC CARDS ══ */}
        {reconResult && (
          <div
            className="animate-fade-up"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 16,
            }}
          >
            {metricCards.map((s) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.label}
                  className="glass"
                  style={{
                    background: s.bg,
                    border: `1px solid ${s.col}33`,
                    borderRadius: "var(--radius-lg)",
                    padding: "20px",
                    textAlign: "center",
                  }}
                >
                  <Icon
                    size={20}
                    style={{
                      color: s.col,
                      margin: "0 auto 8px",
                      display: "block",
                    }}
                  />
                  <div
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      color: s.col,
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: 4,
                    }}
                  >
                    {s.label}
                  </div>
                  <div
                    style={{
                      fontSize: 28,
                      fontWeight: 800,
                      color: "var(--text-primary)",
                      letterSpacing: "-0.03em",
                    }}
                  >
                    {s.count}
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: s.col,
                      opacity: 0.8,
                      marginTop: 4,
                    }}
                  >
                    ₹{" "}
                    {s.val.toLocaleString("en-IN", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ══ ITC RISK BANNER ══ */}
        {reconResult && reconResult.summary.itc_at_risk > 0 && (
          <div
            className="animate-fade-up"
            style={{
              background: "var(--red-soft)",
              border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: "var(--radius-lg)",
              padding: "20px 24px",
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}
          >
            <TrendingDown
              size={24}
              style={{ color: "var(--red)", flexShrink: 0 }}
            />
            <div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: "#fca5a5",
                  marginBottom: 4,
                }}
              >
                ITC at Risk
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "#fca5a5",
                  opacity: 0.8,
                  lineHeight: 1.5,
                }}
              >
                ₹{" "}
                {reconResult.summary.itc_at_risk.toLocaleString("en-IN", {
                  minimumFractionDigits: 2,
                })}{" "}
                in ITC may be at risk due to missing or mismatched invoices.
                Review the table below and export the audit report for filing.
              </div>
            </div>
          </div>
        )}

        {/* ══ RULE 36(4) BANNER ══ */}
        {reconResult?.summary?.rule_36_4?.breached && (
          <div className="animate-fade-up" style={{ background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: "var(--radius-lg)", padding: "18px 24px", display: "flex", alignItems: "flex-start", gap: 14 }}>
            <ShieldAlert size={22} style={{ color: "#ef4444", flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#fca5a5", marginBottom: 6 }}>Rule 36(4) ITC Cap Breached</div>
              <div style={{ fontSize: 12, color: "#fca5a5", lineHeight: 1.6 }}>
                Your provisional ITC cap is <strong>₹ {reconResult.summary.rule_36_4!.cap.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong> (105% of GSTR-2B matched ITC).
                Total ITC claimed in books is <strong>₹ {reconResult.summary.rule_36_4!.total_claimed.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>.
                Excess of <strong>₹ {reconResult.summary.rule_36_4!.excess.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong> may be disallowed.
                Reverse or defer the excess before filing GSTR-3B.
              </div>
            </div>
          </div>
        )}

        {/* ══ RECONCILIATION TABLE ══ */}
        {reconResult && (
          <section
            className="glass animate-fade-up"
            style={{
              borderRadius: "var(--radius-xl)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "24px 28px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 17, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>Reconciliation Detail</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", background: "rgba(255,255,255,0.07)", border: "1px solid var(--border)", borderRadius: 99, padding: "2px 10px" }}>
                  {reconResult.summary.total_rows} rows
                </span>
              </div>
              {/* Status filter tabs */}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {STATUS_FILTERS.map((f) => {
                  const labels: Record<string, string> = { all: "All", matched: "✓ Matched", mismatch: "⚠ Mismatch", missing_in_2b: "✗ Missing 2B", not_in_books: "ℹ Not Booked" };
                  const colors: Record<string, string> = { all: "var(--accent)", matched: "#22c55e", mismatch: "#f59e0b", missing_in_2b: "#ef4444", not_in_books: "#60a5fa" };
                  const active = statusFilter === f;
                  const count = f === "all" ? reconResult.summary.total_rows : (f === "not_in_books" ? reconResult.extra.length : reconResult.rows.filter((r) => r.recon_status === f).length);
                  return (
                    <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: "5px 12px", borderRadius: 99, border: `1px solid ${active ? colors[f] : "var(--border)"}`, background: active ? `${colors[f]}22` : "transparent", color: active ? colors[f] : "var(--text-muted)", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                      {labels[f]} {count > 0 && <span style={{ opacity: 0.7 }}>({count})</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 11,
                }}
              >
                <thead>
                  <tr
                    style={{
                      background: "rgba(0,0,0,0.25)",
                      borderBottom: "1px solid var(--border)",
                      textAlign: "left",
                      color: "var(--text-muted)",
                    }}
                  >
                    <th style={{ padding: "10px 8px", fontWeight: 600 }}>
                      Status
                    </th>
                    <th style={{ padding: "10px 8px", fontWeight: 600 }}>
                      Invoice
                    </th>
                    <th style={{ padding: "10px 8px", fontWeight: 600 }}>
                      GSTIN
                    </th>
                    <th
                      style={{
                        padding: "10px 8px",
                        fontWeight: 600,
                        textAlign: "right",
                      }}
                    >
                      Books Amount
                    </th>
                    <th
                      style={{
                        padding: "10px 8px",
                        fontWeight: 600,
                        textAlign: "right",
                      }}
                    >
                      2B Amount
                    </th>
                    <th style={{ padding: "10px 8px", fontWeight: 600, textAlign: "right" }}>Diff</th>
                    <th style={{ padding: "10px 8px", fontWeight: 600 }}>ITC Eligibility</th>
                  </tr>
                </thead>
                <tbody>
                  {([...reconResult.rows, ...reconResult.extra] as Record<string, unknown>[]).filter((r) => statusFilter === "all" || r.recon_status === statusFilter).map(
                    (r, i) => {
                      const st = r.recon_status as string;
                      const color =
                        st === "matched"
                          ? "#22c55e"
                          : st === "mismatch"
                            ? "#f59e0b"
                            : st === "not_in_books"
                              ? "#60a5fa"
                              : "#ef4444";
                      const bg =
                        st === "matched"
                          ? "rgba(34,197,94,0.04)"
                          : st === "mismatch"
                            ? "rgba(245,158,11,0.04)"
                            : st === "not_in_books"
                              ? "rgba(96,165,250,0.04)"
                              : "rgba(239,68,68,0.04)";
                      const label =
                        st === "matched"
                          ? "✓ Matched"
                          : st === "mismatch"
                            ? "⚠ Mismatch"
                            : st === "not_in_books"
                              ? "ℹ Not Booked"
                              : "✗ Missing 2B";
                      const totalAmount = r.total_amount as number | undefined;
                      const total2b = r["2b_total_val"] as number | undefined;
                      const diffAmount = r.diff_amount as number | undefined;
                      return (
                        <tr
                          key={i}
                          style={{
                            borderBottom: "1px solid var(--border)",
                            background: bg,
                          }}
                        >
                          <td
                            style={{
                              padding: 8,
                              color,
                              fontWeight: 600,
                              whiteSpace: "nowrap",
                            }}
                          >
                            {label}
                          </td>
                          <td
                            style={{
                              padding: 8,
                              color: "var(--text-secondary)",
                            }}
                          >
                            {(r.supplier_inv as string) || "-"}
                          </td>
                          <td
                            style={{
                              padding: 8,
                              fontFamily: "monospace",
                              color: "var(--text-secondary)",
                            }}
                          >
                            {(r.gst_no as string) || (r.gstin as string) || "-"}
                          </td>
                          <td
                            style={{
                              padding: 8,
                              textAlign: "right",
                              color: "var(--text-primary)",
                            }}
                          >
                            {totalAmount
                              ? totalAmount.toFixed(2)
                              : "-"}
                          </td>
                          <td
                            style={{
                              padding: 8,
                              textAlign: "right",
                              color: "var(--text-primary)",
                            }}
                          >
                            {total2b
                              ? total2b.toFixed(2)
                              : "-"}
                          </td>
                          <td style={{ padding: 8, textAlign: "right", color: diffAmount && Math.abs(diffAmount) > 2 ? "#ef4444" : "var(--text-primary)", fontWeight: diffAmount && Math.abs(diffAmount) > 2 ? 700 : 400 }}>
                            {diffAmount ? diffAmount.toFixed(2) : "-"}
                          </td>
                          <td style={{ padding: 8 }}>
                            {(() => {
                              const itc = r.itc_eligibility as string | undefined;
                              if (!itc || itc === "ITC_UNKNOWN") return <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>;
                              const col = itc === "ITC_ELIGIBLE" ? "#22c55e" : itc === "ITC_BLOCKED" ? "#ef4444" : itc === "ITC_RESTRICTED" ? "#f59e0b" : "var(--text-muted)";
                              return <span style={{ fontSize: 10, fontWeight: 700, color: col, background: `${col}18`, borderRadius: 4, padding: "2px 6px" }}>{itc.replace("ITC_", "")}</span>;
                            })()}
                          </td>
                        </tr>
                      );
                    }
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
