"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeftRight, Server, RefreshCw, CheckCircle, AlertCircle,
  AlertTriangle, Loader2, Wifi, WifiOff, FileText, Send,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TallyCompany {
  name: string;
  formal_name: string;
}

interface Batch {
  id: string;
  created_at: string;
  total_files: number;
  status: string;
}

interface TallyPushResultRow {
  success: boolean;
  invoice_no?: string;
  file_name?: string;
  voucher_type?: string;
  error?: string;
}

interface TallyPushResult {
  succeeded?: number;
  skipped_already_pushed?: number;
  failed?: number;
  results?: TallyPushResultRow[];
  error?: string;
}

// ── Style helpers (match existing simple-page convention) ──────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)",
  background: "var(--bg-card)",
  color: "var(--text-primary)",
  fontSize: 13,
  outline: "none",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  color: "var(--text-secondary)",
  marginBottom: 6,
};

function SectionCard({ title, icon, subtitle, disabled, children }: {
  title: string; icon: React.ReactNode; subtitle?: string; disabled?: boolean; children: React.ReactNode;
}) {
  return (
    <div
      className="glass"
      style={{
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
        opacity: disabled ? 0.5 : 1,
        pointerEvents: disabled ? "none" : "auto",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
        {icon}
        <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>{title}</h2>
        {subtitle && <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>{subtitle}</span>}
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

function TallySyncInner() {
  const searchParams = useSearchParams();
  const initialBatchId = searchParams.get("batchId");

  // Connection state (ported from invoice-extractor's Tally modal)
  const [tallyHost, setTallyHost] = useState("");
  const [tallyPort, setTallyPort] = useState("9000");
  const [tallyCompany, setTallyCompany] = useState("");
  const [isPushingToTally, setIsPushingToTally] = useState(false);
  const [tallyPushResult, setTallyPushResult] = useState<TallyPushResult | null>(null);
  const [tallyCompanies, setTallyCompanies] = useState<TallyCompany[]>([]);
  const [isLoadingTallyCompanies, setIsLoadingTallyCompanies] = useState(false);
  const [tallyCompaniesError, setTallyCompaniesError] = useState<string | null>(null);

  // Batch picker state
  const [batches, setBatches] = useState<Batch[]>([]);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(initialBatchId);

  // ── API calls — character-identical contract to the old invoice-extractor modal ──

  const fetchTallyCompanies = async (host: string, port: string) => {
    if (!host.trim()) return;
    setIsLoadingTallyCompanies(true);
    setTallyCompaniesError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/tally/companies?host=${encodeURIComponent(host.trim())}&port=${parseInt(port, 10) || 9000}`,
        { headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Could not reach TallyPrime");
      setTallyCompanies(data.companies || []);
      if (!data.companies?.length) {
        setTallyCompaniesError("No companies open in Tally right now — open one, then refresh.");
      }
    } catch (e: any) {
      setTallyCompanies([]);
      setTallyCompaniesError(e.message || "Could not reach TallyPrime");
    } finally {
      setIsLoadingTallyCompanies(false);
    }
  };

  const handlePushToTally = async () => {
    if (!selectedBatchId) {
      alert("Select a batch to push.");
      return;
    }
    if (!tallyHost.trim() || !tallyCompany.trim()) {
      alert("Enter both the TallyPrime host/IP and the company name.");
      return;
    }
    setIsPushingToTally(true);
    setTallyPushResult(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/tally/push/${selectedBatchId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({
          host: tallyHost.trim(),
          port: parseInt(tallyPort, 10) || 9000,
          company: tallyCompany.trim(),
          type: "both",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Push to Tally failed");
      }
      setTallyPushResult(data);
    } catch (e: any) {
      setTallyPushResult({ error: e.message || "Push to Tally failed" });
    } finally {
      setIsPushingToTally(false);
    }
  };

  // ── Mount effects ────────────────────────────────────────────────────────────

  // Load recent batches for the picker (existing /api/jobs endpoint, newest-first)
  useEffect(() => {
    const loadBatches = async () => {
      setIsLoadingBatches(true);
      try {
        const res = await fetch(`${API_BASE_URL}/api/jobs`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        });
        if (res.ok) {
          const data = await res.json();
          setBatches(data || []);
        }
      } catch (e) {
        console.error("Failed to fetch batches", e);
      } finally {
        setIsLoadingBatches(false);
      }
    };
    loadBatches();
  }, []);

  // Prefill saved Tally config, same tolerant try/catch as the old openTallyModal
  useEffect(() => {
    let cancelled = false;
    const initTallyConfig = async () => {
      let host = tallyHost;
      let port = tallyPort;
      try {
        const res = await fetch(`${API_BASE_URL}/api/tally/config`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        });
        if (res.ok) {
          const data = await res.json();
          if (data.configured && data.config) {
            host = data.config.host || "";
            port = String(data.config.port || 9000);
            if (!cancelled) {
              setTallyHost(host);
              setTallyPort(port);
              setTallyCompany(data.config.company || "");
            }
          }
        }
      } catch {
        // No saved config yet, or fetch failed — leave fields blank for manual entry.
      }
      if (host.trim() && !cancelled) {
        fetchTallyCompanies(host, port);
      }
    };
    initTallyConfig();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isConnected = !!tallyHost.trim();
  const canPush = !!tallyHost.trim() && !!tallyCompany.trim() && !!selectedBatchId;
  const selectedBatch = batches.find((b) => b.id === selectedBatchId) || null;

  const resetForAnotherBatch = () => {
    setTallyPushResult(null);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ flex: 1, padding: "32px 40px", maxWidth: 1100 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <ArrowLeftRight size={20} style={{ color: "var(--accent)" }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Tally Sync</h1>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: isConnected ? "var(--agent)" : "var(--text-muted)" }}>
          {isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {isConnected ? "Host configured" : "Not configured"}
        </span>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>
        Pushes only items marked <strong>ERP_READY</strong> (passed reconciliation review) as vouchers to TallyPrime over your LAN.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

        {/* ── Connection ───────────────────────────────────────────────────── */}
        <SectionCard
          title="Connection"
          icon={<Server size={16} style={{ color: "var(--accent)" }} />}
        >
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            <div>
              <label style={labelStyle}>TallyPrime Host / IP</label>
              <input
                type="text"
                value={tallyHost}
                onChange={(e) => setTallyHost(e.target.value)}
                placeholder="192.168.1.100"
                disabled={isPushingToTally}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Port</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  type="text"
                  value={tallyPort}
                  onChange={(e) => setTallyPort(e.target.value)}
                  placeholder="9000"
                  disabled={isPushingToTally}
                  style={{ ...inputStyle, flex: 1 }}
                />
                <button
                  className="btn-ghost"
                  disabled={isPushingToTally || isLoadingTallyCompanies || !tallyHost.trim()}
                  onClick={() => fetchTallyCompanies(tallyHost, tallyPort)}
                  style={{ padding: "8px 14px", fontSize: 12, whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6, border: "1px solid var(--border)" }}
                >
                  {isLoadingTallyCompanies ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                  {isLoadingTallyCompanies ? "Finding…" : "Find companies"}
                </button>
              </div>
            </div>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={labelStyle}>Tally Company</label>
              {tallyCompanies.length > 0 ? (
                <select
                  value={tallyCompany}
                  onChange={(e) => setTallyCompany(e.target.value)}
                  disabled={isPushingToTally}
                  style={inputStyle}
                >
                  {!tallyCompanies.some((c) => c.name === tallyCompany) && tallyCompany && (
                    <option value={tallyCompany}>{tallyCompany}</option>
                  )}
                  {tallyCompanies.map((c) => (
                    <option key={c.name} value={c.name}>{c.formal_name || c.name}</option>
                  ))}
                </select>
              ) : (
                <>
                  <input
                    type="text"
                    value={tallyCompany}
                    onChange={(e) => setTallyCompany(e.target.value)}
                    placeholder="Your Company Name"
                    disabled={isPushingToTally}
                    style={inputStyle}
                  />
                  {tallyCompaniesError && (
                    <p style={{ marginTop: 6, fontSize: 12, color: "var(--text-muted)" }}>
                      {tallyCompaniesError}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        </SectionCard>

        {/* ── Batch picker ─────────────────────────────────────────────────── */}
        <SectionCard
          title="Batch"
          icon={<FileText size={16} style={{ color: "var(--accent)" }} />}
          subtitle={isLoadingBatches ? "Loading…" : `${batches.length} recent`}
        >
          {isLoadingBatches ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "24px 0", textAlign: "center" }}>Loading batches…</div>
          ) : batches.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
              No extraction batches found — run one from Invoice Extractor first.
            </div>
          ) : (
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", overflow: "hidden" }}>
              {batches.map((b, i) => {
                const isSelected = b.id === selectedBatchId;
                return (
                  <div
                    key={b.id}
                    onClick={() => setSelectedBatchId(b.id)}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 14px", cursor: "pointer",
                      background: isSelected ? "var(--accent-soft)" : "var(--bg-card)",
                      borderLeft: isSelected ? "3px solid var(--accent)" : "3px solid transparent",
                      borderBottom: i < batches.length - 1 ? "1px solid var(--border)" : "none",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 12 }}>
                      <span style={{ color: "var(--text-secondary)", minWidth: 150 }}>{new Date(b.created_at).toLocaleString()}</span>
                      <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{b.id.substring(0, 8)}…</span>
                      <span style={{ color: "var(--text-primary)" }}>{b.total_files} docs</span>
                      <span
                        style={{
                          padding: "3px 9px", borderRadius: 20, fontSize: 11, fontWeight: 500,
                          background: b.status === "COMPLETED" ? "var(--green-soft)" : (b.status === "FAILED" ? "var(--red-soft)" : "var(--accent-soft)"),
                          color: b.status === "COMPLETED" ? "var(--green)" : (b.status === "FAILED" ? "var(--red)" : "var(--accent)"),
                        }}
                      >
                        {b.status}
                      </span>
                    </div>
                    {isSelected && <CheckCircle size={16} style={{ color: "var(--accent)" }} />}
                  </div>
                );
              })}
            </div>
          )}
        </SectionCard>

        {/* ── Push action ──────────────────────────────────────────────────── */}
        {!tallyPushResult && (
          <SectionCard
            title="Push"
            icon={<Send size={16} style={{ color: "var(--accent)" }} />}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ fontSize: 13, color: "var(--text-secondary)", background: "var(--agent-soft)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 14px" }}>
                {canPush ? (
                  <>
                    About to push <strong style={{ color: "var(--text-primary)" }}>batch {selectedBatchId?.substring(0, 8)}…</strong> to{" "}
                    <strong style={{ color: "var(--text-primary)" }}>{tallyCompany}</strong> at{" "}
                    <strong style={{ color: "var(--text-primary)" }}>{tallyHost}:{tallyPort || "9000"}</strong>.
                  </>
                ) : (
                  "Fill in the host, company, and select a batch above to enable the push."
                )}
              </div>
              <button
                className="btn-primary"
                disabled={!canPush || isPushingToTally}
                onClick={handlePushToTally}
                style={{ alignSelf: "flex-start", padding: "10px 20px", display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}
              >
                {isPushingToTally ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                {isPushingToTally ? "Pushing…" : "Push Now"}
              </button>
            </div>
          </SectionCard>
        )}

        {/* ── Results ──────────────────────────────────────────────────────── */}
        {tallyPushResult && (
          <SectionCard
            title="Results"
            icon={<CheckCircle size={16} style={{ color: "var(--accent)" }} />}
          >
            {tallyPushResult.error ? (
              <div style={{ display: "flex", gap: 8, padding: 12, background: "var(--red-soft)", borderRadius: "var(--radius-sm)", fontSize: 13, color: "var(--red)", marginBottom: 16 }}>
                <AlertTriangle size={14} style={{ marginTop: 2, flexShrink: 0 }} />
                {tallyPushResult.error}
              </div>
            ) : (
              <>
                <div style={{ fontSize: 14, marginBottom: 12, color: "var(--text-primary)" }}>
                  <strong>{tallyPushResult.succeeded}</strong> pushed ·{" "}
                  <strong>{tallyPushResult.skipped_already_pushed ?? 0}</strong> already-pushed (skipped) ·{" "}
                  <strong style={{ color: (tallyPushResult.failed ?? 0) > 0 ? "var(--red)" : "inherit" }}>{tallyPushResult.failed}</strong> failed
                </div>
                {tallyPushResult.results?.filter((r) => !r.success).length ? (
                  <div style={{ maxHeight: 200, overflowY: "auto", marginBottom: 16 }}>
                    {tallyPushResult.results
                      .filter((r) => !r.success)
                      .map((r, i) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6, paddingLeft: 8, borderLeft: "2px solid var(--red)" }}>
                          <strong>{r.invoice_no || r.file_name}</strong> ({r.voucher_type}): {r.error}
                        </div>
                      ))}
                  </div>
                ) : null}
              </>
            )}
            <button
              className="btn-ghost"
              onClick={resetForAnotherBatch}
              style={{ padding: "8px 16px", fontSize: 13, display: "flex", alignItems: "center", gap: 6, border: "1px solid var(--border)" }}
            >
              <RefreshCw size={13} />
              Push another batch
            </button>
          </SectionCard>
        )}
      </div>
    </div>
  );
}

export default function TallySyncPage() {
  return (
    <Suspense
      fallback={
        <div style={{ flex: 1, padding: "32px 40px", color: "var(--text-muted)", fontSize: 13 }}>
          Loading Tally Sync…
        </div>
      }
    >
      <TallySyncInner />
    </Suspense>
  );
}
