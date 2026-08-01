"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Cloud, FolderOpen, RefreshCw, CheckCircle, AlertCircle,
  Download, Loader, Link as LinkIcon, Settings,
  FileText, AlertTriangle, StopCircle, ChevronDown,
  ArrowDownToLine, ShieldCheck, FileSpreadsheet,
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

type Pipeline = "sales" | "purchase" | "gstr2b";

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

/** Generate last 12 months as options, most recent first. */
function generateMonthOptions(): { label: string; value: string }[] {
  const options: { label: string; value: string }[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    const monthName = d.toLocaleString("en-IN", { month: "long" });
    options.push({
      label: `${monthName} ${year}`,
      value: `${year}-${String(month).padStart(2, "0")}`,
    });
  }
  return options;
}

const MONTH_OPTIONS = generateMonthOptions();

const PIPELINE_LABELS: Record<Pipeline, string> = {
  sales: "Sales Invoices",
  purchase: "Purchase Invoices",
  gstr2b: "GSTR-2B Returns",
};

const PIPELINE_ENDPOINTS: Record<Pipeline, string> = {
  sales: "/api/google-drive-sync/trigger-sales",
  purchase: "/api/google-drive-sync/trigger-purchase",
  gstr2b: "/api/google-drive-sync/trigger-gstr2b",
};

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
  fontSize: 13,
  color: "var(--text-secondary)",
  marginBottom: 6,
  fontWeight: 500,
};

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function GoogleDriveSyncPage() {
  // Config state
  const [folderInput, setFolderInput]   = useState("");
  const [invoiceType, setInvoiceType]   = useState("both");
  const [schedule, setSchedule]         = useState("0 0 1 * *");
  const [savedConfig, setSavedConfig]   = useState<DriveConfig | null>(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [configMsg, setConfigMsg]       = useState<{ ok: boolean; text: string } | null>(null);

  // Self-resolving folder config
  const [salesRootFolder, setSalesRootFolder]       = useState("");
  const [purchaseRootFolder, setPurchaseRootFolder] = useState("");
  const [gstr2bRootFolder, setGstr2bRootFolder]     = useState("");
  const [fiscalYearStartMonth, setFiscalYearStartMonth] = useState(4);
  const [monthFolderPattern, setMonthFolderPattern] = useState("{n}. {month_name} {year}");

  // Month selector
  const [selectedPeriod, setSelectedPeriod] = useState(MONTH_OPTIONS[0].value);

  // Pipeline task tracking
  const [pipelineTaskIds, setPipelineTaskIds] = useState<Record<Pipeline, string | null>>({
    sales: null, purchase: null, gstr2b: null,
  });
  const [pipelineStatuses, setPipelineStatuses] = useState<Record<Pipeline, TaskStatus | null>>({
    sales: null, purchase: null, gstr2b: null,
  });
  const [pipelineTriggering, setPipelineTriggering] = useState<Record<Pipeline, boolean>>({
    sales: false, purchase: false, gstr2b: false,
  });
  const [pipelineErrors, setPipelineErrors] = useState<Record<Pipeline, string | null>>({
    sales: null, purchase: null, gstr2b: null,
  });

  // History
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

  // ── Poll each pipeline task ───────────────────────────────────────────────

  useEffect(() => {
    const pipelines: Pipeline[] = ["sales", "purchase", "gstr2b"];
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
      }, 3000);
    });
    return () => intervals.forEach((iv) => { if (iv) clearInterval(iv); });
  }, [pipelineTaskIds, loadHistory]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const triggerPipeline = async (pipeline: Pipeline) => {
    setPipelineTriggering(prev => ({ ...prev, [pipeline]: true }));
    setPipelineErrors(prev => ({ ...prev, [pipeline]: null }));
    setPipelineStatuses(prev => ({ ...prev, [pipeline]: null }));
    try {
      const body = pipeline === "gstr2b"
        ? JSON.stringify({})
        : JSON.stringify({ period: selectedPeriod });
      const res = await apiRequest(PIPELINE_ENDPOINTS[pipeline], { method: "POST", body });
      if (res.ok) {
        const data = await res.json();
        setPipelineTaskIds(prev => ({ ...prev, [pipeline]: data.task_id }));
      } else {
        const err = await res.json();
        setPipelineErrors(prev => ({ ...prev, [pipeline]: err.detail ?? "Failed to start." }));
        setPipelineTriggering(prev => ({ ...prev, [pipeline]: false }));
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Network error";
      setPipelineErrors(prev => ({ ...prev, [pipeline]: msg }));
      setPipelineTriggering(prev => ({ ...prev, [pipeline]: false }));
    }
  };

  const cancelPipeline = async (pipeline: Pipeline) => {
    const taskId = pipelineTaskIds[pipeline];
    if (!taskId) return;
    try {
      await apiRequest(`/api/google-drive-sync/cancel/${taskId}`, { method: "POST" });
      setPipelineTriggering(prev => ({ ...prev, [pipeline]: false }));
      setPipelineTaskIds(prev => ({ ...prev, [pipeline]: null }));
      setPipelineStatuses(prev => ({
        ...prev,
        [pipeline]: { task_id: taskId, status: "FAILURE" as const, error: "Cancelled by user" },
      }));
    } catch {
      // cancel failed — keep polling, the task may finish on its own
    }
  };

  const handleSaveConfig = async () => {
    setConfigSaving(true);
    setConfigMsg(null);
    try {
      const folderId = folderInput ? (extractFolderIdFromUrl(folderInput) || folderInput) : null;
      const res = await apiRequest("/api/google-drive-sync/config", {
        method: "POST",
        body: JSON.stringify({
          folder_id: folderId,
          invoice_type: invoiceType,
          schedule,
          sales_root_folder_id: salesRootFolder ? (extractFolderIdFromUrl(salesRootFolder) || salesRootFolder) : null,
          purchase_root_folder_id: purchaseRootFolder ? (extractFolderIdFromUrl(purchaseRootFolder) || purchaseRootFolder) : null,
          gstr2b_root_folder_id: gstr2bRootFolder ? (extractFolderIdFromUrl(gstr2bRootFolder) || gstr2bRootFolder) : null,
          fiscal_year_start_month: fiscalYearStartMonth,
          month_folder_pattern: monthFolderPattern,
        }),
      });
      if (res.ok) {
        setConfigMsg({ ok: true, text: "Settings saved successfully." });
        loadConfig();
      } else {
        const err = await res.json();
        setConfigMsg({ ok: false, text: err.detail ?? "Failed to save settings." });
      }
    } finally {
      setConfigSaving(false);
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
      a.download = `${type}_invoices_${batchId}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Failed to download export", e);
    }
  };

  // ── Derived state ─────────────────────────────────────────────────────────

  const isSalesConfigured = !!savedConfig?.sales_root_folder_id;
  const isPurchaseConfigured = !!savedConfig?.purchase_root_folder_id;
  const isGstr2bConfigured = !!savedConfig?.gstr2b_root_folder_id;
  const anyConfigured = isSalesConfigured || isPurchaseConfigured || isGstr2bConfigured;

  const configuredMap: Record<Pipeline, boolean> = {
    sales: isSalesConfigured,
    purchase: isPurchaseConfigured,
    gstr2b: isGstr2bConfigured,
  };

  const activePipelines: Pipeline[] = (["sales", "purchase", "gstr2b"] as Pipeline[]).filter(
    p => pipelineTriggering[p] || (pipelineStatuses[p] && (pipelineStatuses[p]!.status === "PENDING" || pipelineStatuses[p]!.status === "STARTED"))
  );

  const latestJob = history.find(j => j.status === "completed");
  const selectedMonthLabel = MONTH_OPTIONS.find(o => o.value === selectedPeriod)?.label ?? selectedPeriod;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ flex: 1, padding: "32px 40px", maxWidth: 900 }}>

      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <Cloud size={22} style={{ color: "var(--accent)" }} />
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Invoice Import</h1>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: 14, margin: 0 }}>
          Import invoices from Google Drive and download the extracted Excel sheets.
        </p>
      </div>

      {/* ── Zone 1: Primary Action Bar ──────────────────────────────────── */}
      <div
        className="glass"
        style={{
          borderRadius: "var(--radius-lg)",
          padding: "24px 28px",
          marginBottom: 20,
        }}
      >
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}>
          {/* Month selector */}
          <div style={{ minWidth: 200 }}>
            <label style={{ ...labelStyle, marginBottom: 4 }}>Month</label>
            <select
              value={selectedPeriod}
              onChange={e => setSelectedPeriod(e.target.value)}
              style={{
                ...inputStyle,
                padding: "10px 14px",
                fontSize: 14,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              {MONTH_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Spacer pushes buttons to the right on wide screens */}
          <div style={{ flex: 1, minWidth: 16 }} />

          {/* Action buttons */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <button
              className="btn-primary"
              onClick={() => triggerPipeline("sales")}
              disabled={pipelineTriggering.sales || !isSalesConfigured}
              title={!isSalesConfigured ? "Set up the Sales folder in Advanced Setup below" : undefined}
              style={{
                padding: "10px 20px",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 14,
                border: "none",
                cursor: !isSalesConfigured ? "not-allowed" : "pointer",
              }}
            >
              {pipelineTriggering.sales
                ? <Loader size={15} className="animate-spin" />
                : <ArrowDownToLine size={15} />}
              Import Sales
            </button>

            <button
              className="btn-primary"
              onClick={() => triggerPipeline("purchase")}
              disabled={pipelineTriggering.purchase || !isPurchaseConfigured}
              title={!isPurchaseConfigured ? "Set up the Purchase folder in Advanced Setup below" : undefined}
              style={{
                padding: "10px 20px",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 14,
                border: "none",
                cursor: !isPurchaseConfigured ? "not-allowed" : "pointer",
              }}
            >
              {pipelineTriggering.purchase
                ? <Loader size={15} className="animate-spin" />
                : <ArrowDownToLine size={15} />}
              Import Purchase
            </button>

            <button
              className="btn-primary"
              onClick={() => triggerPipeline("gstr2b")}
              disabled={pipelineTriggering.gstr2b || !isGstr2bConfigured}
              title={!isGstr2bConfigured ? "Set up the GSTR-2B folder in Advanced Setup below" : undefined}
              style={{
                padding: "10px 20px",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 14,
                border: "none",
                background: "var(--green)",
                cursor: !isGstr2bConfigured ? "not-allowed" : "pointer",
              }}
            >
              {pipelineTriggering.gstr2b
                ? <Loader size={15} className="animate-spin" />
                : <ShieldCheck size={15} />}
              Import GSTR-2B
            </button>
          </div>
        </div>

        {/* Setup prompt when nothing is configured */}
        {!anyConfigured && (
          <div style={{
            marginTop: 16,
            padding: "12px 16px",
            background: "var(--amber-soft)",
            borderRadius: "var(--radius-sm)",
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            color: "var(--amber)",
          }}>
            <AlertTriangle size={15} />
            No Drive folders configured yet. Open Advanced Setup below to connect your folders.
          </div>
        )}
      </div>

      {/* ── Zone 2: Live Status (shown when tasks are running) ──────────── */}
      {activePipelines.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
          {activePipelines.map(pipeline => {
            const status = pipelineStatuses[pipeline];
            const taskId = pipelineTaskIds[pipeline];
            const label = PIPELINE_LABELS[pipeline];
            const progressText = status?.status === "STARTED" && status.result
              ? `${status.result.processed_files} of ${status.result.total_files_found} processed`
              : status?.status === "PENDING"
                ? "Queued, waiting to start..."
                : "Connecting to Google Drive...";

            return (
              <div
                key={pipeline}
                className="glass"
                style={{
                  borderRadius: "var(--radius-lg)",
                  padding: "20px 24px",
                  borderLeft: "4px solid var(--accent)",
                }}
              >
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 16,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1 }}>
                    <Loader size={18} className="animate-spin" style={{ color: "var(--accent)", flexShrink: 0 }} />
                    <div>
                      <p style={{ fontSize: 14, fontWeight: 600, margin: 0, color: "var(--text-primary)" }}>
                        Importing {selectedMonthLabel} {label.toLowerCase()}...
                      </p>
                      <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "4px 0 0" }}>
                        {progressText}
                      </p>
                    </div>
                  </div>

                  {/* STOP button */}
                  {taskId && (
                    <button
                      onClick={() => cancelPipeline(pipeline)}
                      style={{
                        padding: "8px 18px",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 13,
                        fontWeight: 600,
                        background: "var(--red)",
                        color: "#fff",
                        border: "none",
                        borderRadius: "var(--radius-sm)",
                        cursor: "pointer",
                        flexShrink: 0,
                      }}
                    >
                      <StopCircle size={15} />
                      Stop
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Completed pipeline results (shown after a pipeline finishes) ── */}
      {(["sales", "purchase", "gstr2b"] as Pipeline[]).map(pipeline => {
        const status = pipelineStatuses[pipeline];
        if (!status) return null;
        if (status.status === "PENDING" || status.status === "STARTED") return null;

        const label = PIPELINE_LABELS[pipeline];
        const error = pipelineErrors[pipeline];

        if (status.status === "FAILURE") {
          return (
            <div
              key={`result-${pipeline}`}
              className="glass"
              style={{
                borderRadius: "var(--radius-lg)",
                padding: "16px 24px",
                marginBottom: 12,
                borderLeft: "4px solid var(--red)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <AlertCircle size={16} style={{ color: "var(--red)", flexShrink: 0 }} />
                <div>
                  <p style={{ fontSize: 14, fontWeight: 600, margin: 0, color: "var(--red)" }}>
                    {label} import failed
                  </p>
                  <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "2px 0 0" }}>
                    {error || status.error || "An unexpected error occurred."}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setPipelineStatuses(prev => ({ ...prev, [pipeline]: null }));
                    setPipelineErrors(prev => ({ ...prev, [pipeline]: null }));
                  }}
                  className="btn-ghost"
                  style={{ marginLeft: "auto", padding: "6px 12px", fontSize: 12, border: "none", cursor: "pointer" }}
                >
                  Dismiss
                </button>
              </div>
            </div>
          );
        }

        if (status.status === "SUCCESS" && status.result) {
          const r = status.result;
          const skipped = r.total_files_found - r.processed_files - r.failed_files;
          return (
            <div
              key={`result-${pipeline}`}
              className="glass"
              style={{
                borderRadius: "var(--radius-lg)",
                padding: "20px 24px",
                marginBottom: 12,
                borderLeft: "4px solid var(--green)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <CheckCircle size={16} style={{ color: "var(--green)" }} />
                  <p style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>
                    {label} import complete
                  </p>
                </div>
                <button
                  onClick={() => setPipelineStatuses(prev => ({ ...prev, [pipeline]: null }))}
                  className="btn-ghost"
                  style={{ padding: "4px 10px", fontSize: 12, border: "none", cursor: "pointer" }}
                >
                  Dismiss
                </button>
              </div>

              <p style={{ fontSize: 14, color: "var(--text-secondary)", margin: "0 0 16px" }}>
                {r.processed_files} new invoice{r.processed_files !== 1 ? "s" : ""} imported
                {skipped > 0 ? `, ${skipped} already existed (skipped)` : ""}
                {r.failed_files > 0 ? `, ${r.failed_files} could not be read` : ""}
                {r.duration_seconds ? ` in ${r.duration_seconds.toFixed(0)}s` : ""}.
              </p>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                <MetricCard label="Found" value={r.total_files_found} />
                <MetricCard label="Imported" value={r.processed_files} color="var(--green)" />
                <MetricCard label="Errors" value={r.failed_files} color={r.failed_files > 0 ? "var(--red)" : undefined} />
              </div>

              {r.batch_id && (
                <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
                  {(pipeline === "sales" || pipeline === "gstr2b") && (
                    <button
                      className="btn-ghost"
                      onClick={() => downloadExcel(r.batch_id, "sales")}
                      style={{ padding: "8px 16px", fontSize: 13, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                    >
                      <FileSpreadsheet size={14} /> Download Sales Excel
                    </button>
                  )}
                  {pipeline === "purchase" && (
                    <button
                      className="btn-ghost"
                      onClick={() => downloadExcel(r.batch_id, "purchase")}
                      style={{ padding: "8px 16px", fontSize: 13, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                    >
                      <FileSpreadsheet size={14} /> Download Purchase Excel
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        }

        return null;
      })}

      {/* ── Zone 3: Results & History ───────────────────────────────────── */}
      <div
        className="glass"
        style={{
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          marginBottom: 20,
        }}
      >
        {/* Latest completed sync */}
        {latestJob && (
          <div style={{
            padding: "20px 24px",
            borderBottom: "1px solid var(--border)",
          }}>
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <CheckCircle size={16} style={{ color: "var(--green)" }} />
                <div>
                  <p style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>
                    Last import: {latestJob.processed_files} invoices extracted
                  </p>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "2px 0 0" }}>
                    {new Date(latestJob.sync_timestamp).toLocaleString("en-IN", {
                      day: "numeric", month: "short", year: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </p>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className="btn-ghost"
                  onClick={() => downloadExcel(latestJob.batch_id, "sales")}
                  style={{ padding: "8px 14px", fontSize: 13, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                >
                  <Download size={14} /> Sales Excel
                </button>
                <button
                  className="btn-ghost"
                  onClick={() => downloadExcel(latestJob.batch_id, "purchase")}
                  style={{ padding: "8px 14px", fontSize: 13, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                >
                  <Download size={14} /> Purchase Excel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* History header */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 24px",
          borderBottom: history.length > 0 ? "1px solid var(--border)" : "none",
        }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Import History</h2>
          <button
            onClick={loadHistory}
            className="btn-ghost"
            style={{ padding: "4px 8px", border: "none", background: "none", cursor: "pointer" }}
          >
            <RefreshCw size={14} className={historyLoading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* History rows */}
        {historyLoading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 14, padding: "32px 24px", textAlign: "center" }}>
            Loading...
          </div>
        ) : history.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 14, padding: "32px 24px", textAlign: "center" }}>
            No imports yet. Use the buttons above to get started.
          </div>
        ) : (
          <div>
            {history.map((job, i) => (
              <div
                key={job.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "12px 24px",
                  borderBottom: i < history.length - 1 ? "1px solid var(--border)" : "none",
                  flexWrap: "wrap",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 13 }}>
                  <span style={{ color: "var(--text-secondary)", minWidth: 140 }}>
                    {new Date(job.sync_timestamp).toLocaleString("en-IN", {
                      day: "numeric", month: "short", year: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                  <StatusBadge status={job.status} />
                  <span style={{ color: "var(--text-primary)" }}>
                    {job.processed_files} imported
                  </span>
                  {job.failed_files > 0 && (
                    <span style={{ color: "var(--red)" }}>
                      {job.failed_files} failed
                    </span>
                  )}
                </div>
                {job.status === "completed" && job.processed_files > 0 && (
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="btn-ghost"
                      onClick={() => downloadExcel(job.batch_id, "sales")}
                      style={{ padding: "4px 10px", fontSize: 12, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}
                    >
                      <Download size={12} /> Sales
                    </button>
                    <button
                      className="btn-ghost"
                      onClick={() => downloadExcel(job.batch_id, "purchase")}
                      style={{ padding: "4px 10px", fontSize: 12, display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}
                    >
                      <Download size={12} /> Purchase
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Advanced Setup (collapsed) ──────────────────────────────────── */}
      <details
        style={{ marginBottom: 32 }}
      >
        <summary
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--text-secondary)",
            padding: "12px 0",
            userSelect: "none",
            listStyle: "none",
          }}
        >
          <Settings size={16} />
          Advanced Setup
          <ChevronDown size={14} style={{ marginLeft: 4 }} />
        </summary>

        <div
          className="glass"
          style={{
            borderRadius: "var(--radius-lg)",
            padding: "24px 28px",
            marginTop: 8,
          }}
        >
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 20px" }}>
            Connect your Google Drive folders so AuditOS knows where to find each month&apos;s invoices.
            Paste the full folder URL or just the folder ID.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {/* Sales folder */}
            <div>
              <label style={labelStyle}>
                Sales invoices folder
                {isSalesConfigured && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: "var(--green)", fontWeight: 600 }}>
                    Connected
                  </span>
                )}
              </label>
              <input
                type="text"
                value={salesRootFolder}
                onChange={e => setSalesRootFolder(e.target.value)}
                placeholder="Google Drive folder URL or ID"
                style={inputStyle}
              />
            </div>

            {/* Purchase folder */}
            <div>
              <label style={labelStyle}>
                Purchase invoices folder
                {isPurchaseConfigured && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: "var(--green)", fontWeight: 600 }}>
                    Connected
                  </span>
                )}
              </label>
              <input
                type="text"
                value={purchaseRootFolder}
                onChange={e => setPurchaseRootFolder(e.target.value)}
                placeholder="Google Drive folder URL or ID"
                style={inputStyle}
              />
            </div>

            {/* GSTR-2B folder */}
            <div>
              <label style={labelStyle}>
                GSTR-2B files folder
                {isGstr2bConfigured && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: "var(--green)", fontWeight: 600 }}>
                    Connected
                  </span>
                )}
              </label>
              <input
                type="text"
                value={gstr2bRootFolder}
                onChange={e => setGstr2bRootFolder(e.target.value)}
                placeholder="Google Drive folder URL or ID"
                style={inputStyle}
              />
            </div>

            {/* Legacy base folder (hidden label) */}
            <div>
              <label style={labelStyle}>
                Base folder (optional)
                {savedConfig?.folder_id && (
                  <span style={{ marginLeft: 8, fontSize: 11, color: "var(--green)", fontWeight: 600 }}>
                    Connected
                  </span>
                )}
              </label>
              <input
                type="text"
                value={folderInput}
                onChange={e => setFolderInput(e.target.value)}
                placeholder="Google Drive folder URL or ID"
                style={inputStyle}
              />
            </div>

            {/* Fiscal year start */}
            <div>
              <label style={labelStyle}>Fiscal year starts in</label>
              <select
                value={fiscalYearStartMonth}
                onChange={e => setFiscalYearStartMonth(Number(e.target.value))}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                {["January","February","March","April","May","June","July","August","September","October","November","December"].map((m, i) => (
                  <option key={m} value={i + 1}>{m}</option>
                ))}
              </select>
            </div>

            {/* Month folder pattern */}
            <div>
              <label style={labelStyle}>Month folder naming pattern</label>
              <input
                type="text"
                value={monthFolderPattern}
                onChange={e => setMonthFolderPattern(e.target.value)}
                style={{ ...inputStyle, fontFamily: "var(--font-mono)" }}
              />
              <p style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>
                e.g. &quot;1. April 2026&quot;, &quot;2. May 2026&quot;
              </p>
            </div>

            {/* Invoice type */}
            <div>
              <label style={labelStyle}>Default invoice type</label>
              <select
                value={invoiceType}
                onChange={e => setInvoiceType(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                <option value="both">Both (Sales + Purchase)</option>
                <option value="sales">Sales only</option>
                <option value="purchase">Purchase only</option>
              </select>
            </div>

            {/* Schedule (hidden behind a plain label) */}
            <div>
              <label style={labelStyle}>Auto-sync schedule</label>
              <input
                type="text"
                value={schedule}
                onChange={e => setSchedule(e.target.value)}
                style={{ ...inputStyle, fontFamily: "var(--font-mono)" }}
              />
              <p style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>
                Cron expression for automatic imports
              </p>
            </div>
          </div>

          {/* Save button */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <button
              className="btn-primary"
              onClick={handleSaveConfig}
              disabled={configSaving}
              style={{
                padding: "10px 24px",
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 14,
                border: "none",
                cursor: configSaving ? "not-allowed" : "pointer",
              }}
            >
              {configSaving ? <Loader size={14} className="animate-spin" /> : <FolderOpen size={14} />}
              {configSaving ? "Saving..." : "Save Settings"}
            </button>
            {configMsg && (
              <span style={{
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 6,
                color: configMsg.ok ? "var(--green)" : "var(--red)",
              }}>
                {configMsg.ok ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                {configMsg.text}
              </span>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}
