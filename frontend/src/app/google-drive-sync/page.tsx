"use client";

import React, { useState, useEffect } from "react";
import {
  Cloud,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  Download,
  History,
  Play,
  Loader,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SyncJob {
  id: string;
  sync_timestamp: string;
  total_files_found: number;
  new_files: number;
  updated_files: number;
  processed_files: number;
  failed_files: number;
  status: "in_progress" | "completed" | "failed";
  excel_output_path: string | null;
  completed_at: string | null;
}

interface TaskStatus {
  task_id: string;
  status: "PENDING" | "PROGRESS" | "SUCCESS" | "FAILURE";
  result?: any;
  error?: string;
}

export default function GoogleDriveSyncPage() {
  const [folderUrl, setFolderUrl] = useState(
    "https://drive.google.com/drive/folders/1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq"
  );
  const [excelPath, setExcelPath] = useState("/data/invoices_output.xlsx");
  const [invoiceType, setInvoiceType] = useState("both");

  const [isLoading, setIsLoading] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [syncHistory, setSyncHistory] = useState<SyncJob[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Poll for task status
  useEffect(() => {
    if (!currentTaskId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/google-drive-sync/status/${currentTaskId}`,
          {
            headers: {
              Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}`,
            },
          }
        );

        if (res.ok) {
          const data = await res.json();
          setTaskStatus(data);

          // Stop polling if task completed or failed
          if (data.status === "SUCCESS" || data.status === "FAILURE") {
            clearInterval(interval);
            if (data.status === "SUCCESS") {
              setSuccess("✅ Sync completed successfully!");
              fetchHistory();
            } else {
              setError(`❌ Sync failed: ${data.error}`);
            }
          }
        }
      } catch (e) {
        console.error("Failed to get task status:", e);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [currentTaskId]);

  const fetchHistory = async () => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/google-drive-sync/history`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}`,
          },
        }
      );

      if (res.ok) {
        const data = await res.json();
        setSyncHistory(data.sync_jobs || []);
      }
    } catch (e) {
      console.error("Failed to fetch sync history:", e);
    }
  };

  const triggerSync = async () => {
    setError(null);
    setSuccess(null);
    setIsLoading(true);

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/google-drive-sync/trigger`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}`,
          },
          body: JSON.stringify({
            google_drive_folder_id: "1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq",
            excel_output_path: excelPath,
            invoice_type: invoiceType,
            model_config: null,
          }),
        }
      );

      if (res.ok) {
        const data = await res.json();
        setCurrentTaskId(data.task_id);
        setSuccess(`📋 Sync started! Task ID: ${data.task_id}`);
      } else {
        const errData = await res.json();
        setError(errData.detail || "Failed to start sync");
      }
    } catch (e: any) {
      setError(e.message || "Failed to start sync");
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "text-green-600";
      case "failed":
        return "text-red-600";
      case "in_progress":
        return "text-blue-600";
      default:
        return "text-gray-600";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="w-5 h-5 text-green-600" />;
      case "failed":
        return <AlertCircle className="w-5 h-5 text-red-600" />;
      case "in_progress":
        return <Loader className="w-5 h-5 text-blue-600 animate-spin" />;
      default:
        return <Clock className="w-5 h-5 text-gray-600" />;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Cloud className="w-8 h-8 text-blue-400" />
            <h1 className="text-4xl font-bold text-white">
              Google Drive Invoice Sync
            </h1>
          </div>
          <p className="text-gray-400">
            Automatically monitor and process invoices from client's Google Drive folder
          </p>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Sync Control Panel */}
          <div className="lg:col-span-2">
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 shadow-lg">
              <h2 className="text-xl font-semibold text-white mb-6 flex items-center gap-2">
                <Play className="w-5 h-5 text-blue-400" />
                Trigger Sync
              </h2>

              {/* Status Messages */}
              {error && (
                <div className="mb-6 p-4 bg-red-900/30 border border-red-700 rounded-lg">
                  <p className="text-red-300 text-sm">{error}</p>
                </div>
              )}

              {success && (
                <div className="mb-6 p-4 bg-green-900/30 border border-green-700 rounded-lg">
                  <p className="text-green-300 text-sm">{success}</p>
                </div>
              )}

              {/* Current Task Status */}
              {currentTaskId && taskStatus && (
                <div className="mb-6 p-4 bg-slate-700 rounded-lg border border-slate-600">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-gray-300 text-sm">Current Task</span>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(taskStatus.status)}
                      <span
                        className={`text-sm font-medium ${
                          taskStatus.status === "SUCCESS"
                            ? "text-green-400"
                            : taskStatus.status === "FAILURE"
                            ? "text-red-400"
                            : taskStatus.status === "PROGRESS"
                            ? "text-blue-400"
                            : "text-yellow-400"
                        }`}
                      >
                        {taskStatus.status}
                      </span>
                    </div>
                  </div>

                  <p className="text-gray-400 text-xs mb-3 font-mono break-all">
                    {currentTaskId}
                  </p>

                  {taskStatus.result && (
                    <div className="grid grid-cols-2 gap-2 text-xs text-gray-300">
                      <div>
                        <span className="text-gray-500">Total Files:</span>{" "}
                        {taskStatus.result.total_files_found}
                      </div>
                      <div>
                        <span className="text-gray-500">New:</span>{" "}
                        {taskStatus.result.new_files}
                      </div>
                      <div>
                        <span className="text-gray-500">Updated:</span>{" "}
                        {taskStatus.result.updated_files}
                      </div>
                      <div>
                        <span className="text-gray-500">Processed:</span>{" "}
                        {taskStatus.result.processed_files}
                      </div>
                      <div>
                        <span className="text-gray-500">Failed:</span>{" "}
                        {taskStatus.result.failed_files}
                      </div>
                      <div>
                        <span className="text-gray-500">Duration:</span>{" "}
                        {taskStatus.result.duration_seconds?.toFixed(1)}s
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Configuration */}
              <div className="space-y-4 mb-6">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    Google Drive Folder ID
                  </label>
                  <input
                    type="text"
                    disabled
                    value="1G29eZJyd2dttQ4ghy2xNdr_h8YssX2nq"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-gray-300 text-sm font-mono cursor-not-allowed"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    <a
                      href={folderUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:text-blue-300"
                    >
                      View folder
                    </a>
                  </p>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    Excel Output Path
                  </label>
                  <input
                    type="text"
                    value={excelPath}
                    onChange={(e) => setExcelPath(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-gray-300 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    Invoice Type
                  </label>
                  <select
                    value={invoiceType}
                    onChange={(e) => setInvoiceType(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-gray-300 text-sm"
                  >
                    <option value="both">Both (Sales & Purchase)</option>
                    <option value="sales">Sales Only</option>
                    <option value="purchase">Purchase Only</option>
                  </select>
                </div>
              </div>

              {/* Action Button */}
              <button
                onClick={triggerSync}
                disabled={isLoading || (currentTaskId && taskStatus?.status === "PROGRESS")}
                className={`w-full py-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all ${
                  isLoading || (currentTaskId && taskStatus?.status === "PROGRESS")
                    ? "bg-slate-600 text-gray-400 cursor-not-allowed"
                    : "bg-blue-600 hover:bg-blue-700 text-white active:scale-95"
                }`}
              >
                {isLoading || (currentTaskId && taskStatus?.status === "PROGRESS") ? (
                  <>
                    <Loader className="w-4 h-4 animate-spin" />
                    Sync In Progress...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    Start Sync Now
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Info Card */}
          <div className="lg:col-span-1">
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 shadow-lg">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-blue-400" />
                What Happens
              </h3>

              <ul className="space-y-3 text-sm text-gray-300">
                <li className="flex gap-2">
                  <span className="text-blue-400 font-bold">1.</span>
                  <span>Connects to Google Drive folder</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-blue-400 font-bold">2.</span>
                  <span>Lists all PDF files (& ZIPs)</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-blue-400 font-bold">3.</span>
                  <span>Checks for new/updated files</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-blue-400 font-bold">4.</span>
                  <span>Extracts invoice data via LLM</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-blue-400 font-bold">5.</span>
                  <span>Appends results to Excel</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-blue-400 font-bold">6.</span>
                  <span>Updates database audit log</span>
                </li>
              </ul>

              <div className="mt-6 p-3 bg-blue-900/20 border border-blue-700 rounded-lg">
                <p className="text-xs text-blue-300">
                  💡 <strong>Tip:</strong> First sync may take longer. Subsequent
                  syncs only process new/changed files.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Sync History */}
        <div className="mt-8">
          <button
            onClick={() => {
              setShowHistory(!showHistory);
              if (!showHistory) fetchHistory();
            }}
            className="flex items-center gap-2 text-blue-400 hover:text-blue-300 mb-4"
          >
            <History className="w-5 h-5" />
            {showHistory ? "Hide" : "Show"} Sync History
          </button>

          {showHistory && (
            <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden shadow-lg">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-700 border-b border-slate-600">
                    <tr>
                      <th className="px-4 py-3 text-left text-gray-300">
                        Timestamp
                      </th>
                      <th className="px-4 py-3 text-left text-gray-300">
                        Status
                      </th>
                      <th className="px-4 py-3 text-right text-gray-300">
                        Total
                      </th>
                      <th className="px-4 py-3 text-right text-gray-300">
                        New
                      </th>
                      <th className="px-4 py-3 text-right text-gray-300">
                        Processed
                      </th>
                      <th className="px-4 py-3 text-right text-gray-300">
                        Failed
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {syncHistory.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-6 text-center text-gray-400">
                          No sync history yet
                        </td>
                      </tr>
                    ) : (
                      syncHistory.map((job) => (
                        <tr
                          key={job.id}
                          className="hover:bg-slate-700/50 transition-colors"
                        >
                          <td className="px-4 py-3 text-gray-300">
                            {new Date(job.sync_timestamp).toLocaleString()}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              {getStatusIcon(job.status)}
                              <span className={`capitalize ${getStatusColor(job.status)}`}>
                                {job.status}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right text-gray-300">
                            {job.total_files_found}
                          </td>
                          <td className="px-4 py-3 text-right text-green-400">
                            {job.new_files}
                          </td>
                          <td className="px-4 py-3 text-right text-blue-400">
                            {job.processed_files}
                          </td>
                          <td className="px-4 py-3 text-right text-red-400">
                            {job.failed_files}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
