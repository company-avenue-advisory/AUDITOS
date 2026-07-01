"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Cloud, FolderOpen, RefreshCw, CheckCircle, AlertCircle,
  Clock, Download, Loader, Link, Settings, ChevronRight,
  FileText, AlertTriangle, Wifi, WifiOff,
} from "lucide-react";
import { apiRequest } from "@/utils/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface DriveConfig {
  folder_id: string;
  invoice_type: string;
  schedule: string;
  updated_at: string | null;
}

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
  // Accept bare ID or full Drive URL
  const match = input.match(/\/folders\/([a-zA-Z0-9_-]{10,})/);
  if (match) return match[1];
  // Bare ID: 28+ alphanumeric chars with no slashes
  if (/^[a-zA-Z0-9_-]{10,}$/.test(input.trim())) return input.trim();
  return "";
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
    completed:  { label: "Completed",  cls: "bg-green-900/40 text-green-300 border-green-700",  icon: <CheckCircle className="w-3.5 h-3.5" /> },
    failed:     { label: "Failed",     cls: "bg-red-900/40 text-red-300 border-red-700",         icon: <AlertCircle className="w-3.5 h-3.5" /> },
    in_progress:{ label: "In Progress",cls: "bg-blue-900/40 text-blue-300 border-blue-700",      icon: <Loader className="w-3.5 h-3.5 animate-spin" /> },
    SUCCESS:    { label: "Done",       cls: "bg-green-900/40 text-green-300 border-green-700",   icon: <CheckCircle className="w-3.5 h-3.5" /> },
    FAILURE:    { label: "Error",      cls: "bg-red-900/40 text-red-300 border-red-700",         icon: <AlertCircle className="w-3.5 h-3.5" /> },
    PENDING:    { label: "Queued",     cls: "bg-yellow-900/40 text-yellow-300 border-yellow-700",icon: <Clock className="w-3.5 h-3.5" /> },
    STARTED:    { label: "Running",    cls: "bg-blue-900/40 text-blue-300 border-blue-700",      icon: <Loader className="w-3.5 h-3.5 animate-spin" /> },
  };
  const s = map[status] ?? { label: status, cls: "bg-slate-700 text-gray-300 border-slate-600", icon: null };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium ${s.cls}`}>
      {s.icon}{s.label}
    </span>
  );
}

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="bg-slate-700/50 rounded-lg p-3 text-center">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-gray-400 mt-0.5">{label}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
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
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving]   = useState(false);
  const [configMsg, setConfigMsg]         = useState<{ ok: boolean; text: string } | null>(null);

  // Sync panel
  const [syncing, setSyncing]           = useState(false);
  const [taskId, setTaskId]             = useState<string | null>(null);
  const [taskStatus, setTaskStatus]     = useState<TaskStatus | null>(null);
  const [syncError, setSyncError]       = useState<string | null>(null);

  // History panel
  const [history, setHistory]           = useState<SyncJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ── Load saved config on mount ────────────────────────────────────────────

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const res = await apiRequest("/api/google-drive-sync/config");
      if (res.ok) {
        const data = await res.json();
        if (data.configured && data.config) {
          setSavedConfig(data.config);
          setFolderInput(data.config.folder_id);
          setInvoiceType(data.config.invoice_type);
          setSchedule(data.config.schedule ?? "0 0 1 * *");
        }
        // no_tenant: user has no firm yet — saving config will auto-create one
      }
    } finally {
      setConfigLoading(false);
    }
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

  // ── Poll task status ──────────────────────────────────────────────────────

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
        body: JSON.stringify({ folder_id: folderId, invoice_type: invoiceType, schedule }),
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

  const downloadExcel = (batchId: string, type: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : "";
    // Trigger download via anchor — token passed as query param since it's a GET download
    const url = `${API_BASE}/api/export/${batchId}?type=${type}&token=${token}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `sync_${batchId}.xlsx`;
    a.click();
  };

  const derivedFolderId = extractFolderIdFromUrl(folderInput);
  const isConfigured = !!savedConfig;
  const activeInvoiceType = savedConfig?.invoice_type ?? invoiceType;
  const latestJob = history.find(j => j.status === "completed");

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-600/20 rounded-lg border border-blue-500/30">
            <Cloud className="w-7 h-7 text-blue-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-white">Google Drive Sync</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Pull invoice PDFs from a client's Drive folder → extract → download Excel
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs">
            {isConfigured
              ? <><Wifi className="w-4 h-4 text-green-400" /><span className="text-green-400">Folder connected</span></>
              : <><WifiOff className="w-4 h-4 text-gray-500" /><span className="text-gray-500">Not configured</span></>
            }
          </div>
        </div>

        {/* ── Step 1: Configure ───────────────────────────────────────────── */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-700">
            <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">1</span>
            <Settings className="w-4 h-4 text-blue-400" />
            <h2 className="text-base font-semibold text-white">Connect Drive Folder</h2>
            {isConfigured && (
              <span className="ml-auto text-xs text-gray-500">
                Last updated {savedConfig?.updated_at ? new Date(savedConfig.updated_at).toLocaleDateString() : "—"}
              </span>
            )}
          </div>

          <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Folder URL */}
            <div className="md:col-span-2">
              <label className="block text-sm text-gray-400 mb-1.5">
                Google Drive Folder URL or ID
              </label>
              <div className="relative">
                <Link className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={folderInput}
                  onChange={e => setFolderInput(e.target.value)}
                  placeholder="https://drive.google.com/drive/folders/1G29eZJyd2d... or bare ID"
                  className="w-full pl-9 pr-4 py-2.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
              {folderInput && (
                <p className="mt-1 text-xs text-gray-500">
                  Folder ID: <span className={`font-mono ${derivedFolderId ? "text-green-400" : "text-red-400"}`}>
                    {derivedFolderId || "— invalid URL"}
                  </span>
                </p>
              )}
            </div>

            {/* Invoice type */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Invoice Type</label>
              <select
                value={invoiceType}
                onChange={e => setInvoiceType(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-blue-500"
              >
                <option value="both">Both (Sales + Purchase)</option>
                <option value="sales">Sales only</option>
                <option value="purchase">Purchase only</option>
              </select>
            </div>

            {/* Schedule */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Auto-sync Schedule (cron)</label>
              <input
                type="text"
                value={schedule}
                onChange={e => setSchedule(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-700 border border-slate-600 rounded-lg text-sm font-mono text-gray-200 focus:outline-none focus:border-blue-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                Default: 1st of every month at midnight UTC
              </p>
            </div>

            {/* Save button + feedback */}
            <div className="md:col-span-2 flex items-center gap-3">
              <button
                onClick={handleSaveConfig}
                disabled={configSaving || !folderInput}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
              >
                {configSaving ? <Loader className="w-4 h-4 animate-spin" /> : <FolderOpen className="w-4 h-4" />}
                {configSaving ? "Saving…" : "Save Configuration"}
              </button>
              {configMsg && (
                <span className={`text-sm flex items-center gap-1.5 ${configMsg.ok ? "text-green-400" : "text-red-400"}`}>
                  {configMsg.ok ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                  {configMsg.text}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ── Step 2: Sync Now ─────────────────────────────────────────────── */}
        <div className={`bg-slate-800 rounded-xl border overflow-hidden transition-opacity ${isConfigured ? "border-slate-700 opacity-100" : "border-slate-700/50 opacity-60 pointer-events-none"}`}>
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-700">
            <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">2</span>
            <RefreshCw className="w-4 h-4 text-blue-400" />
            <h2 className="text-base font-semibold text-white">Pull from Drive</h2>
            {!isConfigured && <span className="ml-2 text-xs text-gray-500">— complete step 1 first</span>}
          </div>

          <div className="p-5">
            {/* Config summary */}
            {isConfigured && (
              <div className="mb-4 flex flex-wrap gap-3 text-xs text-gray-400">
                <span className="flex items-center gap-1.5 bg-slate-700/50 px-3 py-1.5 rounded-lg">
                  <FolderOpen className="w-3.5 h-3.5 text-blue-400" />
                  <span className="font-mono text-blue-300">{savedConfig?.folder_id.slice(0, 16)}…</span>
                </span>
                <span className="flex items-center gap-1.5 bg-slate-700/50 px-3 py-1.5 rounded-lg">
                  <FileText className="w-3.5 h-3.5 text-purple-400" />
                  {savedConfig?.invoice_type}
                </span>
                <span className="flex items-center gap-1.5 bg-slate-700/50 px-3 py-1.5 rounded-lg">
                  <Clock className="w-3.5 h-3.5 text-gray-500" />
                  Auto: {savedConfig?.schedule}
                </span>
              </div>
            )}

            {/* Error banner */}
            {syncError && (
              <div className="mb-4 flex items-start gap-2 p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-sm text-red-300">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {syncError}
              </div>
            )}

            {/* Live task status */}
            {taskStatus && (
              <div className="mb-4 p-4 bg-slate-700/50 rounded-lg border border-slate-600">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm text-gray-300 font-medium">Sync in progress</span>
                  <StatusBadge status={taskStatus.status} />
                </div>

                {taskStatus.status === "PENDING" || taskStatus.status === "STARTED" ? (
                  <div className="flex items-center gap-2 text-sm text-blue-300">
                    <Loader className="w-4 h-4 animate-spin" />
                    Connecting to Google Drive and processing invoices…
                  </div>
                ) : taskStatus.status === "SUCCESS" && taskStatus.result ? (
                  <div className="grid grid-cols-3 gap-3">
                    <StatCard label="Found" value={taskStatus.result.total_files_found} sub="PDFs in folder" />
                    <StatCard label="Processed" value={taskStatus.result.processed_files} sub="new invoices" />
                    <StatCard label="Failed" value={taskStatus.result.failed_files} sub="errors" />
                  </div>
                ) : taskStatus.status === "FAILURE" ? (
                  <p className="text-sm text-red-300">{taskStatus.error}</p>
                ) : null}

                {taskStatus.status === "SUCCESS" && taskStatus.result?.duration_seconds && (
                  <p className="mt-2 text-xs text-gray-500">
                    Completed in {taskStatus.result.duration_seconds.toFixed(1)}s
                  </p>
                )}
              </div>
            )}

            {/* Trigger button */}
            <button
              onClick={handleTriggerSync}
              disabled={syncing || !isConfigured}
              className={`flex items-center gap-2 px-6 py-3 rounded-lg font-medium text-sm transition-all ${
                syncing
                  ? "bg-slate-600 text-gray-400 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 active:scale-95 text-white"
              }`}
            >
              {syncing ? <Loader className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              {syncing ? "Syncing…" : "Pull Invoices from Drive"}
            </button>
            <p className="mt-2 text-xs text-gray-500">
              Only new or changed PDFs are processed — already-synced files are skipped automatically.
            </p>
          </div>
        </div>

        {/* ── Step 3: Results & Download ───────────────────────────────────── */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-700">
            <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">3</span>
            <Download className="w-4 h-4 text-blue-400" />
            <h2 className="text-base font-semibold text-white">Download Results</h2>
            <button
              onClick={loadHistory}
              className="ml-auto p-1.5 text-gray-500 hover:text-gray-300 hover:bg-slate-700 rounded-lg transition-colors"
              title="Refresh history"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${historyLoading ? "animate-spin" : ""}`} />
            </button>
          </div>

          {/* Latest sync download CTA */}
          {latestJob && (
            <div className="mx-5 mt-4 p-4 bg-green-900/20 border border-green-700/40 rounded-lg flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-green-300">Latest sync complete</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {latestJob.processed_files} invoices extracted on {new Date(latestJob.sync_timestamp).toLocaleString()}
                </p>
              </div>
              <div className="flex gap-2">
                {(activeInvoiceType === "both" || activeInvoiceType === "sales") && (
                  <button
                    onClick={() => downloadExcel(latestJob.batch_id, "sales")}
                    className="flex items-center gap-1.5 px-3 py-2 bg-green-700 hover:bg-green-600 text-white text-xs font-medium rounded-lg transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Sales Excel
                  </button>
                )}
                {(activeInvoiceType === "both" || activeInvoiceType === "purchase") && (
                  <button
                    onClick={() => downloadExcel(latestJob.batch_id, "purchase")}
                    className="flex items-center gap-1.5 px-3 py-2 bg-purple-700 hover:bg-purple-600 text-white text-xs font-medium rounded-lg transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Purchase Excel
                  </button>
                )}
              </div>
            </div>
          )}

          {/* History table */}
          {historyLoading ? (
            <div className="flex items-center justify-center py-10 text-gray-500">
              <Loader className="w-5 h-5 animate-spin mr-2" /> Loading history…
            </div>
          ) : history.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-gray-500">
              <Cloud className="w-8 h-8 mb-2 opacity-30" />
              <p className="text-sm">No syncs yet — run your first pull above</p>
            </div>
          ) : (
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-gray-400 text-xs uppercase tracking-wide">
                    <th className="px-5 py-2.5 text-left">Timestamp</th>
                    <th className="px-3 py-2.5 text-center">Status</th>
                    <th className="px-3 py-2.5 text-right">Found</th>
                    <th className="px-3 py-2.5 text-right">New</th>
                    <th className="px-3 py-2.5 text-right">Processed</th>
                    <th className="px-3 py-2.5 text-right">Failed</th>
                    <th className="px-3 py-2.5 text-center">Download</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {history.map(job => (
                    <tr key={job.id} className="hover:bg-slate-700/30 transition-colors">
                      <td className="px-5 py-3 text-gray-300 whitespace-nowrap">
                        {new Date(job.sync_timestamp).toLocaleString()}
                      </td>
                      <td className="px-3 py-3 text-center">
                        <StatusBadge status={job.status} />
                      </td>
                      <td className="px-3 py-3 text-right text-gray-300">{job.total_files_found}</td>
                      <td className="px-3 py-3 text-right text-green-400">{job.new_files}</td>
                      <td className="px-3 py-3 text-right text-blue-400">{job.processed_files}</td>
                      <td className="px-3 py-3 text-right text-red-400">{job.failed_files}</td>
                      <td className="px-3 py-3 text-center">
                        {job.status === "completed" && job.processed_files > 0 ? (
                          <div className="flex items-center justify-center gap-1.5">
                            {(activeInvoiceType === "both" || activeInvoiceType === "sales") && (
                              <button
                                onClick={() => downloadExcel(job.batch_id, "sales")}
                                className="px-2 py-1 bg-green-800/60 hover:bg-green-700 text-green-300 text-xs rounded transition-colors flex items-center gap-1"
                              >
                                <Download className="w-3 h-3" /> Sales
                              </button>
                            )}
                            {(activeInvoiceType === "both" || activeInvoiceType === "purchase") && (
                              <button
                                onClick={() => downloadExcel(job.batch_id, "purchase")}
                                className="px-2 py-1 bg-purple-800/60 hover:bg-purple-700 text-purple-300 text-xs rounded transition-colors flex items-center gap-1"
                              >
                                <Download className="w-3 h-3" /> Purchase
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-600 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="h-4" />
        </div>

      </div>
    </div>
  );
}
