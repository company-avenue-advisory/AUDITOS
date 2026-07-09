"use client";

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import { fetchActiveSession, clearActiveSession, type ResumableSession } from "../utils/sessionSync";

// Setup global fetch interceptor
if (typeof window !== "undefined") {
  const originalFetch = window.fetch;
  window.fetch = async function (input, init) {
    const urlString = typeof input === "string" ? input : (input instanceof Request ? input.url : "");
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const isBackend = urlString.startsWith(apiBaseUrl) || urlString.startsWith("/api");

    if (isBackend) {
      const token = localStorage.getItem("token");
      if (token) {
        init = init || {};
        const headers = new Headers(init.headers || {});
        if (!headers.has("Authorization")) {
          headers.set("Authorization", `Bearer ${token}`);
        }
        init.headers = headers;
      }
    }

    const response = await originalFetch(input, init);

    if (response.status === 401 && isBackend) {
      localStorage.removeItem("token");
      localStorage.removeItem("user_email");
      localStorage.removeItem("user_role");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return response;
  };
}

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [resumeSession, setResumeSession] = useState<ResumableSession | null>(null);
  const [toastDismissed, setToastDismissed] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      setIsAuthenticated(false);
      if (pathname !== "/login") {
        router.replace("/login");
      }
    } else {
      setIsAuthenticated(true);
      if (pathname === "/login") {
        router.replace("/");
      } else if (pathname === "/" || pathname === "/dashboard") {
        // Only show resume prompt on dashboard, not mid-session pages
        fetchActiveSession().then((session) => {
          if (
            session?.active_batch_id &&
            (session.batch_status === "PROCESSING" || session.batch_status === "COMPLETED")
          ) {
            setResumeSession(session);
          }
        });
      }
    }
  }, [pathname, router]);

  // Loading state (prevents layout flash)
  if (isAuthenticated === null) {
    return (
      <div
        style={{
          display: "flex",
          width: "100vw",
          height: "100vh",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--bg-base)",
          color: "var(--accent)",
          fontFamily: "var(--font-inter), sans-serif",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-0.04em", color: "var(--text-primary)" }}>
            Audit OS
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: "14px",
                height: "14px",
                border: "2px solid var(--accent-glow)",
                borderTopColor: "var(--accent)",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
              }}
            />
            <div style={{ fontSize: 13, color: "var(--accent)", fontWeight: 500 }}>
              Initializing secure session...
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (pathname === "/login") {
    return <div style={{ width: "100%", minHeight: "100vh" }}>{children}</div>;
  }

  const handleResume = () => {
    if (!resumeSession?.active_batch_id) return;
    setToastDismissed(true);
    router.push(`/invoice-extractor?batchId=${resumeSession.active_batch_id}`);
  };

  const handleDismissResume = () => {
    setToastDismissed(true);
    clearActiveSession();
  };

  return (
    <>
      <Sidebar />
      <div
        id="main-content-area"
        style={{
          marginLeft: 240,
          flex: 1,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {children}
      </div>

      {/* Resume toast */}
      {resumeSession && !toastDismissed && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            zIndex: 9999,
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "14px 18px",
            display: "flex",
            flexDirection: "column",
            gap: 10,
            maxWidth: 320,
            boxShadow: "0 8px 24px rgba(0,0,0,0.2)",
            fontFamily: "var(--font-inter), sans-serif",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <div style={{ fontSize: 18, lineHeight: 1 }}>📋</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                Resume last audit?
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                {resumeSession.batch_total_files
                  ? `${resumeSession.batch_total_files} invoice${resumeSession.batch_total_files > 1 ? "s" : ""}`
                  : "Batch"}{" "}
                · {resumeSession.batch_status === "COMPLETED" ? "Ready for review" : "In progress"}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleResume}
              className="btn-primary"
              style={{
                flex: 1,
                padding: "6px 12px",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                border: "none",
              }}
            >
              Resume
            </button>
            <button
              onClick={handleDismissResume}
              style={{
                padding: "6px 10px",
                background: "transparent",
                border: "1px solid var(--border)",
                borderRadius: 6,
                color: "var(--text-muted)",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </>
  );
}
