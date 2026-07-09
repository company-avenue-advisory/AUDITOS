"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Shield, Sparkles, LogIn, UserPlus, Eye, EyeOff } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("auditor");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      if (isLogin) {
        // Log in
        const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ email, password }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Authentication failed");
        }

        // Save tokens and user info
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("user_email", data.email);
        localStorage.setItem("user_role", data.role);

        setSuccess("Success! Redirecting...");
        setTimeout(() => {
          router.replace("/");
        }, 800);
      } else {
        // Register
        const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ email, password, role }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Registration failed");
        }

        setSuccess("Account created successfully! Switching to login...");
        setIsLogin(true);
        setPassword(""); // Clear password field
      }
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background: "var(--bg-base)",
      }}
    >
      <div
        className="glass animate-fade-up"
        style={{
          width: "100%",
          maxWidth: "440px",
          borderRadius: "var(--radius-lg)",
          padding: "40px 32px",
        }}
      >
        {/* Logo/Brand */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: "32px" }}>
          <div
            style={{
              width: "48px",
              height: "48px",
              borderRadius: "14px",
              background: "var(--accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: "16px",
            }}
          >
            <Shield size={24} style={{ color: "#fff" }} />
          </div>
          <h1
            style={{
              fontSize: "24px",
              fontWeight: 800,
              letterSpacing: "-0.04em",
              color: "var(--text-primary)",
              margin: 0,
            }}
          >
            Audit OS
          </h1>
          <p
            style={{
              fontSize: "12px",
              color: "var(--text-muted)",
              marginTop: "4px",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              fontWeight: 600,
            }}
          >
            Security Layer Enabled
          </p>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: "flex",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "4px",
            marginBottom: "28px",
          }}
        >
          <button
            onClick={() => {
              setIsLogin(true);
              setError("");
              setSuccess("");
            }}
            style={{
              flex: 1,
              padding: "10px",
              borderRadius: "8px",
              border: "none",
              background: isLogin ? "var(--accent-soft)" : "transparent",
              color: isLogin ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.2s ease",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
            }}
          >
            <LogIn size={14} />
            <span>Sign In</span>
          </button>
          <button
            onClick={() => {
              setIsLogin(false);
              setError("");
              setSuccess("");
            }}
            style={{
              flex: 1,
              padding: "10px",
              borderRadius: "8px",
              border: "none",
              background: !isLogin ? "var(--accent-soft)" : "transparent",
              color: !isLogin ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.2s ease",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
            }}
          >
            <UserPlus size={14} />
            <span>Create Account</span>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {error && (
            <div
              style={{
                background: "var(--red-soft)",
                border: "1px solid var(--red)",
                color: "var(--red)",
                padding: "12px 16px",
                borderRadius: "var(--radius-sm)",
                fontSize: "13px",
                lineHeight: 1.4,
              }}
            >
              {error}
            </div>
          )}

          {success && (
            <div
              style={{
                background: "var(--green-soft)",
                border: "1px solid var(--green)",
                color: "var(--green)",
                padding: "12px 16px",
                borderRadius: "var(--radius-sm)",
                fontSize: "13px",
                lineHeight: 1.4,
              }}
            >
              {success}
            </div>
          )}

          {/* Email input */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)" }}>Email Address</label>
            <input
              id="login-email-input"
              type="email"
              required
              placeholder="e.g. audit.lead@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="focus-ring"
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "12px 16px",
                color: "var(--text-primary)",
                fontSize: "14px",
                transition: "border-color 0.2s ease",
              }}
            />
          </div>

          {/* Password input */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)" }}>Password</label>
            <div style={{ position: "relative" }}>
              <input
                id="login-password-input"
                type={showPassword ? "text" : "password"}
                required
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="focus-ring"
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "12px 48px 12px 16px",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                  width: "100%",
                  transition: "border-color 0.2s ease",
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: "absolute",
                  right: "12px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "4px",
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Role selector - only on registration */}
          {!isLogin && (
            <div className="animate-fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)" }}>Company Role</label>
              <select
                id="login-role-select"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="focus-ring"
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "12px 16px",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                  cursor: "pointer",
                  width: "100%",
                }}
              >
                <option value="owner">Owner (Full Admin Access)</option>
                <option value="hr">HR (Compliance & Udyam Access)</option>
                <option value="auditor">Auditor (Extractor & Audits)</option>
                <option value="other">Other (Read-Only Views)</option>
              </select>
              <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>
                Roles define access rules for MSME tax audits, PDF extractor operations, and dashboard stats.
              </span>
            </div>
          )}

          {/* Submit button */}
          <button
            type="submit"
            disabled={loading}
            id="login-submit-btn"
            className="btn-primary"
            style={{
              padding: "14px",
              marginTop: "8px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              fontSize: "14px",
              cursor: "pointer",
            }}
          >
            {loading ? (
              <div
                className="animate-spin"
                style={{
                  width: "18px",
                  height: "18px",
                  border: "2px solid rgba(255,255,255,0.3)",
                  borderTopColor: "#fff",
                  borderRadius: "50%",
                }}
              />
            ) : isLogin ? (
              <>
                <span>Sign In to Audit OS</span>
                <LogIn size={16} />
              </>
            ) : (
              <>
                <span>Create Audit OS Account</span>
                <UserPlus size={16} />
              </>
            )}
          </button>
        </form>

        {/* Footer info */}
        <div
          style={{
            marginTop: "32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          <Sparkles size={12} style={{ color: "var(--accent)" }} />
          <span>Secured with cryptographic password hashing (bcrypt)</span>
        </div>
      </div>
    </div>
  );
}
