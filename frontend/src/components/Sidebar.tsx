"use client";

import React, { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  FileSpreadsheet,
  GitCompareArrows,
  Shield,
  Sparkles,
  Sun,
  Moon,
  FileText,
} from "lucide-react";

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
    description: "PDF → Line items",
  },
  {
    href: "/reconciliation",
    label: "Reconciliation",
    icon: GitCompareArrows,
    description: "GSTR-2B matching",
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
];

/* ─────────── Sidebar Component ─────────── */
export default function Sidebar() {
  const pathname = usePathname();
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    setTheme(currentTheme);
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
  };

  return (
    <aside
      id="global-sidebar"
      style={{
        width: 240,
        minHeight: "100vh",
        background: theme === "light" ? "rgba(250,250,250,0.97)" : "rgba(6,6,10,0.97)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        padding: "0",
        position: "fixed",
        top: 0,
        left: 0,
        zIndex: 100,
        backdropFilter: "blur(24px) saturate(180%)",
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
              background: "linear-gradient(135deg, #6366f1, #818cf8)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 16px rgba(99,102,241,0.3)",
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
                color: "var(--text-muted)",
                fontWeight: 500,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                marginTop: 2,
              }}
            >
              Compliance Platform
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
        {NAV_ITEMS.map((item) => {
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
                  ? "1px solid rgba(99,102,241,0.25)"
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
