"use client";

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";

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
          background: "#06060a",
          color: "#a5b4fc",
          fontFamily: "var(--font-inter), sans-serif",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            width: "40vw",
            height: "40vw",
            top: "-10vw",
            left: "-10vw",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(99,102,241,0.1) 0%, transparent 75%)",
            filter: "blur(60px)",
            pointerEvents: "none",
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16, zIndex: 1 }}>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-0.04em", color: "#f5f5f7" }}>
            Audit OS
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: "14px",
                height: "14px",
                border: "2px solid rgba(129,140,248,0.3)",
                borderTopColor: "#818cf8",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
              }}
            />
            <div style={{ fontSize: 13, color: "#818cf8", fontWeight: 500 }}>
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
    </>
  );
}
