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
  const [stats, setStats] = useState<DashboardStats>({
    totalInvoices: 0,
    cleanInvoices: 0,
    discrepancies: 0,
    accuracy: 100,
    urgentItems: [],
  });
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");

  useEffect(() => {
    // Check backend health
    fetch(`${API_BASE_URL}/api/models`)
      .then((r) => {
        if (r.ok) setBackendStatus("online");
        else setBackendStatus("offline");
      })
      .catch(() => setBackendStatus("offline"));

    // Load any cached items from sessionStorage
    try {
      const cached = sessionStorage.getItem("audit_os_items");
      if (cached) {
        const items: ValidatedItem[] = JSON.parse(cached);
        const validated = items.map((item) => ({
          ...item,
          errors: validateGstItem(item),
        }));
        const discrepancies = validated.filter(
          (i) => i.errors && i.errors.length > 0
        );
        setStats({
          totalInvoices: validated.length,
          cleanInvoices: validated.length - discrepancies.length,
          discrepancies: discrepancies.length,
          accuracy:
            validated.length > 0
              ? Math.round(
                  ((validated.length - discrepancies.length) /
                    validated.length) *
                    100
                )
              : 100,
          urgentItems: discrepancies.slice(0, 10),
        });
      }
    } catch {
      // No cached data
    }
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
              value: stats.totalInvoices,
              icon: FileSpreadsheet,
              color: "var(--accent)",
              bg: "var(--accent-soft)",
            },
            {
              label: "Clean (No Errors)",
              value: stats.cleanInvoices,
              icon: CheckCircle,
              color: "#22c55e",
              bg: "var(--green-soft)",
            },
            {
              label: "Active Discrepancies",
              value: stats.discrepancies,
              icon: AlertTriangle,
              color: "#ef4444",
              bg: "var(--red-soft)",
            },
            {
              label: "Accuracy Rate",
              value: `${stats.accuracy}%`,
              icon: TrendingUp,
              color:
                stats.accuracy >= 90
                  ? "#22c55e"
                  : stats.accuracy >= 70
                    ? "#f59e0b"
                    : "#ef4444",
              bg:
                stats.accuracy >= 90
                  ? "var(--green-soft)"
                  : stats.accuracy >= 70
                    ? "var(--amber-soft)"
                    : "var(--red-soft)",
            },
          ].map((card) => {
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

        {/* ══ URGENT REVIEW GRID ══ */}
        {stats.urgentItems.length > 0 && (
          <section
            className="glass animate-fade-up"
            style={{
              borderRadius: "var(--radius-xl)",
              overflow: "hidden",
              animationDelay: "0.15s",
            }}
          >
            <div
              style={{
                padding: "24px 28px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <Shield
                size={18}
                style={{ color: "var(--red)" }}
              />
              <span
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.02em",
                }}
              >
                Urgent Review Required
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "#fca5a5",
                  background: "var(--red-soft)",
                  border: "1px solid rgba(239,68,68,0.25)",
                  borderRadius: 99,
                  padding: "2px 10px",
                }}
              >
                {stats.urgentItems.length} items
              </span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 12,
                }}
              >
                <thead>
                  <tr
                    style={{
                      background: "rgba(239,68,68,0.04)",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    {["Invoice", "GSTIN", "Party", "Total", "Issues"].map(
                      (h) => (
                        <th
                          key={h}
                          style={{
                            padding: "10px 12px",
                            textAlign: "left",
                            color: "var(--text-muted)",
                            fontWeight: 600,
                            fontSize: 10,
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                          }}
                        >
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {stats.urgentItems.map((item, idx) => (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: "1px solid var(--border)",
                        background: "rgba(239,68,68,0.02)",
                      }}
                    >
                      <td
                        style={{
                          padding: "10px 12px",
                          color: "var(--text-primary)",
                          fontWeight: 500,
                        }}
                      >
                        {item.supplier_inv || "—"}
                      </td>
                      <td
                        style={{
                          padding: "10px 12px",
                          fontFamily: "monospace",
                          color: "var(--text-secondary)",
                          fontSize: 11,
                        }}
                      >
                        {item.gst_no || "—"}
                      </td>
                      <td
                        style={{
                          padding: "10px 12px",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {item.party_ac_name || "—"}
                      </td>
                      <td
                        style={{
                          padding: "10px 12px",
                          color: "var(--text-primary)",
                          fontFamily: "monospace",
                          textAlign: "right",
                        }}
                      >
                        ₹{(item.total_amount || 0).toFixed(2)}
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        {item.errors?.map((err, i) => (
                          <div
                            key={i}
                            style={{
                              fontSize: 11,
                              color: "#fca5a5",
                              marginBottom: 2,
                              display: "flex",
                              gap: 4,
                              alignItems: "flex-start",
                            }}
                          >
                            <span
                              style={{
                                color: "var(--red)",
                                flexShrink: 0,
                              }}
                            >
                              ·
                            </span>
                            {err}
                          </div>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ══ EMPTY STATE ══ */}
        {stats.totalInvoices === 0 && (
          <div
            className="glass animate-fade-up"
            style={{
              borderRadius: "var(--radius-xl)",
              padding: "48px 32px",
              textAlign: "center",
              animationDelay: "0.15s",
            }}
          >
            <FileSpreadsheet
              size={40}
              style={{
                color: "var(--text-muted)",
                margin: "0 auto 16px",
                display: "block",
                opacity: 0.5,
              }}
            />
            <div
              style={{
                fontSize: 16,
                fontWeight: 600,
                color: "var(--text-secondary)",
                marginBottom: 8,
              }}
            >
              No invoices processed yet
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-muted)",
                maxWidth: 400,
                margin: "0 auto",
                lineHeight: 1.6,
              }}
            >
              Navigate to the{" "}
              <Link
                href="/invoice-extractor"
                style={{
                  color: "var(--accent)",
                  textDecoration: "none",
                  fontWeight: 600,
                }}
              >
                Invoice Extractor
              </Link>{" "}
              to upload PDFs and start the audit pipeline.
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
