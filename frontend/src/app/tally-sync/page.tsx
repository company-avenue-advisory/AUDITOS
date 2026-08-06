"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Link2, Wifi, WifiOff, KeyRound, Copy, CheckCircle, AlertCircle,
  Loader, ShieldOff, Clock, Terminal, ArrowRight,
} from "lucide-react";
import { apiRequest } from "@/utils/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RelayAgent {
  id: string;
  name: string | null;
  paired_at: string;
  last_seen_at: string | null;
}

interface RelayStatus {
  paired: boolean;
  online: boolean;
  agent: RelayAgent | null;
}

interface PairingCode {
  code: string;
  expires_at: string;
}

// ── Shared styling (matches google-drive-sync/page.tsx's pattern) ──────────────

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

function SectionCard({ title, icon, subtitle, children }: {
  title: string; icon: React.ReactNode; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <div className="glass" style={{ borderRadius: "var(--radius-lg)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
        {icon}
        <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>{title}</h2>
        {subtitle && <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>{subtitle}</span>}
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

// Backend timestamps (models.py DateTime columns via datetime.utcnow()) are
// naive UTC — isoformat() omits the "Z"/offset, so new Date() would parse
// them as local time and misjudge every diff by the browser's UTC offset
// (confirmed live: a fresh pairing code showed as already-expired in IST).
// Normalize to an explicit UTC string before parsing.
function parseUtc(iso: string): Date {
  return new Date(/[Z+-]\d{2}:?\d{2}$|Z$/.test(iso) ? iso : `${iso}Z`);
}

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.floor((Date.now() - parseUtc(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function TallySyncPage() {
  const [status, setStatus] = useState<RelayStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [copied, setCopied] = useState(false);

  const [revoking, setRevoking] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await apiRequest("/api/tally/relay/status");
      if (res.ok) {
        const data: RelayStatus = await res.json();
        setStatus(data);
        // Once an agent is paired and comes online, stop showing a stale
        // pairing code — the code has served its purpose.
        if (data.online) setPairing(null);
      }
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    pollRef.current = setInterval(loadStatus, 10_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadStatus]);

  // Countdown for the pairing code's 10-minute validity window.
  useEffect(() => {
    if (!pairing) return;
    const tick = () => {
      const secs = Math.max(0, Math.floor((parseUtc(pairing.expires_at).getTime() - Date.now()) / 1000));
      setRemainingSeconds(secs);
      if (secs === 0) setPairing(null);
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [pairing]);

  const generateCode = async () => {
    setPairingLoading(true);
    setPairingError(null);
    try {
      const res = await apiRequest("/api/tally/relay/pairing-code", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to generate a pairing code.");
      setPairing(data);
    } catch (e: any) {
      setPairingError(e.message);
    } finally {
      setPairingLoading(false);
    }
  };

  const revokeAgent = async () => {
    if (!status?.agent) return;
    if (!confirm(`Revoke "${status.agent.name || "this agent"}"? It will stop being able to relay pushes until re-paired.`)) return;
    setRevoking(true);
    try {
      const res = await apiRequest(`/api/tally/relay/${status.agent.id}/revoke`, { method: "POST" });
      if (res.ok) loadStatus();
    } finally {
      setRevoking(false);
    }
  };

  const pairCommand = pairing
    ? `python tally_relay_agent.py --pair ${pairing.code} --backend-url ${API_BASE_URL}`
    : "";

  const copyCommand = () => {
    if (!pairCommand) return;
    navigator.clipboard.writeText(pairCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  const connected = !!status?.online;

  return (
    <div style={{ flex: 1, padding: "32px 40px", maxWidth: 1100 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <Link2 size={20} style={{ color: "var(--accent)" }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Tally Sync</h1>
        {!statusLoading && (
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: connected ? "var(--green)" : "var(--text-muted)" }}>
            {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
            {connected ? "Local agent connected" : status?.paired ? "Local agent paired, offline" : "No local agent"}
          </span>
        )}
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>
        Lets AuditOS push approved vouchers into a firm&apos;s on-prem TallyPrime without any inbound
        firewall or IP configuration — the agent only makes outbound connections, same pattern as
        Zoom/ngrok/TeamViewer relays.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

        {/* ── Agent status ─────────────────────────────────────────────────── */}
        <SectionCard
          title="Local Bridge Agent"
          icon={<Terminal size={16} style={{ color: "var(--accent)" }} />}
          subtitle={status?.agent?.paired_at ? `Paired ${parseUtc(status.agent.paired_at).toLocaleDateString()}` : undefined}
        >
          {statusLoading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "12px 0" }}>Loading…</div>
          ) : status?.paired && status.agent ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", padding: 16, marginBottom: 16 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 600 }}>{status.agent.name || "Unnamed agent"}</span>
                    <span style={{
                      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: "var(--radius-sm)",
                      color: connected ? "var(--green)" : "var(--amber)",
                      background: connected ? "var(--green-soft)" : "var(--amber-soft)",
                    }}>
                      {connected ? "Online" : "Offline"}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-muted)" }}>
                    <Clock size={12} />
                    Last seen {timeAgo(status.agent.last_seen_at)}
                  </div>
                </div>
                <button
                  className="dl-btn secondary"
                  onClick={revokeAgent}
                  disabled={revoking}
                  style={{ padding: "8px 14px", fontSize: 12, display: "flex", alignItems: "center", gap: 6, color: "var(--red)" }}
                >
                  <ShieldOff size={13} /> {revoking ? "Revoking…" : "Revoke"}
                </button>
              </div>
              {!connected && (
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Offline for more than 2 minutes — pushes will fall back to a direct LAN connection until
                  the agent (<code>python tally_relay_agent.py</code>) is running again on the accountant&apos;s machine.
                </p>
              )}
            </div>
          ) : (
            <div>
              <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 0 }}>
                No local agent paired yet. Without one, pushes only work when AuditOS&apos;s backend and
                TallyPrime are on the same LAN — set up an agent to push from anywhere.
              </p>

              {!pairing ? (
                <>
                  <button
                    className="btn-primary"
                    onClick={generateCode}
                    disabled={pairingLoading}
                    style={{ padding: "10px 20px", display: "flex", alignItems: "center", gap: 8, fontSize: 13, border: "none" }}
                  >
                    {pairingLoading ? <Loader size={14} className="animate-spin" /> : <KeyRound size={14} />}
                    {pairingLoading ? "Generating…" : "Generate pairing code"}
                  </button>
                  {pairingError && (
                    <p style={{ marginTop: 8, fontSize: 13, color: "var(--red)", display: "flex", alignItems: "center", gap: 6 }}>
                      <AlertCircle size={14} /> {pairingError}
                    </p>
                  )}
                </>
              ) : (
                <div style={{ background: "var(--bg-card)", borderRadius: "var(--radius-sm)", padding: 20 }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 4 }}>
                    <span style={{ fontSize: 32, fontWeight: 800, fontFamily: "var(--font-mono)", letterSpacing: "0.1em", color: "var(--accent)" }}>
                      {pairing.code}
                    </span>
                    <span style={{ fontSize: 12, color: remainingSeconds < 60 ? "var(--red)" : "var(--text-muted)" }}>
                      expires in {Math.floor(remainingSeconds / 60)}:{String(remainingSeconds % 60).padStart(2, "0")}
                    </span>
                  </div>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 0, marginBottom: 16 }}>
                    On the accountant&apos;s machine (same network as TallyPrime), with <code>tally_relay_agent.py</code> and{" "}
                    <code>tally_connector.py</code> from <code>backend/tools/</code> copied to a folder, run:
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#0c0c14", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 12px" }}>
                    <code style={{ fontSize: 12, color: "var(--text-primary)", fontFamily: "var(--font-mono)", flex: 1, overflowX: "auto", whiteSpace: "nowrap" }}>
                      {pairCommand}
                    </code>
                    <button
                      onClick={copyCommand}
                      style={{ background: "none", border: "none", cursor: "pointer", color: copied ? "var(--green)" : "var(--text-muted)", flexShrink: 0 }}
                      title="Copy command"
                    >
                      {copied ? <CheckCircle size={16} /> : <Copy size={16} />}
                    </button>
                  </div>
                  <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 12, marginBottom: 0 }}>
                    This page checks every 10s and will show &quot;Online&quot; automatically once the agent
                    pairs and starts polling — no need to refresh.
                  </p>
                </div>
              )}
            </div>
          )}
        </SectionCard>

        {/* ── Fallback / direct mode note ─────────────────────────────────── */}
        <SectionCard
          title="Direct LAN Connection"
          icon={<ArrowRight size={16} style={{ color: "var(--accent)" }} />}
        >
          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0 }}>
            Without an online agent, <strong>Push to Tally</strong> (in the Invoice Extractor&apos;s export
            step) still works whenever AuditOS&apos;s backend can reach TallyPrime directly — the same
            host/port/company connection used before this agent existed. That path is unchanged and needs
            no setup here.
          </p>
        </SectionCard>
      </div>
    </div>
  );
}
