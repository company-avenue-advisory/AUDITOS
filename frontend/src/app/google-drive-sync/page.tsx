"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Cloud, FolderOpen, RefreshCw, CheckCircle, AlertCircle,
  Clock, Download, Loader, Link as LinkIcon, Settings,
  FileText, AlertTriangle, Wifi, WifiOff,
} from "lucide-react";
import { apiRequest } from "@/utils/api";
import StatusBadge from "../../components/ui/StatusBadge";
import MetricCard from "../../components/ui/MetricCard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface DriveConfig {
  folder_id: string | null;
  invoice_type: string;
  schedule: string;
  fiscal_year_start_month?: number | null;
  month_folder_pattern?: string | null;
  sales_root_folder_id?: string | null;
  purchase_root_folder_id?: string | null;
  gstr2b_root_folder_id?: string | null;
  sales_schedule?: string | null;
  purchase_schedule?: string | null;
  gstr2b_schedule?: string | null;
  updated_at: string | null;
}

type SelfResolvingPipeline = "sales" | "purchase" | "gstr2b";

interface SyncJob {
  id: string;
  batch_id: string;
  sync_timestamp: string;
  total_files_found: number;
  new_files: number;
  updated_files: number;
  processed_files: number;
  failed_files: number;
  status: "in_progress" | "completed" | "failed";
  completed_at: string | null;
}

interface TaskStatus {
  task_id: string;
  status: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE";
  result?: {
    batch_id: string;
    total_files_found: number;
    new_files: number;
    updated_files: number;
    processed_files: number;
    failed_files: number;
    duration_seconds: number | null;
  };
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractFolderIdFromUrl(input: string): string {
  const match = input.match(/\/folders\/([a-zA-Z0-9_-]{10,})/);
  if (match) return match[1];
  if (/^[a-zA-Z0-9_-]{10,}$/.test(input.trim())) return input.trim();
  return "";
}

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

export default function GoogleDriveSyncPage() {
  // Config panel
  const [folderInput, setFolderInput]   = useState("");
  const [invoiceType, setInvoiceType]   = useState("both");
  const [schedule, setSchedule]         = useState("0 0 1 * *");
  const [savedConfig, setSavedConfig]   = useState<DriveConfig | null>(null);
  const [configSaving, setConfigSaving]   = useState(false);
  const [configMsg, setConfigMsg]         = useState<{ ok: boolean; text: string } | null>(null);

  // Sync panel
  const [syncing, setSyncing]           = useState(false);
  const [taskId, setTaskId]             = useState<string | null>(null);
  const [taskStatus, setTaskStatus]     = useState<TaskStatus | null>(null);
  const [syncError, setSyncError]       = useState<string | null>(null);

  // Self-resolving ingestion panel (Sales / Purchase / GSTR-2B)
  const [salesRootFolder, setSalesRootFolder]       = useState("");
  const [purchaseRootFolder, setPurchaseRootFolder] = useState("");
  const [gstr2bRootFolder, setGstr2bRootFolder]     = useState("");
  const [fiscalYearStartMonth, setFiscalYearStartMonth] = useState(4);
  const [monthFolderPattern, setMonthFolderPattern] = useState("{n}. {month_name} {year}");
  const [selfResolvingSaving, setSelfResolvingSaving] = useState(false);
  const [selfResolvingMsg, setSelfResolvingMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [pipelineTaskIds, setPipelineTaskIds] = useState<Record<SelfResolvingPipeline, string | null>>({
    sales: null, purchase: null, gstr2b: null,
  });
  const [pipelineStatuses, setPipelineStatuses] = useState<Record<SelfResolvingPipeline, TaskStatus | null>>({
    sales: null, purchase: null, gstr2b: null,
  });
  const [pipelineTriggering, setPipelineTriggering] = useState<Record<SelfResolvingPipeline, boolean>>({
    sales: false, purchase: false, gstr2b: false,
  });
  const [pipelineErrors, setPipelineErrors] = useState<Record<SelfResolvingPipeline, string | null>>({
    sales: null, purchase: null, gstr2b: null,
  });

  // History panel
  const [history, setHistory]           = useState<SyncJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ── Load saved config on mount ────────────────────────────────────────────

  const loadConfig = useCallback(async () => {
    try {
      const res = await apiRequest("/api/google-drive-sync/config");
      if (res.ok) {
        const data = await res.json();
        if (data.configured && data.config) {
          setSavedConfig(data.config);
          setFolderInput(data.config.folder_id ?? "");
          setInvoiceType(data.config.invoice_type);
          setSchedule(data.config.schedule ?? "0 0 1 * *");
          setSalesRootFolder(data.config.sales_root_folder_id ?? "");
          setPurchaseRootFolder(data.config.purchase_root_folder_id ?? "");
          setGstr2bRootFolder(data.config.gstr2b_root_folder_id ?? "");
          setFiscalYearStartMonth(data.config.fiscal_year_start_month ?? 4);
          setMonthFolderPattern(data.config.month_folder_pattern ?? "{n}. {month_name} {year}");
        }
      }
    } finally { /* no-op */ }
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await apiRequest("/api/google-drive-sync/history");
      if (res.ok) {
        const data = await res.json();
        setHistory(data.sync_jobs ?? []);
      }
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadHistory();
  }, [loadConfig, loadHistory]);

  // ── Poll legacy task status ───────────────────────────────────────────────

  useEffect(() => {
    if (!taskId) return;
    const iv = setInterval(async () => {
      try {
        const res = await apiRequest(`/api/google-drive-sync/status/${taskId}`);
        if (!res.ok) return;
        const data: TaskStatus = await res.json();
        setTaskStatus(data);
        if (data.status === "SUCCESS" || data.status === "FAILURE") {
          clearInterval(iv);
          setSyncing(false);
          if (data.status === "FAILURE") setSyncError(data.error ?? "Unknown error");
          loadHistory();
        }
      } catch {/* network blip — keep polling */}
    }, 2500);
    return () => clearInterval(iv);
  }, [taskId, loadHistory]);

  // Poll each self-resolving pipeline's task independently.
  useEffect(() => {
    const pipelines: SelfResolvingPipeline[] = ["sales", "purchase", "gstr2b"];
    const intervals = pipelines.map((p) => {
      const id = pipelineTaskIds[p];
      if (!id) return null;
      return setInterval(async () => {
        try {
          const res = await apiRequest(`/api/google-drive-sync/status/${id}`);
          if (!res.ok) return;
          const data: TaskStatus = await res.json();
          setPipelineStatuses(prev => ({ ...prev, [p]: data }));
          if (data.status === "SUCCESS" || data.status === "FAILURE") {
            setPipelineTriggering(prev => ({ ...prev, [p]: false }));
            if (data.status === "FAILURE") {
              setPipelineErrors(prev => ({ ...prev, [p]: data.error ?? "Unknown error" }));
            }
            loadHistory();
          }
        } catch {/* network blip - keep polling */}
      }, 2500);
    });
    return () => intervals.forEach((iv) => { if (iv) clearInterval(iv); });
  }, [pipelineTaskIds, loadHistory]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleSaveConfig = async () => {
    const folderId = extractFolderIdFromUrl(folderInput);
    if (!folderId) {
      setConfigMsg({ ok: false, text: "Paste a valid Google Drive folder URL or ID." });
      return;
    }
    setConfigSaving(true);
    setConfigMsg(null);
    try {
      const res = await apiRequest("/api/google-drive-sync/config", {
        method: "POST",
        body: JSON.stringify({
          folder_id: folderId, invoice_type: invoiceType, schedule,
          sales_root_folder_id: salesRootFolder ? extractFolderIdFromUrl(salesRootFolder) || salesRootFolder : null,
          purchase_root_folder_id: purchaseRootFolder ? extractFolderIdFromUrl(purchaseRootFolder) || purchaseRootFolder : null,
          gstr2b_root_folder_id: gstr2bRootFolder ? extractFolderIdFromUrl(gstr2bRootFolder) || gstr2bRootFolder : null,
          fiscal_year_start_month: fiscalYearStartMonth,
          month_folder_pattern: monthFolderPattern,
        }),
      });
      if (res.ok) {
        setConfigMsg({ ok: true, text: "Config saved. Drive folder connected." });
        loadConfig();
      } else {
        const err = await res.json();
        setConfigMsg({ ok: false, text: err.detail ?? "Failed to save config." });
      }
    } finally {
      setConfigSaving(false);
    }
  };

  const handleSaveSelfResolvingConfig = async () => {
    setSelfResolvingSaving(true);
    setSelfResolvingMsg(null);
    try {
      const res = await apiRequest("/api/google-drive-sync/config", {
        method: "POST",
        body: JSON.stringify({
          folder_id: savedConfig?.folder_id ? extractFolderIdFromUrl(savedConfig.folder_id) || savedConfig.folder_id : null,
          invoice_type: savedConfig?.invoice_type ?? "both",
          schedule: savedConfig?.schedule ?? "0 0 1 * *",
          sales_root_folder_id: salesRootFolder ? (extractFolderIdFromUrl(salesRootFolder) || salesRootFolder) : null,
          purchase_root_folder_id: purchaseRootFolder ? (extractFolderIdFromUrl(purchaseRootFolder) || purchaseRootFolder) : null,
          gstr2b_root_folder_id: gstr2bRootFolder ? (extractFolderIdFromUrl(gstr2bRootFolder) || gstr2bRootFolder) : null,
          fiscal_year_start_month: fiscalYearStartMonth,
          month_folder_pattern: monthFolderPattern,
        }),
      });
      if (res.ok) {
        setSelfResolvingMsg({ ok: true, text: "Saved. Ingestion schedules registered." });
        loadConfig();
      } else {
        const err = await res.json();
        setSelfResolvingMsg({ ok: false, text: err.detail ?? "Failed to save config." });
      }
    } finally {
      setSelfResolvingSaving(false);
    }
  };

  const triggerPipeline = async (pipeline: SelfResolvingPipeline) => {
    setPipelineTriggering(prev => ({ ...prev, [pipeline]: true }));
    setPipelineErrors(prev => ({ ...prev, [pipeline]: null }));
    setPipelineStatuses(prev => ({ ...prev, [pipeline]: null }));
    try {
      const res = await apiRequest(`/api/google-drive-sync/trigger-${pipeline}`, { method: "POST", body: JSON.stringify({}) });
      if (res.ok) {
        const data = await res.json();
        setPipelineTaskIds(prev => ({ ...prev, [pipeline]: data.task_id }));
      } else {
        const err = await res.json();
        setPipelineErrors(prev => ({ ...prev, [pipeline]: err.detail ?? "Failed to start." }));
        setPipelineTriggering(prev => ({ ...prev, [pipeline]: false }));
      }
    } catch (e: any) {
      setPipelineErrors(prev => ({ ...prev, [pipeline]: e.message }));
      setPipelineTriggering(prev => ({ ...prev, [pipeline]: false }));
    }
  };

  const handleTriggerSync = async () => {
    setSyncing(true);
    setSyncError(null);
    setTaskStatus(null);
    setTaskId(null);
    try {
      const res = await apiRequest("/api/google-drive-sync/trigger", { method: "POST", body: JSON.stringify({}) });
      if (res.ok) {
        const data = await res.json();
        setTaskId(data.task_id);
      } else {
        const err = await res.json();
        setSyncError(err.detail ?? "Failed to start sync.");
        setSyncing(false);
      }
    } catch (e: any) {
      setSyncError(e.message);
      setSyncing(false);
    }
  };

  const downloadExcel = async (batchId: string, type: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : "";
    try {
      const res = await fetch(`${API_BASE}/api/export/${batchId}?type=${type}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sync_${batchId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Failed to download export", e);
    }
  };

  const derivedFolderId = extractFolderIdFromUrl(folderInput);
  const isConfigured = !!savedConfig?.folder_id;
  const activeInvoiceType = savedConfig?.invoice_type ?? invoiceType;
  const latestJob = history.find(j => j.status === "completed");

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ flex: 1, padding: "32px 40px", maxWidth: 1100 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <Cloud size={20} style={{ color: "var(--accent)" }} />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Google Drive Sync</h1>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: isConfigured ? "var(--green)" : "var(--text-muted)" }}>
          {isConfigured ? <Wifi size={14} /> : <WifiOff size={14} />}
          {isConfigured ? "Folder connected" : "Not configured"}
        </span>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 24 }}>
        Pull invoice PDFs from a client&apos;s Drive folder, extract, and download Excel.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

        {/* ── Connect Drive Folder (legacy single-folder mode) ────────────── */}
        <SectionCard
          title="Connect Drive Folder"
          icon={<Settings size={16} style={{ color: "var(--accent)" }} />}
          subtitle={savedConfig?.updated_at ? `Updated ${new Date(savedConfig.updated_at).toLocaleDateString()}` : undefined}
        >
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            <div style={{ gridColumn: "1 / -1" }}>
              <label style={labelStyle}>Google Drive folder URL or ID</label>
              <div style={{ position: "relative" }}>
                <LinkIcon size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
                <input
                  type="text"
                  value={folderInput}
                  onChange={e => setFolderInput(e.target.value)}
                  placeholder="https://drive.google.com/drive/folders/... or bare ID"
                  style={{ ...inputStyle, paddingLeft: 32 }}
                />
              </div>
              {folderInput && (
                <p style={{ marginTop: 6, fontSize: 12, color: derivedFolderId ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>
                  {derivedFolderId || "invalid URL"}
                </p>
              )}
            </div>
            <div>
              <label style={labelStyle}>Invoice type</label>
              <select value={invoiceType} onChange={e => setInvoiceType(e.target.value)} style={inputStyle}>
                <option value="both">Both (Sales + Purchase)</option>
                <option value="sales">Sales only</option>
                <option value="purchase">Purchase only</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Auto-sync schedule (cron)</label>
              <input type="text" value={schedule} onChange={e => setSchedule(e.target.value)} style={{ ...inputStyle, fontFamily: "var(--font-mono)" }} />
              <p style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>Default: 1st of every month at midnight UTC</p>
            </div>
            <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: 12 }}>
              <button className="btn-primary" onClick={handleSaveConfig} disabled={configSaving || !folderInput} style={{ padding: "10px 20px", display: "flex", alignItems: "center", gap: 8, fontSize: 13, border: "none" }}>
                {configSaving ? <Loader size={14} className="animate-spin" /> : <FolderOpen size={14} />}
                {configSaving ? "Saving…" : "Save configuration"}
              </button>
              {configMsg && (
                <span style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6, color: configMsg.ok ? "var(--green)" : "var(--red)" }}>
                  {configMsg.ok ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                  {configMsg.text}
                </span>
              )}
            </div>
          </div>
        </SectionCard>

        {/* ── Self-resolving ingestion: Sales / Purchase / GSTR-2B ──────────── */}
        <SectionCard
          title="Self-Resolving Ingestion"
          icon={<RefreshCw size={16} style={{ color: "var(--accent)" }} />}
          subtitle="Auto-resolves the current month's folder"
        >
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            <div>
              <label style={labelStyle}>Sales root folder (URL or ID)</label>
              <input type="text" value={salesRootFolder} onChange={e => setSalesRootFolder(e.target.value)}
                placeholder="Folder containing '1. April 2026', '2. May 2026', ..." style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>Purchase root folder (URL or ID)</label>
              <input type="text" value={purchaseRootFolder} onChange={e => setPurchaseRootFolder(e.target.value)}
                placeholder="Folder containing the same month subfolders" style={inputStyle} />
            </div>
            <div>
              <label style={labelStyle}>GSTR-2B root folder (URL or ID)</label>
              <input type="text" value={gstr2bRootFolder} onChange={e => setGstr2bRootFolder(e.target.value)}
                placeholder="A dedicated drop folder for monthly GSTR-2B JSON files" style={inputStyle} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={labelStyle}>Fiscal year starts</label>
                <select value={fiscalYearStartMonth} onChange={e => setFiscalYearStartMonth(Number(e.target.value))} style={inputStyle}>
                  {["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].map((m, i) => (
                    <option key={m} value={i + 1}>{m}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={labelStyle}>Month folder pattern</label>
                <input type="text" value={monthFolderPattern} onChange={e => setMonthFolderPattern(e.target.value)} style={{ ...inputStyle, fontFamily: "var(--font-mono)" }} />
              </div>
            </div>

            <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: 12 }}>
              <button
                className="btn-primary"
                onClick={handleSaveSelfResolvingConfig}
                disabled={selfResolvingSaving || (!salesRootFolder && !purchaseRootFolder && !gstr2bRootFolder)}
                style={{ padding: "10px 20px", display: "flex", alignItems: "center", gap: 8, fontSize: 13, border: "none" }}
              >
                {selfResolvingSaving ? <Loader size={14} className="animate-spin" /> : <FolderOpen size={14} />}
                {selfResolvingSaving ? "Saving…" : "Save & register schedules"}
              </button>
              {selfResolvingMsg && (
                <span style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6, color: selfResolvingMsg.ok ? "var(--green)" : "var(--red)" }}>
                  {selfResolvingMsg.ok ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                  {selfResolvingMsg.text}
                </span>
              )}
            </div>

            {/* Per-pipeline trigger + status */}
            <div style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
              {(["sales", "purchase", "gstr2b"] as SelfResolvingPipeline[]).map((pipeline) => {
                const configured =
                  pipeline === "sales" ? !!savedConfig?.sales_root_folder_id :
                  pipeline === "purchase" ? !!savedConfig?.purchase_root_folder_id :
                  !!savedConfig?.gstr2b_root_folder_id;
                const status = pipelineStatuses[pipeline];
                const triggering = pipelineTriggering[pipeline];
                const error = pipelineErrors[pipeline];
                const label = pipeline === "sales" ? "Sales" : pipeline === "purchase" ? "Purchase" : "GSTR-2B";
                return (
                  <div key={pipeline} style={{ background: "var(--bg-card)", borderRadius: "var(--radius-sm)", padding: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
                      {status && <StatusBadge status={status.status} />}
                    </div>
                    <button
                      onClick={() => triggerPipeline(pipeline)}
                      disabled={triggering || !configured}
                      className={triggering || !configured ? "btn-ghost" : "btn-primary"}
                      style={{ width: "100%", padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "center", gap: 6, fontSize: 12, border: triggering || !configured ? undefined : "none" }}
                    >
                      {triggering ? <Loader size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                      {triggering ? "Running…" : configured ? "Run now" : "Not configured"}
                    </button>
                    {error && <p style={{ marginTop: 8, fontSize: 11, color: "var(--red)" }}>{error}</p>}
                    {status?.status === "SUCCESS" && status.result && (
                      <p style={{ marginTop: 8, fontSize: 11, color: "var(--green)" }}>
                        {status.result.processed_files} processed, {status.result.failed_files} failed
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </SectionCard>

        {/* ── Pull from Drive (legacy manual trigger) ─────────────────────── */}
        <SectionCard
          title="Pull from Drive"
          icon={<RefreshCw size={16} style={{ color: "var(--accent)" }} />}
          disabled={!isConfigured}
          subtitle={!isConfigured ? "Connect a folder above first" : undefined}
        >
          {isConfigured && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16, fontSize: 12, color: "var(--text-secondary)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-card)", padding: "6px 12px", borderRadius: "var(--radius-sm)", fontFamily: "var(--font-mono)" }}>
                <FolderOpen size={13} style={{ color: "var(--accent)" }} />
                {savedConfig?.folder_id?.slice(0, 16)}…
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-card)", padding: "6px 12px", borderRadius: "var(--radius-sm)" }}>
                <FileText size={13} />
                {savedConfig?.invoice_type}
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-card)", padding: "6px 12px", borderRadius: "var(--radius-sm)" }}>
                <Clock size={13} />
                Auto: {savedConfig?.schedule}
              </span>
            </div>
          )}

          {syncError && (
            <div style={{ display: "flex", gap: 8, padding: 12, background: "var(--red-soft)", borderRadius: "var(--radius-sm)", fontSize: 13, color: "var(--red)", marginBottom: 16 }}>
              <AlertTriangle size={14} style={{ marginTop: 2, flexShrink: 0 }} />
              {syncError}
            </div>
          )}

          {taskStatus && (
            <div style={{ marginBottom: 16, padding: 16, background: "var(--bg-card)", borderRadius: "var(--radius-sm)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Sync in progress</span>
                <StatusBadge status={taskStatus.status} />
              </div>
              {taskStatus.status === "PENDING" || taskStatus.status === "STARTED" ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--accent)" }}>
                  <Loader size={14} className="animate-spin" />
                  Connecting to Google Drive and processing invoices…
                </div>
              ) : taskStatus.status === "SUCCESS" && taskStatus.result ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
                  <MetricCard label="Found" value={taskStatus.result.total_files_found} />
                  <MetricCard label="Processed" value={taskStatus.result.processed_files} color="var(--green)" />
                  <MetricCard label="Failed" value={taskStatus.result.failed_files} color={taskStatus.result.failed_files > 0 ? "var(--red)" : undefined} />
                </div>
              ) : taskStatus.status === "FAILURE" ? (
                <p style={{ fontSize: 13, color: "var(--red)" }}>{taskStatus.error}</p>
              ) : null}
              {taskStatus.status === "SUCCESS" && taskStatus.result?.duration_seconds && (
                <p style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
                  Completed in {taskStatus.result.duration_seconds.toFixed(1)}s
                </p>
              )}
            </div>
          )}

          <button
            className={syncing ? "btn-ghost" : "btn-primary"}
            onClick={handleTriggerSync}
            disabled={syncing || !isConfigured}
            style={{ padding: "10px 20px", display: "flex", alignItems: "center", gap: 8, fontSize: 13, border: syncing ? undefined : "none" }}
          >
            {syncing ? <Loader size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {syncing ? "Syncing…" : "Pull invoices from Drive"}
          </button>
          <p style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
            Only new or changed PDFs are processed — already-synced files are skipped automatically.
          </p>
        </SectionCard>

        {/* ── Download Results ────────────────────────────────────────────── */}
        <SectionCard
          title="Download Results"
          icon={<Download size={16} style={{ color: "var(--accent)" }} />}
        >
          {latestJob && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--green-soft)", borderRadius: "var(--radius-sm)", padding: 16, marginBottom: 16 }}>
              <div>
                <p style={{ fontSize: 13, fontWeight: 600, color: "var(--green)", margin: 0 }}>Latest sync complete</p>
                <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>
                  {latestJob.processed_files} invoices extracted on {new Date(latestJob.sync_timestamp).toLocaleString()}
                </p>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {(activeInvoiceType === "both" || activeInvoiceType === "sales") && (
                  <button className="btn-ghost" onClick={() => downloadExcel(latestJob.batch_id, "sales")} style={{ padding: "8px 14px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                    <Download size={13} /> Sales Excel
                  </button>
                )}
                {(activeInvoiceType === "both" || activeInvoiceType === "purchase") && (
                  <button className="btn-ghost" onClick={() => downloadExcel(latestJob.batch_id, "purchase")} style={{ padding: "8px 14px", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                    <Download size={13} /> Purchase Excel
                  </button>
                )}
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>Sync history</span>
            <button onClick={loadHistory} className="btn-ghost" style={{ padding: 6, border: "none", background: "none" }}>
              <RefreshCw size={14} className={historyLoading ? "animate-spin" : ""} />
            </button>
          </div>

          {historyLoading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "24px 0", textAlign: "center" }}>Loading…</div>
          ) : history.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "24px 0", textAlign: "center" }}>No syncs yet — run your first pull above.</div>
          ) : (
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", overflow: "hidden" }}>
              {history.map((job, i) => (
                <div
                  key={job.id}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 14px", background: "var(--bg-card)",
                    borderBottom: i < history.length - 1 ? "1px solid var(--border)" : "none",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 12 }}>
                    <span style={{ color: "var(--text-secondary)", minWidth: 140 }}>{new Date(job.sync_timestamp).toLocaleString()}</span>
                    <StatusBadge status={job.status} />
                    <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{job.total_files_found} found</span>
                    <span style={{ color: "var(--green)", fontFamily: "var(--font-mono)" }}>{job.processed_files} processed</span>
                    {job.failed_files > 0 && <span style={{ color: "var(--red)", fontFamily: "var(--font-mono)" }}>{job.failed_files} failed</span>}
                  </div>
                  {job.status === "completed" && job.processed_files > 0 && (
                    <div style={{ display: "flex", gap: 6 }}>
                      {(activeInvoiceType === "both" || activeInvoiceType === "sales") && (
                        <button className="btn-ghost" onClick={() => downloadExcel(job.batch_id, "sales")} style={{ padding: "4px 10px", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                          <Download size={11} /> Sales
                        </button>
                      )}
                      {(activeInvoiceType === "both" || activeInvoiceType === "purchase") && (
                        <button className="btn-ghost" onClick={() => downloadExcel(job.batch_id, "purchase")} style={{ padding: "4px 10px", fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                          <Download size={11} /> Purchase
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
