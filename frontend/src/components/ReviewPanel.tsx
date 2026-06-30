"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  X,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ChevronRight,
  Zap,
  BadgeCheck,
  Scale,
  ListChecks,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ReviewItem {
  field_name: string;
  extracted_value: number | null;
  calculated_value: number | null;
  expected_value: number | null;
  variance: number | null;
  reason: string;
  recommendation: string;
  severity: "ERROR" | "BLOCKER" | "WARNING";
  failure_category: string;
}

interface ReconReport {
  is_reconciled: boolean;
  status: string;
  overall_confidence: number;
  calculated_taxable: number;
  calculated_tax: number;
  calculated_total: number;
  variance_taxable: number;
  variance_total: number;
  failed_fields: string[];
  calculation_trace: {
    semantic_columns: Record<string, string>;
    math_evaluation: { winning_path: string; min_variance: number };
    grand_total: number;
    calculated_total: number;
    taxable_value: number;
    calculated_taxable: number;
  };
  review_context: {
    is_blocked: boolean;
    items: ReviewItem[];
  };
  execution_time_ms: number;
}

interface ReviewResponse {
  task_id: string;
  filename: string;
  recon_status: string | null;
  recon_report: ReconReport | null;
}

const STATUS_CONFIG: Record<string, { icon: React.ElementType; color: string; bg: string; border: string; label: string }> = {
  ERP_READY: { icon: ShieldCheck, color: "#22c55e", bg: "rgba(34,197,94,0.08)", border: "rgba(34,197,94,0.25)", label: "ERP Ready" },
  HUMAN_CORRECTED: { icon: BadgeCheck, color: "#a78bfa", bg: "rgba(167,139,250,0.08)", border: "rgba(167,139,250,0.25)", label: "Human Corrected" },
  NEEDS_REVIEW: { icon: ShieldAlert, color: "#f59e0b", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.25)", label: "Needs Review" },
  BLOCKED: { icon: ShieldX, color: "#ef4444", bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.25)", label: "Blocked" },
};

const FMT = (v: number | null | undefined) =>
  v == null ? "—" : `INR ${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function ReviewPanel({ taskId, filename, batchId, onClose, onAccepted }: {
  taskId: string; filename: string; batchId?: string; onClose: () => void; onAccepted?: () => void;
}) {
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState(false);

  const fetchReview = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/review`);
      if (!res.ok) throw new Error("Failed to load review report.");
      const json: ReviewResponse = await res.json();
      setData(json);
      if (json.recon_status === "HUMAN_CORRECTED") setAccepted(true);
    } catch (e) { setError(e instanceof Error ? e.message : "Unknown error"); }
    finally { setLoading(false); }
  }, [taskId]);

  useEffect(() => { fetchReview(); }, [fetchReview]);

  // Load source PDF when batchId + filename are available
  useEffect(() => {
    if (!batchId || !filename) return;
    setPdfLoading(true); setPdfError(false);
    const token = localStorage.getItem("token");
    fetch(`${API_BASE_URL}/api/jobs/${batchId}/files/${encodeURIComponent(filename)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error("not found");
        return r.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        setPdfUrl(url);
      })
      .catch(() => setPdfError(true))
      .finally(() => setPdfLoading(false));
    return () => {
      // cleanup blob URL on unmount / filename change
      setPdfUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, [batchId, filename]);

  const handleAccept = async () => {
    setAccepting(true);
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/accept-correction`, {
        method: "PATCH", headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to accept correction.");
      setAccepted(true);
      if (data) setData({ ...data, recon_status: "HUMAN_CORRECTED" });
      onAccepted?.();
    } catch (e) { setError(e instanceof Error ? e.message : "Acceptance failed"); }
    finally { setAccepting(false); }
  };

  const status = data?.recon_status ?? "NEEDS_REVIEW";
  const statusCfg = STATUS_CONFIG[status] ?? STATUS_CONFIG["NEEDS_REVIEW"];
  const StatusIcon = statusCfg.icon;
  const report = data?.recon_report;

  const hasPdf = batchId && (pdfUrl || pdfLoading || pdfError);

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", backdropFilter: "blur(4px)", zIndex: 1000, display: "flex", alignItems: "stretch", justifyContent: "flex-end" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: hasPdf ? "min(1100px, 98vw)" : "min(520px, 95vw)", height: "100vh", background: "var(--surface, #0f0f1a)", borderLeft: "1px solid rgba(255,255,255,0.08)", display: "flex", flexDirection: "row", overflow: "hidden", animation: "slideInRight 0.25s ease" }}>

        {/* ── Left pane: Source PDF ── */}
        {hasPdf && (
          <div style={{ flex: "0 0 60%", borderRight: "1px solid rgba(255,255,255,0.08)", display: "flex", flexDirection: "column", background: "#0a0a12" }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.07)", display: "flex", alignItems: "center", gap: 8, background: "rgba(0,0,0,0.3)" }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted, #888)", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                📄 {filename}
              </span>
              {pdfUrl && (
                <a href={pdfUrl} download={filename} style={{ fontSize: 11, color: "#6366f1", textDecoration: "none", fontWeight: 600, flexShrink: 0 }}>↓ Download</a>
              )}
            </div>
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
              {pdfLoading && (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, color: "var(--text-muted, #888)" }}>
                  <Loader2 size={28} className="animate-spin" />
                  <span style={{ fontSize: 13 }}>Loading source document…</span>
                </div>
              )}
              {pdfError && (
                <div style={{ textAlign: "center", color: "var(--text-muted, #888)", padding: 32 }}>
                  <div style={{ fontSize: 32, marginBottom: 12 }}>📂</div>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>PDF not available</div>
                  <div style={{ fontSize: 12 }}>This file was processed in an older session and has been cleaned from the server.<br />Re-upload to view it here.</div>
                </div>
              )}
              {pdfUrl && !pdfLoading && (
                <iframe src={pdfUrl} width="100%" height="100%" style={{ border: "none", display: "block" }} title={filename} />
              )}
            </div>
          </div>
        )}

        {/* ── Right pane: Recon report ── */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.07)", display: "flex", alignItems: "center", justifyContent: "space-between", background: statusCfg.bg }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: statusCfg.bg, border: `1px solid ${statusCfg.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <StatusIcon size={20} style={{ color: statusCfg.color }} />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary, #fff)" }}>Audit Review Panel</div>
              <div style={{ fontSize: 11, color: statusCfg.color, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{statusCfg.label}</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted, #888)", padding: 6 }}><X size={20} /></button>
        </div>

        {!hasPdf && (
          <div style={{ padding: "10px 24px", borderBottom: "1px solid rgba(255,255,255,0.06)", fontSize: 12, color: "var(--text-muted, #888)", fontFamily: "monospace", background: "rgba(0,0,0,0.2)" }}>
            {filename}
          </div>
        )}

        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 20 }}>
          {loading && <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-muted, #888)" }}><Loader2 size={18} className="animate-spin" /><span style={{ fontSize: 13 }}>Loading reconciliation report...</span></div>}
          {error && <div style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 10, padding: "12px 16px", fontSize: 13, color: "#fca5a5" }}>{error}</div>}
          {!loading && !report && <div style={{ fontSize: 13, color: "var(--text-muted, #888)", textAlign: "center", paddingTop: 40 }}>No reconciliation report available yet.<br /><span style={{ fontSize: 11 }}>Run extraction to generate an audit report.</span></div>}
          
          {report && (<>
            <div style={{ background: statusCfg.bg, border: `1px solid ${statusCfg.border}`, borderRadius: 12, padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
              <StatusIcon size={28} style={{ color: statusCfg.color, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: statusCfg.color }}>{report.is_reconciled ? "Fully Reconciled" : statusCfg.label}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted, #888)", marginTop: 3 }}>Math path: <strong style={{ color: "var(--text-primary, #fff)" }}>{report.calculation_trace?.math_evaluation?.winning_path ?? "N/A"}</strong> &middot; Confidence: <strong style={{ color: statusCfg.color }}>{((report.overall_confidence || 0) * 100).toFixed(0)}%</strong> &middot; {report.execution_time_ms?.toFixed(0)}ms</div>
              </div>
            </div>

            <section>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted, #888)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}><Scale size={12} /> Math Verification</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {[
                  { label: "Extracted Taxable", value: FMT(report.calculation_trace?.taxable_value), color: "var(--text-primary, #fff)" },
                  { label: "Calculated Taxable", value: FMT(report.calculated_taxable), color: report.variance_taxable > 0.5 ? "#f59e0b" : "#22c55e" },
                  { label: "Extracted Total", value: FMT(report.calculation_trace?.grand_total), color: "var(--text-primary, #fff)" },
                  { label: "Calculated Total", value: FMT(report.calculated_total), color: report.variance_total > 0.5 ? "#f59e0b" : "#22c55e" },
                  { label: "Taxable Variance", value: FMT(report.variance_taxable), color: report.variance_taxable > 0.5 ? "#ef4444" : "#22c55e" },
                  { label: "Total Variance", value: FMT(report.variance_total), color: report.variance_total > 0.5 ? "#ef4444" : "#22c55e" },
                ].map((m) => (
                  <div key={m.label} style={{ background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: "10px 14px" }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted, #888)", fontWeight: 600, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{m.label}</div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: m.color }}>{m.value}</div>
                  </div>
                ))}
              </div>
            </section>

            {report.calculation_trace?.semantic_columns && (
              <section>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted, #888)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}><Zap size={12} /> Column Classification</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {Object.entries(report.calculation_trace.semantic_columns).map(([col, type]) => (
                    <div key={col} style={{ background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.25)", borderRadius: 99, padding: "4px 12px", fontSize: 11, color: "#a5b4fc", fontFamily: "monospace" }}>
                      {col} &rarr; <strong>{type}</strong>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {report.review_context?.items?.length > 0 && (
              <section>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted, #888)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}><AlertTriangle size={12} /> Variance Details</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {report.review_context.items.map((item, i) => (
                    <div key={i} style={{ background: item.severity === "BLOCKER" ? "rgba(239,68,68,0.06)" : "rgba(245,158,11,0.06)", border: `1px solid ${item.severity === "BLOCKER" ? "rgba(239,68,68,0.2)" : "rgba(245,158,11,0.2)"}`, borderRadius: 10, padding: "12px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: item.severity === "BLOCKER" ? "#ef4444" : "#f59e0b", textTransform: "uppercase", letterSpacing: "0.06em", background: item.severity === "BLOCKER" ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)", padding: "2px 8px", borderRadius: 99 }}>{item.severity}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary, #fff)" }}>{item.field_name}</span>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-muted, #888)", lineHeight: 1.5, marginBottom: 6 }}>{item.reason}</div>
                      <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
                        <span>Extracted: <strong style={{ color: "#ef4444" }}>{FMT(item.extracted_value)}</strong></span>
                        <ChevronRight size={12} style={{ color: "var(--text-muted, #888)", flexShrink: 0, alignSelf: "center" }} />
                        <span>Corrected: <strong style={{ color: "#22c55e" }}>{FMT(item.calculated_value)}</strong></span>
                      </div>
                      <div style={{ marginTop: 6, fontSize: 11, color: "#a5b4fc", fontStyle: "italic" }}>Recommendation: {item.recommendation}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {report.is_reconciled && !report.review_context?.items?.length && (
              <div style={{ background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: 10, padding: "16px 20px", display: "flex", alignItems: "center", gap: 12 }}>
                <CheckCircle2 size={22} style={{ color: "#22c55e", flexShrink: 0 }} />
                <div style={{ fontSize: 13, color: "#86efac" }}>All financial fields verified. This invoice is mathematically consistent and ERP-ready.</div>
              </div>
            )}

            {report.failed_fields?.length > 0 && (
              <section>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted, #888)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}><ListChecks size={12} /> Failed Checks</div>
                <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
                  {report.failed_fields.map((f, i) => <li key={i} style={{ fontSize: 12, color: "#fca5a5", lineHeight: 1.5 }}>{f}</li>)}
                </ul>
              </section>
            )}
          </>)}
        </div>

        {!loading && report && !accepted && status !== "ERP_READY" && (
          <div style={{ padding: "16px 24px", borderTop: "1px solid rgba(255,255,255,0.07)", display: "flex", gap: 12, background: "rgba(0,0,0,0.2)" }}>
            <button id={`accept-correction-${taskId}`} onClick={handleAccept} disabled={accepting} style={{ flex: 1, padding: "12px 20px", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", border: "none", borderRadius: 10, color: "#fff", fontSize: 13, fontWeight: 700, cursor: accepting ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: accepting ? 0.7 : 1 }}>
              {accepting ? <Loader2 size={14} className="animate-spin" /> : <BadgeCheck size={14} />}
              Accept Correction Proposal
            </button>
          </div>
        )}

        {accepted && (
          <div style={{ padding: "14px 24px", borderTop: "1px solid rgba(255,255,255,0.07)", background: "rgba(167,139,250,0.08)", display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "#c4b5fd" }}>
            <BadgeCheck size={16} style={{ color: "#a78bfa" }} />
            Correction accepted and marked as <strong style={{ color: "#a78bfa", marginLeft: 4 }}>Human Corrected</strong>
          </div>
        )}
        </div>{/* end right pane */}
      </div>

      <style>{`@keyframes slideInRight { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }`}</style>
    </div>
  );
}
