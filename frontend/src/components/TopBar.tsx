"use client";

import React from "react";
import { usePeriod } from "../utils/PeriodContext";
import { useTenantName } from "../utils/useTenant";
import { MONTH_OPTIONS } from "../utils/periods";

/**
 * Global top bar: client indicator + period switcher only. User identity
 * (email, role) and logout stay in Sidebar's footer, where they already
 * lived - this bar doesn't duplicate them.
 */
export default function TopBar() {
  const tenantName = useTenantName();
  const { period, setPeriod } = usePeriod();

  return (
    <div
      style={{
        height: 56,
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-card)",
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "0 24px",
        flexShrink: 0,
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}
    >
      {/* Client indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.08em",
            color: "var(--text-muted)",
            textTransform: "uppercase",
          }}
        >
          Client
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
          {tenantName ?? "—"}
        </span>
      </div>

      {/* Period switcher */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.08em",
            color: "var(--text-muted)",
            textTransform: "uppercase",
          }}
        >
          Period
        </span>
        <select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          style={{
            padding: "5px 8px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--bg-base)",
            color: "var(--text-primary)",
            fontSize: 13,
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          {MONTH_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
