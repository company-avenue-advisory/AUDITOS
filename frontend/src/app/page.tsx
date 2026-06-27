"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  FileSpreadsheet,
  AlertTriangle,
  CheckCircle,
  GitCompareArrows,
  Zap,
  Shield,
  TrendingUp,
  ArrowRight,
} from "lucide-react";
import { validateGstItem, type ValidatedItem } from "../utils/gstValidator";

/* ─────────── Config ─────────── */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ─────────── Types ─────────── */
interface DashboardStats {
  totalInvoices: number;
  cleanInvoices: number;
  discrepancies: number;
  accuracy: number;
  urgentItems: ValidatedItem[];
}

/* ─────────── Component ─────────── */
export default function DashboardPage() {
  const [userRole, setUserRole] = useState("");
  const [liveStats, setLiveStats] = useState({
    totalBatches: 0,
    totalFiles: 0,
    averageQualityScore: 1.0,
    totalCostInr: 0.0,
    totalFlags: 0,
    recentFlags: [] as any[],
    recentJobs: [] as any[]
  });
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");

  useEffect(() => {
    setUserRole(localStorage.getItem("user_role") || "");
    // Check backend health
    fetch(`${API_BASE_URL}/api/models`)
      .then((r) => {
        if (r.ok) setBackendStatus("online");
        else setBackendStatus("offline");
      })
      .catch(() => setBackendStatus("offline"));

    // Fetch live observability stats
    fetch(`${API_BASE_URL}/api/observability/stats`)
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error();
      })
      .then((data) => {
        setLiveStats({
          totalBatches: data.total_batches || 0,
          totalFiles: data.total_files || 0,
          averageQualityScore: data.average_quality_score !== undefined ? data.average_quality_score : 1.0,
          totalCostInr: data.total_cost_inr || 0.0,
          totalFlags: data.total_flags || 0,
          recentFlags: data.recent_flags || [],
          recentJobs: data.recent_jobs || []
        });
      })
      .catch((err) => console.error("Failed to load live observability stats", err));
  }, []);

  const statusColor =
    backendStatus === "online"
      ? "#22c55e"
      : backendStatus === "offline"
        ? "#ef4444"
        : "#f59e0b";
  const statusLabel =
    backendStatus === "online"
      ? "Online"
      : backendStatus === "offline"
        ? "Offline"
        : "Checking…";

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
        <header className="animate-fade-up" style={{ paddingBottom: 8 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 24,
            }}
          >
            <div>
              <h1
                style={{
                  fontSize: "clamp(32px, 5vw, 48px)",
                  fontWeight: 800,
                  letterSpacing: "-0.04em",
                  lineHeight: 1.05,
                  margin: 0,
                }}
              >
                <span className="shimmer-text">Audit OS</span>
              </h1>
              <p
                style={{
                  marginTop: 8,
                  color: "var(--text-secondary)",
                  fontSize: 15,
                  fontWeight: 400,
                  lineHeight: 1.6,
                }}
              >
                Executive compliance dashboard — real-time extraction and
                reconciliation status.
              </p>
            </div>

            {/* Backend status */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 16px",
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: statusColor,
                  boxShadow: `0 0 8px ${statusColor}66`,
                }}
              />
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 500,
                  color: statusColor,
                }}
              >
                API: {statusLabel}
              </span>
            </div>
          </div>
        </header>

        {/* ══ OPERATIONAL COUNTERS ══ */}
        <div
          className="animate-fade-up"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 16,
            animationDelay: "0.05s",
          }}
        >
          {[
            {
              label: "Total Invoices",
              value: liveStats.totalFiles,
              icon: FileSpreadsheet,
              color: "var(--accent)",
              bg: "var(--accent-soft)",
            },
            {
              label: "Avg Quality Score",
              value: `${(liveStats.averageQualityScore * 100).toFixed(1)}%`,
              icon: CheckCircle,
              color: liveStats.averageQualityScore >= 0.90 ? "#22c55e" : liveStats.averageQualityScore >= 0.75 ? "#f59e0b" : "#ef4444",
              bg: liveStats.averageQualityScore >= 0.90 ? "var(--green-soft)" : liveStats.averageQualityScore >= 0.75 ? "var(--amber-soft)" : "var(--red-soft)",
            },
            {
              label: "Total Cloud Cost",
              value: `₹ ${liveStats.totalCostInr.toFixed(2)}`,
              icon: TrendingUp,
              color: "#A78BFA",
              bg: "rgba(167, 139, 250, 0.1)",
              hidden: !(userRole.toLowerCase() === "developer" || userRole.toLowerCase() === "owner")
            },
            {
              label: "Active System Flags",
              value: liveStats.totalFlags,
              icon: AlertTriangle,
              color: liveStats.totalFlags > 0 ? "#ef4444" : "#22c55e",
              bg: liveStats.totalFlags > 0 ? "var(--red-soft)" : "var(--green-soft)",
              hidden: !(userRole.toLowerCase() === "developer" || userRole.toLowerCase() === "owner")
            },
          ].filter(card => !card.hidden).map((card) => {
            const Icon = card.icon;
            return (
              <div
                key={card.label}
                className="glass"
                style={{
                  borderRadius: "var(--radius-lg)",
                  padding: "24px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 10,
                    background: card.bg,
                    border: `1px solid ${card.color}33`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Icon size={17} style={{ color: card.color }} />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 28,
                      fontWeight: 800,
                      color: "var(--text-primary)",
                      letterSpacing: "-0.03em",
                      lineHeight: 1,
                    }}
                  >
                    {card.value}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      marginTop: 4,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {card.label}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* ══ QUICK ACTIONS ══ */}
        <div
          className="animate-fade-up"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
            animationDelay: "0.1s",
          }}
        >
          <Link
            href="/invoice-extractor"
            id="goto-extractor"
            style={{
              textDecoration: "none",
            }}
          >
            <div
              className="glass"
              style={{
                borderRadius: "var(--radius-lg)",
                padding: "28px",
                cursor: "pointer",
                transition: "border-color 0.15s ease, transform 0.15s ease",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 14,
                    background:
                      "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))",
                    border: "1px solid rgba(99,102,241,0.3)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Zap
                    size={22}
                    style={{ color: "var(--accent)" }}
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 700,
                      color: "var(--text-primary)",
                      marginBottom: 4,
                    }}
                  >
                    Invoice Extractor
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-muted)",
                    }}
                  >
                    Upload PDFs → AI extraction → Validated Excel
                  </div>
                </div>
              </div>
              <ArrowRight
                size={18}
                style={{ color: "var(--text-muted)" }}
              />
            </div>
          </Link>

          <Link
            href="/reconciliation"
            id="goto-reconciliation"
            style={{
              textDecoration: "none",
            }}
          >
            <div
              className="glass"
              style={{
                borderRadius: "var(--radius-lg)",
                padding: "28px",
                cursor: "pointer",
                transition: "border-color 0.15s ease, transform 0.15s ease",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 14,
                    background:
                      "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(234,88,12,0.2))",
                    border: "1px solid rgba(245,158,11,0.3)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <GitCompareArrows
                    size={22}
                    style={{ color: "var(--amber)" }}
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 700,
                      color: "var(--text-primary)",
                      marginBottom: 4,
                    }}
                  >
                    GSTR-2B Reconciliation
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-muted)",
                    }}
                  >
                    Cross-reference books vs. government records
                  </div>
                </div>
              </div>
              <ArrowRight
                size={18}
                style={{ color: "var(--text-muted)" }}
              />
            </div>
          </Link>
        </div>

        {/* ══ ACTIVE SYSTEM FLAGS / ALERTS ══ */}
        {liveStats.recentFlags.length > 0 && (userRole.toLowerCase() === "developer" || userRole.toLowerCase() === "owner") && (
          <section
            className="glass animate-fade-up"
            style={{
              borderRadius: "var(--radius-xl)",
              overflow: "hidden",
              animationDelay: "0.15s",
              border: "1px solid rgba(239,68,68,0.2)"
            }}
          >
            <div
              style={{
                padding: "20px 24px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                gap: 10,
                background: "rgba(239,68,68,0.02)"
              }}
            >
              <Shield
                size={18}
                style={{ color: "#ef4444" }}
              />
              <span
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.02em",
                }}
              >
                Active System Flags & Alerts
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "#fca5a5",
                  background: "rgba(239,68,68,0.15)",
                  border: "1px solid rgba(239,68,68,0.25)",
                  borderRadius: 99,
                  padding: "2px 10px",
                }}
              >
                {liveStats.totalFlags} flags
              </span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "rgba(0,0,0,0.02)", borderBottom: "1px solid var(--border)" }}>
                    <th style={{ padding: "12px 16px", textAlign: "left", color: "var(--text-muted)", fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Severity</th>
                    <th style={{ padding: "12px 16px", textAlign: "left", color: "var(--text-muted)", fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Flag ID</th>
                    <th style={{ padding: "12px 16px", textAlign: "left", color: "var(--text-muted)", fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Source Document</th>
                    <th style={{ padding: "12px 16px", textAlign: "left", color: "var(--text-muted)", fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Trigger Condition / Details</th>
                    <th style={{ padding: "12px 16px", textAlign: "right", color: "var(--text-muted)", fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {liveStats.recentFlags.map((flag, idx) => (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: "1px solid var(--border)",
                        background: flag.severity === "CRITICAL" ? "rgba(239,68,68,0.015)" : "transparent",
                      }}
                    >
                      <td style={{ padding: "12px 16px" }}>
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 700,
                          background: flag.severity === "CRITICAL" ? "rgba(239,68,68,0.15)" : flag.severity === "HIGH" ? "rgba(245,158,11,0.15)" : "rgba(59,130,246,0.15)",
                          color: flag.severity === "CRITICAL" ? "#ef4444" : flag.severity === "HIGH" ? "#f59e0b" : "#3b82f6"
                        }}>
                          {flag.severity}
                        </span>
                      </td>
                      <td style={{ padding: "12px 16px", fontFamily: "monospace", color: "var(--text-primary)", fontWeight: 500 }}>
                        {flag.flag_id}
                      </td>
                      <td style={{ padding: "12px 16px", color: "var(--text-secondary)" }}>
                        {flag.filename.length > 25 ? flag.filename.slice(0, 23) + "…" : flag.filename}
                      </td>
                      <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                        {flag.detail}
                      </td>
                      <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--text-muted)", fontSize: 11 }}>
                        {new Date(flag.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ══ RECENT UPLOAD RUNS ══ */}
        <section
          className="glass animate-fade-up"
          style={{
            borderRadius: "var(--radius-xl)",
            overflow: "hidden",
            animationDelay: "0.2s"
          }}
        >
          <div
            style={{
              padding: "20px 24px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <FileSpreadsheet
                size={18}
                style={{ color: "var(--accent)" }}
              />
              <span
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.02em",
                }}
              >
                Recent Audit Pipeline Batches
              </span>
            </div>
            <Link href="/invoice-extractor" style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none", fontWeight: 500 }}>
              Upload New Batch →
            </Link>
          </div>
          
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
              <thead>
                <tr style={{ background: "rgba(0,0,0,0.02)", borderBottom: "1px solid var(--border)" }}>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500 }}>Date Started</th>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500 }}>Batch ID</th>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500 }}>Invoices</th>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500 }}>Status</th>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500 }}>Avg Quality Score</th>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500 }}>Flags raised</th>
                  <th style={{ padding: "14px 20px", color: "var(--text-secondary)", fontWeight: 500, textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {liveStats.recentJobs.map((b) => (
                  <tr
                    key={b.id}
                    style={{ borderBottom: "1px solid var(--border)", transition: "background .15s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.01)"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                  >
                    <td style={{ padding: "14px 20px", color: "var(--text-primary)" }}>
                      {new Date(b.created_at).toLocaleString()}
                    </td>
                    <td style={{ padding: "14px 20px", color: "var(--text-secondary)", fontFamily: "monospace", fontSize: 11 }}>
                      {b.id}
                    </td>
                    <td style={{ padding: "14px 20px", color: "var(--text-primary)", fontWeight: 600 }}>
                      {b.total_files} docs
                    </td>
                    <td style={{ padding: "14px 20px" }}>
                      <span style={{
                        padding: "4px 10px",
                        borderRadius: 20,
                        fontSize: 11,
                        fontWeight: 500,
                        background: b.status === "COMPLETED" ? "var(--green-soft)" : (b.status === "FAILED" ? "var(--red-soft)" : "var(--amber-soft)"),
                        color: b.status === "COMPLETED" ? "#34D399" : (b.status === "FAILED" ? "#EF4444" : "#D4A017")
                      }}>
                        {b.status}
                      </span>
                    </td>
                    <td style={{ padding: "14px 20px" }}>
                      {b.average_quality_score !== null && b.average_quality_score !== undefined ? (
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          background: b.average_quality_score >= 0.90 ? "rgba(16,185,129,0.12)" : b.average_quality_score >= 0.75 ? "rgba(234,179,8,0.12)" : "rgba(239,68,68,0.12)",
                          color: b.average_quality_score >= 0.90 ? "#34D399" : b.average_quality_score >= 0.75 ? "#D4A017" : "#EF4444"
                        }}>
                          {(b.average_quality_score * 100).toFixed(1)}%
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: "14px 20px" }}>
                      {b.flags_count > 0 ? (
                        <span style={{
                          color: "#ef4444",
                          fontWeight: 600,
                          background: "var(--red-soft)",
                          padding: "2px 8px",
                          borderRadius: 12
                        }}>
                          ⚠️ {b.flags_count} flags
                        </span>
                      ) : (
                        <span style={{ color: "#22c55e" }}>✓ Clean</span>
                      )}
                    </td>
                    <td style={{ padding: "14px 20px", textAlign: "right" }}>
                      <Link
                        href={`/invoice-extractor?batchId=${b.id}`}
                        style={{
                          textDecoration: "none"
                        }}
                      >
                        <button
                          className="nav-pill"
                          style={{
                            borderColor: "var(--accent)",
                            color: "var(--accent)",
                            background: "rgba(26,107,255,0.05)",
                            fontSize: 12,
                            padding: "6px 14px",
                            borderRadius: 6
                          }}
                        >
                          View Ledger →
                        </button>
                      </Link>
                    </td>
                  </tr>
                ))}
                {liveStats.recentJobs.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ padding: "60px 20px", textAlign: "center", color: "var(--text-secondary)" }}>
                      No extraction history found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
