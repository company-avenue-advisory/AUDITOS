"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Building2, UserPlus, Trash2, RefreshCw, CheckCircle, AlertCircle, Edit2 } from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Member = {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
};

type Firm = {
  id: string;
  name: string;
  slug: string;
};

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" };
}

export default function FirmSettingsPage() {
  const [firm, setFirm] = useState<Firm | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create firm form
  const [creating, setCreating] = useState(false);
  const [newFirmName, setNewFirmName] = useState("");
  const [newFirmSlug, setNewFirmSlug] = useState("");
  const [createError, setCreateError] = useState("");
  const [createSuccess, setCreateSuccess] = useState("");

  // Edit firm
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editSlug, setEditSlug] = useState("");
  const [editError, setEditError] = useState("");

  // Invite member
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState("");
  const [inviteError, setInviteError] = useState("");

  const fetchFirm = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/api/me/tenant`, { headers: authHeaders() });
      const data = await res.json();
      if (data?.tenant) {
        setFirm(data.tenant);
        setEditName(data.tenant.name);
        setEditSlug(data.tenant.slug);
        // Fetch members
        const mRes = await fetch(`${API_BASE_URL}/api/admin/tenants/${data.tenant.id}/users`, { headers: authHeaders() });
        const mData = await mRes.json();
        setMembers(mData?.users || []);
      } else {
        setFirm(null);
        setMembers([]);
      }
    } catch {
      setError("Failed to load firm data. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFirm();
  }, [fetchFirm]);

  async function handleCreateFirm(e: React.FormEvent) {
    e.preventDefault();
    setCreateError("");
    setCreateSuccess("");
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/tenants`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ name: newFirmName, slug: newFirmSlug }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create firm");
      // Assign self
      await fetch(`${API_BASE_URL}/api/admin/tenants/${data.tenant_id}/assign-user?user_email=${encodeURIComponent(localStorage.getItem("user_email") || "")}`, {
        method: "POST",
        headers: authHeaders(),
      });
      setCreateSuccess(`Firm "${newFirmName}" created.`);
      setNewFirmName("");
      setNewFirmSlug("");
      await fetchFirm();
    } catch (e: any) {
      setCreateError(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleEditFirm(e: React.FormEvent) {
    e.preventDefault();
    setEditError("");
    if (!firm) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/tenants/${firm.id}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ name: editName, slug: editSlug }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update firm");
      setFirm(data);
      setEditing(false);
    } catch (e: any) {
      setEditError(e.message);
    }
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!firm) return;
    setInviteMsg("");
    setInviteError("");
    setInviting(true);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/admin/tenants/${firm.id}/assign-user?user_email=${encodeURIComponent(inviteEmail)}`,
        { method: "POST", headers: authHeaders() }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to add member");
      setInviteMsg(`${inviteEmail} added to firm.`);
      setInviteEmail("");
      await fetchFirm();
    } catch (e: any) {
      setInviteError(e.message);
    } finally {
      setInviting(false);
    }
  }

  async function handleRemove(userId: string, email: string) {
    if (!firm) return;
    if (!confirm(`Remove ${email} from ${firm.name}?`)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin/tenants/${firm.id}/users/${userId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to remove member");
      await fetchFirm();
    } catch (e: any) {
      alert(e.message);
    }
  }

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

  const btn = (variant: "primary" | "secondary" | "danger"): React.CSSProperties => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "10px 18px",
    borderRadius: 8,
    border: "none",
    cursor: "pointer",
    fontWeight: 600,
    fontSize: 13,
    background:
      variant === "primary" ? "var(--accent)" :
      variant === "danger" ? "rgba(239,68,68,0.1)" : "var(--bg-card)",
    color:
      variant === "primary" ? "#fff" :
      variant === "danger" ? "#ef4444" : "var(--text-secondary)",
    border:
      variant === "primary" ? "none" :
      variant === "danger" ? "1px solid rgba(239,68,68,0.25)" : "1px solid var(--border)",
  });

  const roleColor: Record<string, string> = {
    owner: "#6366f1", auditor: "#22d3ee", hr: "#f59e0b",
    developer: "#10b981", other: "var(--text-muted)",
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "40px 24px", color: "var(--text-primary)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 32 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: "linear-gradient(135deg,#6366f1,#818cf8)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 0 20px rgba(99,102,241,0.3)",
        }}>
          <Building2 size={22} color="#fff" />
        </div>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, letterSpacing: "-0.03em" }}>Firm Settings</h1>
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>
            Manage your CA firm's name, slug, and team members.
          </p>
        </div>
        <button onClick={fetchFirm} style={{ marginLeft: "auto", ...btn("secondary") }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {loading && (
        <div style={{ color: "var(--text-muted)", fontSize: 14 }}>Loading firm data...</div>
      )}

      {error && (
        <div style={{ padding: 14, borderRadius: 8, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444", fontSize: 13, marginBottom: 20 }}>
          <AlertCircle size={14} style={{ display: "inline", marginRight: 6 }} />{error}
        </div>
      )}

      {/* No firm yet — create one */}
      {!loading && !firm && (
        <div style={card}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 6px" }}>Create your firm</h2>
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 20px" }}>
            Set up your CA firm so team members can be grouped under the same workspace.
          </p>
          <form onSubmit={handleCreateFirm} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>Firm Name</label>
              <input
                style={input}
                placeholder="e.g. Avenue Advisory LLP"
                value={newFirmName}
                onChange={(e) => {
                  setNewFirmName(e.target.value);
                  if (!newFirmSlug) setNewFirmSlug(e.target.value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, ""));
                }}
                required
              />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>Slug <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(URL-safe, auto-generated)</span></label>
              <input style={input} placeholder="avenue-advisory-llp" value={newFirmSlug}
                onChange={(e) => setNewFirmSlug(e.target.value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, ""))}
                required
              />
            </div>
            {createError && <div style={{ fontSize: 12, color: "#ef4444" }}>{createError}</div>}
            {createSuccess && <div style={{ fontSize: 12, color: "#22d3ee" }}><CheckCircle size={12} style={{ display: "inline", marginRight: 4 }} />{createSuccess}</div>}
            <button type="submit" style={btn("primary")} disabled={creating}>
              {creating ? "Creating..." : "Create Firm"}
            </button>
          </form>
        </div>
      )}

      {/* Firm details */}
      {!loading && firm && (
        <>
          <div style={card}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: editing ? 20 : 0 }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Your Firm</div>
                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em" }}>{firm.name}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, fontFamily: "monospace" }}>/{firm.slug}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>ID: {firm.id}</div>
              </div>
              {!editing && (
                <button onClick={() => setEditing(true)} style={btn("secondary")}>
                  <Edit2 size={13} /> Edit
                </button>
              )}
            </div>
            {editing && (
              <form onSubmit={handleEditFirm} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>Firm Name</label>
                  <input style={input} value={editName} onChange={(e) => setEditName(e.target.value)} required />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: 6 }}>Slug</label>
                  <input style={input} value={editSlug}
                    onChange={(e) => setEditSlug(e.target.value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, ""))}
                    required
                  />
                </div>
                {editError && <div style={{ fontSize: 12, color: "#ef4444" }}>{editError}</div>}
                <div style={{ display: "flex", gap: 10 }}>
                  <button type="submit" style={btn("primary")}>Save Changes</button>
                  <button type="button" onClick={() => { setEditing(false); setEditName(firm.name); setEditSlug(firm.slug); setEditError(""); }} style={btn("secondary")}>Cancel</button>
                </div>
              </form>
            )}
          </div>

          {/* Team members */}
          <div style={card}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 16px" }}>Team Members <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: 13 }}>({members.length})</span></h2>
            {members.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-muted)", paddingBottom: 8 }}>No members yet. Invite someone below.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
                {members.map((m) => (
                  <div key={m.id} style={{
                    display: "flex", alignItems: "center", gap: 12,
                    padding: "12px 14px", borderRadius: 8,
                    background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)",
                  }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: "50%",
                      background: "var(--accent-soft)", display: "flex", alignItems: "center",
                      justifyContent: "center", fontSize: 13, fontWeight: 700, color: "var(--accent)",
                      flexShrink: 0,
                    }}>
                      {m.email[0].toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={m.email}>{m.email}</div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: roleColor[m.role] || "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 2 }}>{m.role}</div>
                    </div>
                    {!m.is_active && (
                      <span style={{ fontSize: 10, fontWeight: 700, color: "#f59e0b", background: "rgba(245,158,11,0.1)", borderRadius: 4, padding: "2px 6px" }}>INACTIVE</span>
                    )}
                    <button
                      onClick={() => handleRemove(m.id, m.email)}
                      style={{ ...btn("danger"), padding: "6px 10px" }}
                      title="Remove from firm"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Invite form */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 20 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, margin: "0 0 12px", color: "var(--text-secondary)" }}>Add Team Member</h3>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 14px" }}>
                The user must already have an account. Enter their registered email address.
              </p>
              <form onSubmit={handleInvite} style={{ display: "flex", gap: 10 }}>
                <input
                  style={{ ...input, width: "auto", flex: 1 }}
                  type="email"
                  placeholder="colleague@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                />
                <button type="submit" style={btn("primary")} disabled={inviting}>
                  <UserPlus size={14} />
                  {inviting ? "Adding..." : "Add"}
                </button>
              </form>
              {inviteMsg && <div style={{ fontSize: 12, color: "#22d3ee", marginTop: 10 }}><CheckCircle size={12} style={{ display: "inline", marginRight: 4 }} />{inviteMsg}</div>}
              {inviteError && <div style={{ fontSize: 12, color: "#ef4444", marginTop: 10 }}>{inviteError}</div>}
            </div>
          </div>

          {/* GSTIN info */}
          <div style={{ ...card, background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.2)" }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)", marginBottom: 8 }}>Firm GSTIN</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
              Set in <code style={{ background: "rgba(255,255,255,0.06)", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>backend/.env</code> as <code style={{ background: "rgba(255,255,255,0.06)", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>FIRM_GSTIN</code>.
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              The first 2 digits determine your state code for B2B/B2CS/B2CL inter-state split in GSTR-1 exports. Update this before exporting.
            </div>
          </div>
        </>
      )}
    </div>
  );
}
