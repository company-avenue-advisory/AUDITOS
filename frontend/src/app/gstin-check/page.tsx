"use client";

import React, { useState } from "react";
import { ShieldCheck, Search, Loader2, AlertCircle } from "lucide-react";
import { apiRequest } from "@/utils/api";
import StatusBadge from "../../components/ui/StatusBadge";

interface GstinResult {
  gstin: string;
  status: string | null;
  state_code: string | null;
  taxpayer_type: string | null;
  legal_name: string | null;
  status_change_date: string | null;
  as_of_date?: string;
  b2b_status?: "active" | "inactive" | "needs_review";
}

const B2B_STATUS_COPY: Record<string, { label: string; note: string }> = {
  active: { label: "B2B", note: "Registration was active as of the invoice date." },
  inactive: { label: "B2C", note: "Registration was already cancelled/suspended on or before the invoice date - treat as B2C." },
  needs_review: { label: "Needs review", note: "Status changed, but the change date is unknown - a human must confirm before filing this as B2B or B2C." },
};

export default function GstinCheckPage() {
  const [gstin, setGstin] = useState("");
  const [asOfDate, setAsOfDate] = useState(""); // DD-MM-YYYY
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<GstinResult | null>(null);

  const card: React.CSSProperties = {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    padding: "24px 28px",
    marginBottom: 24,
  };
  const input: React.CSSProperties = {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "10px 14px",
    color: "var(--text-primary)",
    fontSize: 14,
    width: "100%",
    outline: "none",
  };
  const label: React.CSSProperties = {
    display: "block", fontSize: 12, fontWeight: 600,
    color: "var(--text-secondary)", marginBottom: 6,
  };

  async function handleCheck() {
    setError("");
    setResult(null);
    const clean = gstin.trim().toUpperCase();
    if (clean.length !== 15) {
      setError("Enter a 15-character GSTIN.");
      return;
    }
    setLoading(true);
    try {
      const qs = asOfDate.trim() ? `?as_of_date=${encodeURIComponent(asOfDate.trim())}` : "";
      const res = await apiRequest(`/api/gstin/${clean}/verify${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "GSTIN verification failed.");
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Network error.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: "0 auto", padding: "40px 24px", color: "var(--text-primary)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 32 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12, background: "var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <ShieldCheck size={22} color="#fff" />
        </div>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>GSTIN Check</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0 }}>
            Registry lookup, with B2B/B2C resolved as of a specific invoice date
          </p>
        </div>
      </div>

      <div style={card}>
        <div style={{ marginBottom: 16 }}>
          <label style={label}>GSTIN</label>
          <input
            style={input}
            value={gstin}
            onChange={(e) => setGstin(e.target.value)}
            placeholder="e.g. 27AADCO0061H1ZQ"
            maxLength={15}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={label}>Invoice date (optional, DD-MM-YYYY)</label>
          <input
            style={input}
            value={asOfDate}
            onChange={(e) => setAsOfDate(e.target.value)}
            placeholder="Leave blank for the registry's current live status"
          />
        </div>
        <button
          onClick={handleCheck}
          disabled={loading || !gstin.trim()}
          style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "10px 18px", borderRadius: 8, fontWeight: 600, fontSize: 13,
            background: "var(--accent)", color: "#fff", border: "none",
            cursor: loading || !gstin.trim() ? "not-allowed" : "pointer",
            opacity: loading || !gstin.trim() ? 0.6 : 1,
          }}
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
          Check GSTIN
        </button>

        {error && (
          <div style={{
            marginTop: 16, display: "flex", alignItems: "center", gap: 8,
            color: "var(--red)", fontSize: 13,
          }}>
            <AlertCircle size={16} />
            {error}
          </div>
        )}
      </div>

      {result && (
        <div style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)" }}>{result.gstin}</span>
            <StatusBadge status={result.status || "unknown"} />
          </div>
          <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 16px", fontSize: 13, margin: 0 }}>
            <dt style={{ color: "var(--text-secondary)" }}>Legal name</dt>
            <dd style={{ margin: 0 }}>{result.legal_name || "-"}</dd>
            <dt style={{ color: "var(--text-secondary)" }}>Registered state</dt>
            <dd style={{ margin: 0 }}>{result.state_code || "-"}</dd>
            <dt style={{ color: "var(--text-secondary)" }}>Taxpayer type</dt>
            <dd style={{ margin: 0 }}>{result.taxpayer_type || "-"}</dd>
            <dt style={{ color: "var(--text-secondary)" }}>Status changed on</dt>
            <dd style={{ margin: 0 }}>{result.status_change_date || "-"}</dd>
          </dl>

          {result.b2b_status && (
            <div style={{
              marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--border)",
              display: "flex", flexDirection: "column", gap: 6,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  As of {result.as_of_date}:
                </span>
                <StatusBadge status={result.b2b_status} />
              </div>
              <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>
                {B2B_STATUS_COPY[result.b2b_status]?.note}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
