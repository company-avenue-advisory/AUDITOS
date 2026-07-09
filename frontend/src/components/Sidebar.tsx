"use client";

import React, { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { fetchPreferences, savePreferences } from "../utils/sessionSync";
import {
  LayoutDashboard,
  FileSpreadsheet,
  GitCompareArrows,
  Shield,
  Sparkles,
  Sun,
  Moon,
  FileText,
  LogOut,
  Building2,
  Cloud,
  ClipboardCheck,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ─────────── Navigation Items ─────────── */
const NAV_ITEMS = [
  {
    href: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    description: "Executive overview",
  },
  {
    href: "/invoice-extractor",
    label: "Extractor",
    icon: FileSpreadsheet,
    description: "PDF → GST Ledger",
  },
  {
    href: "/reconciliation",
    label: "Reconciliation",
    icon: GitCompareArrows,
    description: "GSTR-2B matching",
  },
  {
    href: "/sales-period-review",
    label: "Sales Review",
    icon: ClipboardCheck,
    description: "Approve before filing",
  },
  {
    href: "/purchase-gstr2b-review",
    label: "GSTR-2B Review",
    icon: ClipboardCheck,
    description: "Approve before ITC claim",
  },
  {
    href: "/tax-audit/msme",
    label: "MSME Audit",
    icon: Shield,
    description: "43B(h) compliance",
  },
  {
    href: "/document-utilities",
    label: "Doc Utilities",
    icon: FileText,
    description: "Admin file toolbox",
  },
  {
    href: "/google-drive-sync",
    label: "Drive Sync",
    icon: Cloud,
    description: "Auto-sync from Google Drive",
  },
  {
    href: "/firm-settings",
    label: "Firm Settings",
    icon: Building2,
    description: "Team & firm management",
    ownerOnly: true,
  },
];

/* ─────────── Sidebar Component ─────────── */
export default function Sidebar() {
  const pathname = usePathname();
  const [theme, setTheme] = useState("dark");
  const [userEmail, setUserEmail] = useState("");
  const [userRole, setUserRole] = useState("");
  const [firmName, setFirmName] = useState<string | null>(null);

  useEffect(() => {
    const email = localStorage.getItem("user_email") || "";
    const role = localStorage.getItem("user_role") || "";
    setUserEmail(email);
    setUserRole(role);

    // Load theme from preferences API (falls back to localStorage then default)
    fetchPreferences().then((prefs) => {
      const serverTheme = prefs?.theme;
      const localTheme = localStorage.getItem("theme");
      const resolved = serverTheme || localTheme || "dark";
      setTheme(resolved);
      document.documentElement.setAttribute("data-theme", resolved);
      localStorage.setItem("theme", resolved);
    }).catch(() => {
      const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
      setTheme(currentTheme);
    });

    // Fetch tenant name (firm name) to show in sidebar
    const token = localStorage.getItem("token");
    if (token) {
      fetch(`${API_BASE_URL}/api/me/tenant`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((data) => {
          if (data?.tenant?.name) setFirmName(data.tenant.name);
        })
        .catch(() => {});
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
    // Persist to backend so theme follows the user across devices
    savePreferences({ theme: newTheme });
  };

  return (
    <aside
      id="global-sidebar"
      style={{
        width: 240,
        minHeight: "100vh",
        background: "var(--bg-base)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        padding: "0",
        position: "fixed",
        top: 0,
        left: 0,
        zIndex: 100,
        transition: "background 0.3s ease",
      }}
    >
      {/* ── Brand ── */}
      <div
        style={{
          padding: "28px 20px 20px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              background: "var(--accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Shield size={17} style={{ color: "#fff" }} />
          </div>
          <div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 800,
                color: "var(--text-primary)",
                letterSpacing: "-0.03em",
                lineHeight: 1.1,
              }}
            >
              Audit OS
            </div>
            <div
              style={{
                fontSize: 10,
                color: firmName ? "var(--accent)" : "var(--text-muted)",
                fontWeight: firmName ? 600 : 500,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                marginTop: 2,
                maxWidth: 140,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={firmName || "Compliance Platform"}
            >
              {firmName || "Compliance Platform"}
            </div>
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav style={{ flex: 1, padding: "16px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            padding: "4px 8px 8px",
          }}
        >
          Modules
        </div>
        {NAV_ITEMS.filter((item: any) => {
          const role = userRole.toLowerCase();
          if ((item as any).ownerOnly && role !== "owner" && role !== "developer") return false;
          if (role === "developer") return true;
          if (role === "ca" || role === "auditor" || role === "owner") return true;
          if (role === "accountant") return item.href !== "/tax-audit/msme";
          if (role === "client") return item.href === "/" || item.href === "/invoice-extractor";
          return true;
        }).map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              id={`nav-${item.label.toLowerCase().replace(/\s/g, "-")}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 12px",
                borderRadius: "var(--radius-sm)",
                textDecoration: "none",
                transition: "background 0.15s ease, border-color 0.15s ease",
                background: isActive ? "var(--accent-soft)" : "transparent",
                border: isActive
                  ? "1px solid var(--accent-glow)"
                  : "1px solid transparent",
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: isActive
                    ? "var(--accent-soft)"
                    : "var(--bg-card)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 0.15s ease",
                }}
              >
                <Icon
                  size={15}
                  style={{
                    color: isActive ? "var(--accent)" : "var(--text-muted)",
                    transition: "color 0.15s ease",
                  }}
                />
              </div>
              <div>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: isActive ? 600 : 500,
                    color: isActive
                      ? "var(--text-primary)"
                      : "var(--text-secondary)",
                    lineHeight: 1.2,
                  }}
                >
                  {item.label}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: "var(--text-muted)",
                    marginTop: 1,
                  }}
                >
                  {item.description}
                </div>
              </div>
            </Link>
          );
        })}
      </nav>

      {/* ── Footer ── */}
      <div
        style={{
          padding: "16px 20px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {userEmail && (
          <div
            style={{
              padding: "10px 12px",
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "var(--text-primary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={userEmail}
            >
              {userEmail}
            </div>
            <div
              style={{
                fontSize: 9,
                fontWeight: 700,
                color: "var(--accent)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              Role: {userRole}
            </div>
          </div>
        )}

        <button
          onClick={toggleTheme}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "8px 12px",
            color: "var(--text-secondary)",
            fontSize: 12,
            fontWeight: 500,
            cursor: "pointer",
            transition: "all 0.2s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--bg-card-hover)";
            e.currentTarget.style.color = "var(--text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "var(--bg-card)";
            e.currentTarget.style.color = "var(--text-secondary)";
          }}
        >
          {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
          <span>{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>
        </button>

        {userEmail && (
          <button
            onClick={() => {
              localStorage.removeItem("token");
              localStorage.removeItem("user_email");
              localStorage.removeItem("user_role");
              window.location.href = "/login";
            }}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "var(--red-soft)",
              border: "1px solid var(--red)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 12px",
              color: "var(--red)",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--red-soft)";
              e.currentTarget.style.opacity = "0.8";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "var(--red-soft)";
              e.currentTarget.style.opacity = "1";
            }}
          >
            <LogOut size={13} />
            <span>Log Out</span>
          </button>
        )}

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: 10,
            color: "var(--text-muted)",
          }}
        >
          <Sparkles size={10} style={{ color: "var(--accent)" }} />
          <span>Deterministic · GST-Compliant</span>
        </div>
      </div>
    </aside>
  );
}
