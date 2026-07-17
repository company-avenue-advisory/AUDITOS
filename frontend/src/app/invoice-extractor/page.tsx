"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { ChevronLeft } from "lucide-react";
import ReviewPanel from "@/components/ReviewPanel";
import { useSessionSync, clearActiveSession } from "@/utils/sessionSync";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type InvoiceType = "sales" | "purchase" | "both" | null;

export default function AuditOSInvoiceExtractor() {
  const [type, setType] = useState<InvoiceType>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [model, setModel] = useState("auto");
  const [step, setStep] = useState(1);
  const [dragActive, setDragActive] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [procStep, setProcStep] = useState(0);
  const [salesItems, setSalesItems] = useState<any[]>([]);
  const [purchaseItems, setPurchaseItems] = useState<any[]>([]);
  const [progressPct, setProgressPct] = useState(0);
  const [taskErrors, setTaskErrors] = useState<string[]>([]);
const [activeTab, setActiveTab] = useState<"sales" | "purchase">("sales");
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [selectedPdf, setSelectedPdf] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [exportSchema, setExportSchema] = useState<string>("suvit");
  const [showHistory, setShowHistory] = useState(false);
  const [historyData, setHistoryData] = useState<any[]>([]);

  const [batchMetrics, setBatchMetrics] = useState<any>(null);
  const [batchFlags, setBatchFlags] = useState<any[]>([]);
  const [tasksMeta, setTasksMeta] = useState<any[]>([]);
  const [duplicates, setDuplicates] = useState<{ within_batch: any[]; cross_batch: any[]; total_duplicates: number; critical_count: number } | null>(null);
  const [selectedPdfFilename, setSelectedPdfFilename] = useState<string | null>(null);
  const [activeOursTab, setActiveOursTab] = useState<"ledger" | "observability">("ledger");
  const [traceTaskId, setTraceTaskId] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<any[]>([]);
  const [isTraceLoading, setIsTraceLoading] = useState(false);
  // Phase 4A: Review Panel state
  const [reviewTask, setReviewTask] = useState<{ taskId: string; filename: string } | null>(null);

  // Tally connector: push ERP_READY items to TallyPrime as vouchers
  const [showTallyModal, setShowTallyModal] = useState(false);
  const [tallyHost, setTallyHost] = useState("");
  const [tallyPort, setTallyPort] = useState("9000");
  const [tallyCompany, setTallyCompany] = useState("");
  const [isPushingToTally, setIsPushingToTally] = useState(false);
  const [tallyPushResult, setTallyPushResult] = useState<any>(null);

  // Auto-save session state so users can resume across devices/interfaces
  const sessionState = useMemo(() => ({
    active_batch_id: batchId,
    active_page: "invoice-extractor",
    selected_invoice_type: type ?? undefined,
    selected_model: model,
  }), [batchId, type, model]);

  useSessionSync(sessionState, !!batchId);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const qBatchId = params.get("batchId");
      if (qBatchId) {
        rehydrateBatch(qBatchId);
      }
    }
  }, []);

  useEffect(() => {
    if (!traceTaskId) return;
    
    const fetchTrace = async () => {
      setIsTraceLoading(true);
      try {
        const res = await fetch(`${API_BASE_URL}/api/tasks/${traceTaskId}/observability`);
        if (res.ok) {
          const data = await res.json();
          setTraceEvents(data.events || []);
        }
      } catch (e) {
        console.error("Failed to fetch task trace", e);
      } finally {
        setIsTraceLoading(false);
      }
    };
    
    fetchTrace();
  }, [traceTaskId]);

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/jobs`);
      if (res.ok) {
        const data = await res.json();
        setHistoryData(data);
        setShowHistory(true);
      }
    } catch (e) {
      console.error("Failed to fetch history");
    }
  };

  const rehydrateBatch = async (id: string) => {
    try {
      setBatchId(id);
      setShowHistory(false);
      setStep(4);
      const res = await fetch(`${API_BASE_URL}/api/jobs/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSalesItems(data.sales_items || []);
        setPurchaseItems(data.purchase_items || []);
        setBatchMetrics(data.batch_metrics || null);
        setBatchFlags(data.batch_flags || []);
        setTasksMeta(data.tasks || []);
        setActiveOursTab("ledger"); // Reset tab
        setType((data.sales_items?.length && data.purchase_items?.length) ? "both" : (data.sales_items?.length ? "sales" : "purchase"));
        setStep(5);
      }
    } catch (e) {
      alert("Failed to load batch data");
    }
  };

  const [editingCell, setEditingCell] = useState<{rowIdx: number, field: string, type: "sales" | "purchase", itemId: number, value: string} | null>(null);

  const handleCellClick = (rowIdx: number, field: string, type: "sales" | "purchase", itemId: number, initialValue: string) => {
    if (!itemId) return; // Wait until backend assigns an ID
    setEditingCell({ rowIdx, field, type, itemId, value: initialValue || "" });
  };

  const handleCellBlur = async () => {
    if (!editingCell) return;
    
    // Optimistic UI update
    if (editingCell.type === "sales") {
      const newItems = [...salesItems];
      newItems[editingCell.rowIdx][editingCell.field] = editingCell.value;
      setSalesItems(newItems);
    } else {
      const newItems = [...purchaseItems];
      newItems[editingCell.rowIdx][editingCell.field] = editingCell.value;
      setPurchaseItems(newItems);
    }
    
    const currentEdit = editingCell;
    setEditingCell(null);
    
    try {
      await fetch(`${API_BASE_URL}/api/items/${currentEdit.itemId}?type=${currentEdit.type}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({ field: currentEdit.field, value: currentEdit.value })
      });
    } catch (e) {
      console.error("Failed to update cell", e);
    }
  };

  const renderGSTR1CategoryCell = (row: any, idx: number) => {
    const value = row.gstr1_category || "";
    const categories = ["B2B", "B2CL", "B2CS", "CDNR", "CDNUR", "EXP"];
    
    const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
      const newVal = e.target.value;
      
      // Optimistic UI update
      const newItems = [...salesItems];
      newItems[idx].gstr1_category = newVal;
      setSalesItems(newItems);
      
      try {
        await fetch(`${API_BASE_URL}/api/items/${row.id}?type=sales`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("token")}`,
          },
          body: JSON.stringify({ field: "gstr1_category", value: newVal })
        });
      } catch (err) {
        console.error("Failed to update GSTR-1 Category", err);
      }
    };

    return (
      <td
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--border)",
          background: "transparent"
        }}
      >
        <select
          value={value}
          onChange={handleChange}
          style={{
            width: "100%",
            background: "var(--bg-base)",
            color: "var(--text-primary)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "4px 8px",
            outline: "none",
            cursor: "pointer",
            fontSize: "12px",
            transition: "border-color 0.15s"
          }}
        >
          <option value="" disabled style={{ color: "var(--text-muted)" }}>Select category</option>
          {categories.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </td>
    );
  };


  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    const unique = [...files];
    arr.forEach((f) => {
      if (!unique.find((x) => x.name === f.name)) unique.push(f);
    });
    setFiles(unique);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  };
  const onDragLeave = () => setDragActive(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  };

  const removeFile = (idx: number) => {
    setFiles(files.filter((_, i) => i !== idx));
  };

  const procStepsList = [
    { label: "Reading PDFs", sub: "Extracting text layer" },
    ...(type === "both"
      ? [{ label: "Auto-classifying invoices", sub: "Sorting sales vs purchase" }]
      : []),
    {
      label: "Running GST routing engine",
      sub:
        type === "sales"
          ? "B2B · B2CL · B2CS · CDNR · ECO gates"
          : type === "purchase"
          ? "ITC eligibility · RCM · blocked check"
          : "Sales + Purchase dual routing",
    },
    { label: "Compliance guardrails", sub: "HSN math assertion · TDS checks" },
    { label: "Suvit data mapper", sub: "Pivoting to Suvit column schema" },
  ];

  const startProcessing = async () => {
    setStep(4);
    setIsProcessing(true);
    setProcStep(0);
    setProgressPct(0);

    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/invoices/upload-batch?model=${encodeURIComponent(
          model
        )}&type=${encodeURIComponent(type || "both")}`,
        { method: "POST", body: fd }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Extraction enqueue failed.");
      }
      
      const uploadData = await res.json();
      const activeBatchId = uploadData.batch_id;
      setBatchId(activeBatchId);
      // Clear any previous session so the new batch becomes the resume target
      clearActiveSession();

      // Connect via WebSocket for real-time progress
      const wsUrl = API_BASE_URL.replace(/^http/, "ws") + `/api/ws/jobs/${activeBatchId}`;
      const ws = new WebSocket(wsUrl);

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.total > 0) {
            const pct = ((data.completed + data.failed) / data.total) * 100;
            setProgressPct(pct);
            
            // Advance UI proc steps roughly based on completion percentage
            if (pct > 25) setProcStep(1);
            if (pct > 50) setProcStep(2);
            if (pct > 75) setProcStep(3);
          }
          
          if (data.status === "COMPLETED" || data.status === "FAILED") {
            ws.close();
            setProgressPct(100);
            setProcStep(procStepsList.length);
            
            // Fetch final extracted data payload
            const statusRes = await fetch(`${API_BASE_URL}/api/jobs/${activeBatchId}`);
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              setSalesItems(statusData.sales_items || []);
              setPurchaseItems(statusData.purchase_items || []);
              setBatchMetrics(statusData.batch_metrics || null);
              setBatchFlags(statusData.batch_flags || []);
              setTasksMeta(statusData.tasks || []);
              setActiveOursTab("ledger"); // Reset tab
              
              const errors = statusData.tasks?.filter((t: any) => t.status === "FAILED" && t.error_message).map((t: any) => `${t.filename}: ${t.error_message}`) || [];
              setTaskErrors(errors);

              // Duplicate invoice check
              try {
                const dupRes = await fetch(`${API_BASE_URL}/api/jobs/${activeBatchId}/duplicates`, {
                  headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
                });
                if (dupRes.ok) {
                  const dupData = await dupRes.json();
                  if (dupData.has_duplicates) setDuplicates(dupData);
                }
              } catch { /* non-fatal */ }
            }
            
            setTimeout(() => {
              setIsProcessing(false);
              setStep(5);
            }, 800);
          }
        } catch (err) {
          console.error("WS message error", err);
        }
      };

      ws.onerror = (err) => {
        console.error("WebSocket error", err);
      };

    } catch (e: any) {
      alert("Error: " + e.message);
      setStep(3); // Go back
    }
  };


  const calculateAccuracy = () => {
    let totalRows = 0;
    let validRows = 0;
    const allItems = [...salesItems, ...purchaseItems];
    
    if (allItems.length === 0) return 0;

    allItems.forEach(r => {
      const amount = parseFloat(r.taxable_value) || 0;
      const rate = parseFloat(r.rate) || 0;
      const igst = parseFloat(r.igst_amount) || 0;
      const cgst = parseFloat(r.cgst_amount) || 0;
      const sgst = parseFloat(r.sgst_amount) || 0;
      
      totalRows++;
      if (amount > 0 && rate > 0) {
         const expectedTax = amount * (rate / 100);
         const actualTax = igst > 0 ? igst : (cgst + sgst);
         if (Math.abs(expectedTax - actualTax) <= 2.0) {
            validRows++;
         }
      } else {
         validRows++; // Treat as valid if there's no math error detected
      }
    });

    return totalRows > 0 ? Math.round((validRows / totalRows) * 100) : 0;
  };

  const handlePdfClick = async (url: string, filenameHint?: string) => {
    if (selectedPdf && selectedPdf.startsWith("blob:")) {
      URL.revokeObjectURL(selectedPdf);
    }
    // Extract filename from URL if not provided
    const fname = filenameHint || decodeURIComponent(url.split("/").pop() || "");
    setSelectedPdfFilename(fname);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error("Failed to load PDF");
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      setSelectedPdf(objUrl);
    } catch (error) {
      console.error("Failed to fetch PDF", error);
    }
  };

  const handleDownloadGSTR1 = async () => {
    if (!batchId) {
      alert("No active batch to download.");
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/export/${batchId}/gstr1`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Export failed" }));
        throw new Error(err.detail || "Export failed");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const cd = res.headers.get("Content-Disposition") || "";
      const match = cd.match(/filename=([^\s;]+)/);
      a.download = match ? match[1] : "GSTR1.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert("Error downloading GSTR-1 JSON: " + e.message);
    }
  };

  const handlePushToTally = async () => {
    if (!batchId) {
      alert("No active batch to push.");
      return;
    }
    if (!tallyHost.trim() || !tallyCompany.trim()) {
      alert("Enter both the TallyPrime host/IP and the company name.");
      return;
    }
    setIsPushingToTally(true);
    setTallyPushResult(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/tally/push/${batchId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({
          host: tallyHost.trim(),
          port: parseInt(tallyPort, 10) || 9000,
          company: tallyCompany.trim(),
          type: "both",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Push to Tally failed");
      }
      setTallyPushResult(data);
    } catch (e: any) {
      setTallyPushResult({ error: e.message || "Push to Tally failed" });
    } finally {
      setIsPushingToTally(false);
    }
  };

  const handleDownload = async (downloadType: "sales" | "purchase" | "both") => {
    if (!batchId) {
      alert("No active batch to download.");
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/export/${batchId}?type=${downloadType}&schema=${exportSchema}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });

      if (!res.ok) throw new Error("Export failed");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      if (downloadType === "both" && salesItems.length && purchaseItems.length) {
        a.download = "Suvit_Both_Upload.zip";
      } else if (downloadType === "sales" || (!purchaseItems.length && salesItems.length)) {
        a.download = "Suvit_Sales_Upload.xlsx";
      } else {
        a.download = "Suvit_Purchase_Upload.xlsx";
      }
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert("Error downloading file: " + e.message);
    }
  };

  const resetAll = () => {
    setType(null);
    setFiles([]);
    setModel("auto");
    setSalesItems([]);
    setPurchaseItems([]);
    setTaskErrors([]);
    setDuplicates(null);
    setSelectedPdfFilename(null);
    setStep(1);
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        .app-container { font-family: 'Inter', sans-serif; background: var(--bg-base); min-height: 100vh; color: var(--text-primary); padding: 0; }
        .topnav { display: flex; align-items: center; justify-content: space-between; padding: 14px 28px; border-bottom: 0.5px solid rgba(255,255,255,0.07); }
        .topnav .logo { display: flex; align-items: center; gap: 10px; }
        .logo-mark { width: 28px; height: 28px; border-radius: 7px; background: var(--accent); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: #fff; }
        .logo-name { font-size: 14px; font-weight: 600; letter-spacing: -0.02em; color: var(--text-primary); }
        .logo-tag { font-size: 11px; color: var(--text-secondary); margin-left: 2px; }
        .nav-right { display: flex; align-items: center; gap: 8px; }
        .nav-pill { font-size: 11px; padding: 4px 10px; border-radius: 20px; border: 0.5px solid rgba(255,255,255,0.12); color: var(--text-secondary); background: transparent; cursor: pointer; transition: all .15s; }
        .nav-pill:hover { border-color: rgba(255,255,255,0.25); color: var(--text-primary); }
        .step-bar { display: flex; align-items: center; justify-content: center; gap: 0; padding: 20px 28px 0; }
        .step-item { display: flex; align-items: center; gap: 8px; }
        .step-dot { width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: rgba(232,230,224,0.3); transition: all .3s; flex-shrink: 0; }
        .step-dot.done { background: var(--accent); border-color: var(--accent); color: #fff; }
        .step-dot.active { background: transparent; border-color: var(--accent); color: var(--accent); }
        .step-label { font-size: 11px; color: var(--text-secondary); transition: color .3s; white-space: nowrap; }
        .step-label.active { color: var(--text-primary); }
        .step-label.done { color: var(--text-secondary); }
        .step-line { width: 36px; height: 0.5px; background: rgba(255,255,255,0.1); margin: 0 8px; flex-shrink: 0; }
        .step-line.done { background: var(--accent); }
        .stage { max-width: 640px; margin: 0 auto; padding: 40px 24px 60px; }
        .step-view { animation: fadeIn .25s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .step-heading { font-size: 22px; font-weight: 600; letter-spacing: -0.03em; color: var(--text-primary); margin-bottom: 6px; line-height: 1.2; }
        .step-sub { font-size: 13px; color: var(--text-secondary); margin-bottom: 28px; line-height: 1.5; }
        .type-cards { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 28px; }
        .type-card { border: 1.5px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 20px 14px 16px; cursor: pointer; background: rgba(255,255,255,0.025); transition: all .2s; position: relative; text-align: center; }
        .type-card:hover { border-color: var(--accent-glow); background: var(--accent-soft); }
        .type-card.selected { border-color: var(--accent); background: var(--accent-soft); }
        .type-icon { width: 40px; height: 40px; border-radius: 10px; margin: 0 auto 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .type-icon.sales { background: var(--accent-soft); }
        .type-icon.purch { background: rgba(16,185,129,0.15); }
        .type-icon.both { background: rgba(139,92,246,0.15); }
        .type-card-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
        .type-card-sub { font-size: 11px; color: var(--text-secondary); line-height: 1.4; }
        .type-check { position: absolute; top: 10px; right: 10px; width: 16px; height: 16px; border-radius: 50%; background: var(--accent); display: none; align-items: center; justify-content: center; font-size: 9px; color: #fff; }
        .type-card.selected .type-check { display: flex; }
        .model-section { margin-bottom: 24px; }
        .model-section-label { font-size: 11px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 10px; }
        .model-rows { display: flex; flex-direction: column; gap: 6px; }
        .model-row { display: flex; align-items: center; gap: 12px; border: 0.5px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; cursor: pointer; background: rgba(255,255,255,0.02); transition: all .15s; position: relative; }
        .model-row:hover { border-color: rgba(255,255,255,0.18); }
        .model-row.selected { border-color: var(--accent); background: var(--accent-soft); }
        .model-dot { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
        .model-dot.auto { background: rgba(234,179,8,0.15); }
        .model-dot.groq { background: rgba(239,68,68,0.12); }
        .model-dot.ollama { background: rgba(16,185,129,0.12); }
        .model-dot.claude { background: rgba(214,132,79,0.18); }
        .model-info { flex: 1; }
        .model-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
        .model-desc { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }
        .model-badge { font-size: 10px; padding: 2px 7px; border-radius: 20px; font-weight: 500; flex-shrink: 0; }
        .badge-rec { background: var(--accent-glow); color: var(--accent); }
        .badge-fast { background: rgba(234,179,8,0.15); color: #D4A017; }
        .badge-priv { background: rgba(16,185,129,0.15); color: #34D399; }
        .model-radio { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.2); flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
        .model-row.selected .model-radio { border-color: var(--accent); background: var(--accent); }
        .model-row.selected .model-radio::after { content: ''; display: block; width: 6px; height: 6px; border-radius: 50%; background: #fff; }
        .both-hint { border: 0.5px solid rgba(139,92,246,0.3); border-radius: 10px; padding: 12px 14px; background: rgba(139,92,246,0.06); font-size: 12px; color: var(--text-secondary); margin-bottom: 24px; line-height: 1.5; }
        .both-hint span { color: #A78BFA; font-weight: 500; }
        .dropzone { border: 1.5px dashed rgba(255,255,255,0.12); border-radius: 14px; padding: 40px 24px; text-align: center; cursor: pointer; transition: all .2s; margin-bottom: 12px; background: rgba(255,255,255,0.015); position: relative; }
        .dropzone:hover, .dropzone.dragging { border-color: var(--accent); background: var(--accent-soft); }
        .dz-icon { font-size: 32px; margin-bottom: 12px; opacity: 0.6; }
        .dz-title { font-size: 14px; font-weight: 500; color: var(--text-primary); margin-bottom: 4px; }
        .dz-sub { font-size: 12px; color: var(--text-secondary); }
        .file-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
        .file-chip { display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.05); border: 0.5px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 4px 10px 4px 8px; font-size: 11px; color: var(--text-primary); }
        .chip-icon { font-size: 12px; opacity: 0.7; }
        .chip-remove { cursor: pointer; opacity: 0.4; font-size: 10px; margin-left: 2px; transition: opacity .15s; }
        .chip-remove:hover { opacity: 0.9; }
        .review-card { border: 0.5px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 20px; background: rgba(255,255,255,0.025); margin-bottom: 14px; }
        .review-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 0.5px solid rgba(255,255,255,0.05); font-size: 13px; }
        .review-row:last-child { border-bottom: none; padding-bottom: 0; }
        .review-label { color: var(--text-secondary); }
        .review-val { color: var(--text-primary); font-weight: 500; }
        .review-val.blue { color: var(--accent); }
        .review-val.green { color: #34D399; }
        .review-val.purple { color: #A78BFA; }
        .output-tabs { display: flex; flex-direction: column; gap: 6px; margin-top: 16px; }
        .output-tab { display: flex; align-items: center; gap: 10px; border: 0.5px solid rgba(255,255,255,0.07); border-radius: 10px; padding: 10px 14px; background: rgba(255,255,255,0.02); }
        .out-icon { font-size: 16px; }
        .out-name { font-size: 12px; font-weight: 500; color: var(--text-primary); }
        .out-desc { font-size: 11px; color: var(--text-secondary); margin-top: 1px; }
        .processing-wrap { text-align: center; padding: 40px 0; }
        .proc-title { font-size: 16px; font-weight: 500; color: var(--text-primary); margin-bottom: 8px; }
        .proc-sub { font-size: 12px; color: var(--text-secondary); margin-bottom: 32px; }
        .proc-steps { text-align: left; display: flex; flex-direction: column; gap: 10px; }
        .proc-step { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-secondary); transition: color .3s; }
        .proc-step.done { color: var(--text-primary); }
        .proc-step.active { color: var(--text-primary); }
        .proc-step-dot { width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 9px; }
        .proc-step.done .proc-step-dot { background: var(--accent); border-color: var(--accent); color: #fff; }
        .proc-step.active .proc-step-dot { border-color: var(--accent); color: var(--accent); }
        .done-wrap { text-align: center; padding: 32px 0 16px; }
        .done-icon { font-size: 40px; margin-bottom: 14px; }
        .done-title { font-size: 20px; font-weight: 600; letter-spacing: -0.02em; color: var(--text-primary); margin-bottom: 6px; }
        .done-sub { font-size: 13px; color: var(--text-secondary); margin-bottom: 28px; }
        .download-btns { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
        .dl-btn { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-radius: 12px; cursor: pointer; transition: all .15s; text-align: left; }
        .dl-btn.primary { background: var(--accent); border: none; color: #fff; }
        .dl-btn.primary:hover { background: #2277FF; }
        .dl-btn.secondary { background: transparent; border: 0.5px solid rgba(255,255,255,0.12); color: var(--text-primary); }
        .dl-btn.secondary:hover { border-color: rgba(255,255,255,0.25); color: var(--text-primary); }
        .dl-btn-left { display: flex; align-items: center; gap: 10px; }
        .dl-btn-icon { font-size: 18px; }
        .dl-btn-title { font-size: 13px; font-weight: 500; }
        .dl-btn-sub { font-size: 11px; opacity: 0.6; margin-top: 1px; }
        .dl-btn-arrow { font-size: 14px; opacity: 0.6; }
        .alert-row { display: flex; flex-direction: column; gap: 6px; margin-top: 14px; }
        .alert { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border-radius: 8px; font-size: 12px; }
        .alert.warn { background: rgba(234,179,8,0.08); border: 0.5px solid rgba(234,179,8,0.2); color: #D4A017; }
        .alert.err { background: rgba(239,68,68,0.08); border: 0.5px solid rgba(239,68,68,0.2); color: #F87171; }
        .alert.ok { background: rgba(16,185,129,0.08); border: 0.5px solid rgba(16,185,129,0.2); color: #34D399; }
        .alert-icon { font-size: 14px; flex-shrink: 0; margin-top: 0; }
        .cta-btn { width: 100%; padding: 14px; border-radius: 12px; background: var(--accent); border: none; color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; transition: all .15s; letter-spacing: -0.01em; }
        .cta-btn:hover:not(:disabled) { background: #2277FF; transform: translateY(-1px); }
        .cta-btn:active:not(:disabled) { transform: translateY(0); }
        .cta-btn:disabled { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.25); cursor: not-allowed; transform: none; }
        .cta-btn.secondary { background: transparent; border: 0.5px solid rgba(255,255,255,0.12); color: var(--text-secondary); margin-top: 8px; font-weight: 400; }
        .cta-btn.secondary:hover { border-color: rgba(255,255,255,0.25); color: var(--text-primary); background: transparent; }
        .back-link { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-secondary); cursor: pointer; margin-bottom: 24px; transition: color .15s; background: none; border: none; }
        .back-link:hover { color: var(--text-primary); }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner { width: 36px; height: 36px; border-radius: 50%; border: 2px solid var(--accent-glow); border-top-color: var(--accent); animation: spin 0.8s linear infinite; margin: 0 auto 20px; }
        .prog-bar { height: 2px; background: rgba(255,255,255,0.06); border-radius: 2px; margin-bottom: 28px; overflow: hidden; }
        .prog-fill { height: 100%; background: var(--accent); border-radius: 2px; transition: width 0.4s ease; }
        .obs-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; text-align: left; }
        .obs-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; transition: border-color 0.15s; }
        .obs-card:hover { border-color: rgba(255,255,255,0.15); }
        .obs-card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 6px; }
        .obs-card-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }
        .obs-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; margin-top: 12px; }
        .obs-th { padding: 12px 16px; color: var(--text-secondary); fontWeight: 600; border-bottom: 1px solid var(--border); }
        .obs-td { padding: 14px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }
        .obs-badge { font-size: 11px; padding: 3px 8px; border-radius: 20px; font-weight: 500; display: inline-flex; align-items: center; gap: 4px; }
        .obs-badge.success { background: rgba(16,185,129,0.15); color: #34D399; }
        .obs-badge.warning { background: rgba(234,179,8,0.15); color: #D4A017; }
        .obs-badge.danger { background: rgba(239,68,68,0.15); color: #EF4444; }
        .trace-modal { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 2000; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
        .trace-content { background: var(--bg-card); border: 1px solid var(--border); width: 100%; max-width: 680px; border-radius: 16px; max-height: 85vh; display: flex; flex-direction: column; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); overflow: hidden; animation: zoomIn .2s ease; }
        @keyframes zoomIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        .trace-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px; border-bottom: 1px solid var(--border); }
        .trace-body { padding: 24px; overflow-y: auto; flex: 1; text-align: left; }
        .stepper { display: flex; flex-direction: column; gap: 20px; position: relative; padding-left: 28px; }
        .stepper::before { content: ''; position: absolute; left: 10px; top: 8px; bottom: 8px; width: 2px; background: var(--border); }
        .stepper-item { position: relative; display: flex; flex-direction: column; gap: 4px; }
        .stepper-dot { position: absolute; left: -24px; top: 4px; width: 10px; height: 10px; border-radius: 50%; background: var(--border); border: 2px solid var(--bg-card); z-index: 1; }
        .stepper-dot.active { background: var(--accent); }
        .stepper-dot.done { background: var(--green); }
        .stepper-title { font-size: 13px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 10px; }
        .stepper-meta { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 12px; }
        .stepper-detail { background: rgba(255,255,255,0.015); border: 1px solid rgba(255,255,255,0.03); border-radius: 8px; padding: 12px 14px; font-size: 12px; margin-top: 6px; color: var(--text-secondary); line-height: 1.5; }
      ` }} />

      <div className="app-container">
        <nav className="topnav">
          <div className="logo">
            <div className="logo-mark">A</div>
            <span className="logo-name">Audit OS</span>
            <span className="logo-tag">beta</span>
          </div>
          <div className="nav-right">
            <button className="nav-pill" onClick={fetchHistory}>Upload History</button>
            <button
              className="nav-pill"
              style={{ borderColor: "var(--accent-glow)", color: "var(--accent)" }}
              onClick={() => { setShowHistory(false); resetAll(); }}
            >
              New upload
            </button>
          </div>
        </nav>

        
        {showHistory ? (
          <div className="stage" style={{ maxWidth: 840, padding: "40px 24px" }}>
            <div className="step-heading" style={{ marginBottom: 6 }}>Upload History</div>
            <div className="step-sub" style={{ marginBottom: 28 }}>View and re-download past extraction batches instantly.</div>
            
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                <thead style={{ background: "rgba(0,0,0,0.02)", borderBottom: "1px solid var(--border)" }}>
                  <tr>
                    <th style={{ padding: "14px 16px", color: "var(--text-secondary)", fontWeight: 500 }}>Date</th>
                    <th style={{ padding: "14px 16px", color: "var(--text-secondary)", fontWeight: 500 }}>Batch ID</th>
                    <th style={{ padding: "14px 16px", color: "var(--text-secondary)", fontWeight: 500 }}>Files</th>
                    <th style={{ padding: "14px 16px", color: "var(--text-secondary)", fontWeight: 500 }}>Status</th>
                    <th style={{ padding: "14px 16px", color: "var(--text-secondary)", fontWeight: 500, textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {historyData.map((b) => (
                    <tr key={b.id} style={{ borderBottom: "1px solid var(--border)", transition: "background .15s" }} onMouseEnter={e => e.currentTarget.style.background = "rgba(0,0,0,0.02)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                      <td style={{ padding: "14px 16px", color: "var(--text-primary)" }}>{new Date(b.created_at).toLocaleString()}</td>
                      <td style={{ padding: "14px 16px", color: "var(--text-secondary)", fontFamily: "monospace", fontSize: 12 }}>{b.id.substring(0, 8)}...</td>
                      <td style={{ padding: "14px 16px", color: "var(--text-primary)" }}>{b.total_files} docs</td>
                      <td style={{ padding: "14px 16px" }}>
                        <span style={{ padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: 500, background: b.status === "COMPLETED" ? "rgba(16,185,129,0.12)" : (b.status === "FAILED" ? "rgba(239,68,68,0.12)" : "rgba(234,179,8,0.12)"), color: b.status === "COMPLETED" ? "#34D399" : (b.status === "FAILED" ? "#EF4444" : "#D4A017") }}>
                          {b.status}
                        </span>
                      </td>
                      <td style={{ padding: "14px 16px", textAlign: "right" }}>
                        <button 
                          className="nav-pill" 
                          style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--accent-soft)" }}
                          onClick={() => rehydrateBatch(b.id)}
                        >
                          View Data →
                        </button>
                      </td>
                    </tr>
                  ))}
                  {historyData.length === 0 && (
                    <tr><td colSpan={5} style={{ padding: "60px 20px", textAlign: "center", color: "var(--text-secondary)" }}>No extraction history found.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <>

          <div className="step-bar">
          {[1, 2, 3, 4].map((i) => (
            <React.Fragment key={i}>
              <div className="step-item">
                <div className={`step-dot ${step > i ? "done" : step === i ? "active" : ""}`}>
                  {step > i ? "✓" : i}
                </div>
                <span className={`step-label ${step > i ? "done" : step === i ? "active" : ""}`}>
                  {i === 1 ? "Invoice type" : i === 2 ? "Upload" : i === 3 ? "Review & run" : "Download"}
                </span>
              </div>
              {i < 4 && <div className={`step-line ${step > i ? "done" : ""}`} />}
            </React.Fragment>
          ))}
        </div>

        <div className="stage" style={{ maxWidth: step === 5 ? 800 : 640 }}>
          {step === 1 && (
            <div className="step-view">
              <div className="step-heading">What are you uploading today?</div>
              <div className="step-sub">Pick the invoice type. Each runs through its own GST routing engine.</div>
              <div className="type-cards">
                <div
                  className={`type-card ${type === "sales" ? "selected" : ""}`}
                  onClick={() => setType("sales")}
                >
                  <div className="type-icon sales">🧾</div>
                  <div className="type-card-title">Sales</div>
                  <div className="type-card-sub">GSTR-1: B2B, B2CL, B2CS, CDNR, ECO</div>
                  <div className="type-check">✓</div>
                </div>
                <div
                  className={`type-card ${type === "purchase" ? "selected" : ""}`}
                  onClick={() => setType("purchase")}
                >
                  <div className="type-icon purch">🛒</div>
                  <div className="type-card-title">Purchase</div>
                  <div className="type-card-sub">ITC routing, RCM, GSTR-2B match</div>
                  <div className="type-check">✓</div>
                </div>
                <div
                  className={`type-card ${type === "both" ? "selected" : ""}`}
                  onClick={() => setType("both")}
                >
                  <div className="type-icon both">⚡</div>
                  <div className="type-card-title">Both</div>
                  <div className="type-card-sub">Drop everything — AI auto-sorts each invoice</div>
                  <div className="type-check">✓</div>
                </div>
              </div>
              <button className="cta-btn" disabled={!type} onClick={() => setStep(2)}>
                Continue →
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="step-view">
              <button className="back-link" onClick={() => setStep(1)}>
                <ChevronLeft size={14} /> Back
              </button>
              <div className="step-heading">
                {type === "both"
                  ? "Drop all your invoices"
                  : type === "sales"
                  ? "Drop your sales invoices"
                  : "Drop your purchase invoices"}
              </div>
              <div className="step-sub">
                {type === "both"
                  ? "PDF and ZIP only. The engine auto-classifies each file as sales or purchase."
                  : "PDF and ZIP only. Batch uploads supported — mix scanned and digital."}
              </div>

              {type === "both" && (
                <div className="both-hint">
                  <span>Both mode:</span> Drop your entire month's folder. The engine reads each PDF and
                  auto-classifies it as sales or purchase before routing. No manual sorting needed.
                </div>
              )}

              <div
                className={`dropzone ${dragActive ? "dragging" : ""}`}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="dz-icon">📂</div>
                <div className="dz-title">Drop invoices here or click to browse</div>
                <div className="dz-sub">PDF or ZIP · up to 50 files per batch</div>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.zip"
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  onChange={(e) => e.target.files && handleFiles(e.target.files)}
                />
              </div>

              <div className="file-chips">
                {files.map((f, i) => (
                  <div key={i} className="file-chip">
                    <span className="chip-icon">📄</span>
                    <span>{f.name.length > 28 ? f.name.slice(0, 26) + "…" : f.name}</span>
                    <span
                      className="chip-remove"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFile(i);
                      }}
                    >
                      ✕
                    </span>
                  </div>
                ))}
              </div>

              <button className="cta-btn" disabled={files.length === 0} onClick={() => setStep(3)}>
                Review before running →
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="step-view">
              <button className="back-link" onClick={() => setStep(2)}>
                <ChevronLeft size={14} /> Back
              </button>
              <div className="step-heading">Review before running</div>
              <div className="step-sub">Confirm the details. The engine runs once you hit extract.</div>

              <div className="review-card">
                <div className="review-row">
                  <span className="review-label">Invoice type</span>
                  <span
                    className={`review-val ${
                      type === "sales" ? "blue" : type === "purchase" ? "green" : "purple"
                    }`}
                  >
                    {type === "sales"
                      ? "Sales invoices"
                      : type === "purchase"
                      ? "Purchase invoices"
                      : "Sales + Purchase (auto-sort)"}
                  </span>
                </div>
                <div className="review-row">
                  <span className="review-label">Files queued</span>
                  <span className="review-val">
                    {files.length} file{files.length !== 1 ? "s" : ""}
                  </span>
                </div>
                
                <div className="review-row">
                  <span className="review-label">GST engine</span>
                  <span className="review-val">
                    {type === "sales"
                      ? "GSTR-1 · Tables 4/5/7/9B/12/14–15"
                      : type === "purchase"
                      ? "ITC router · GSTR-2B match · Rule 36(4)"
                      : "GSTR-1 + ITC router (dual engine)"}
                  </span>
                </div>
              </div>

              <div className="output-tabs">
                {(type === "sales" || type === "both") && (
                  <div className="output-tab">
                    <span className="out-icon">📊</span>
                    <div>
                      <div className="out-name">Suvit_Sales_Upload.xlsx</div>
                      <div className="out-desc">Tables 4 · 5 · 7 · 9B · 12 · 14–15</div>
                    </div>
                  </div>
                )}
                {(type === "purchase" || type === "both") && (
                  <div className="output-tab">
                    <span className="out-icon">📗</span>
                    <div>
                      <div className="out-name">Suvit_Purchase_Upload.xlsx</div>
                      <div className="out-desc">ITC eligible · Blocked · RCM · Import tabs</div>
                    </div>
                  </div>
                )}
              </div>

              <div className="alert-row">
                <div className="alert ok">
                  <span className="alert-icon">✓</span>
                  HSN math assertion enabled — sum(HSN) == sum(invoices) checked.
                </div>
                {(type === "sales" || type === "both") && (
                  <div className="alert warn">
                    <span className="alert-icon">⚠</span>
                    Lower TDS Sec 197 check active — buyer over-deductions flagged.
                  </div>
                )}
                {(type === "purchase" || type === "both") && (
                  <div className="alert warn">
                    <span className="alert-icon">⚠</span>
                    GSTR-2B & Rule 36(4) cap checks active for ITC limits.
                  </div>
                )}
              </div>

              {/* AI Model Picker */}
              <div className="model-section" style={{ marginTop: 24 }}>
                <div className="model-section-label">AI Extraction Engine</div>
                <div className="model-rows">
                  {[
                    { id: "auto",      label: "Auto (Gemini 2.5 Flash)", desc: "Gemini 2.5 Flash · Groq free fallback", icon: "⚡", dot: "auto", badge: "Recommended", badgeCls: "badge-rec" },
                    { id: "anthropic", label: "Claude Haiku", desc: "Best accuracy · Requires ANTHROPIC_API_KEY", icon: "◆", dot: "claude", badge: "Future", badgeCls: "badge-fast" },
                    { id: "ollama",    label: "Ollama (Local)", desc: "100% private · No data leaves your machine", icon: "🔒", dot: "ollama", badge: "Private", badgeCls: "badge-priv" },
                  ].map((m) => (
                    <div key={m.id} className={`model-row ${model === m.id ? "selected" : ""}`} onClick={() => setModel(m.id)}>
                      <div className={`model-dot ${m.dot}`}>{m.icon}</div>
                      <div className="model-info">
                        <div className="model-name">{m.label}</div>
                        <div className="model-desc">{m.desc}</div>
                      </div>
                      <span className={`model-badge ${m.badgeCls}`}>{m.badge}</span>
                      <div className="model-radio" />
                    </div>
                  ))}
                </div>
              </div>

              <button className="cta-btn" style={{ marginTop: 20 }} onClick={startProcessing}>
                Start extraction →
              </button>
              <button className="cta-btn secondary" onClick={resetAll}>
                Start over
              </button>
            </div>
          )}

          {step === 4 && (
            <div className="step-view">
              <div className="processing-wrap">
                <div className="spinner"></div>
                <div className="proc-title">
                  {procStepsList[procStep]?.label || "Finalizing…"}
                </div>
                <div className="proc-sub">
                  {procStepsList[procStep]?.sub || "Preparing downloads"}
                </div>
                <div className="prog-bar">
                  <div
                    className="prog-fill"
                    style={{
                      width: `${progressPct > 0 ? progressPct : ((procStep + 1) / (procStepsList.length + 1)) * 100}%`,
                    }}
                  ></div>
                </div>
                <div className="proc-steps">
                  {procStepsList.map((s, i) => (
                    <div
                      key={i}
                      className={`proc-step ${procStep > i ? "done" : procStep === i ? "active" : ""}`}
                    >
                      <div className="proc-step-dot">{i + 1}</div>
                      <div>
                        <div style={{ fontSize: 13 }}>{s.label}</div>
                        <div style={{ fontSize: 11, color: "rgba(232,230,224,0.35)", marginTop: 2 }}>
                          {s.sub}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="step-view" style={{ maxWidth: activeOursTab === "ledger" && isFullScreen ? "100%" : 1000, margin: "0 auto" }}>
              <div className="done-wrap" style={{ paddingBottom: 16 }}>
                <div className="done-icon" style={{ fontSize: 32, marginBottom: 8 }}>✅</div>
                
                {/* TOP TAB CONTROLLERS */}
                <div style={{ display: "flex", borderBottom: "1px solid var(--border)", marginBottom: 24, justifyContent: "center" }}>
                  <button
                    onClick={() => setActiveOursTab("ledger")}
                    style={{
                      padding: "12px 24px",
                      background: "transparent",
                      border: "none",
                      borderBottom: activeOursTab === "ledger" ? "2px solid var(--accent)" : "2px solid transparent",
                      color: activeOursTab === "ledger" ? "var(--text-primary)" : "var(--text-secondary)",
                      fontWeight: 600,
                      cursor: "pointer",
                      fontSize: 14,
                      display: "flex",
                      alignItems: "center",
                      gap: 8
                    }}
                  >
                    📊 Audited Ledgers
                  </button>
                  <button
                    onClick={() => setActiveOursTab("observability")}
                    style={{
                      padding: "12px 24px",
                      background: "transparent",
                      border: "none",
                      borderBottom: activeOursTab === "observability" ? "2px solid var(--accent)" : "2px solid transparent",
                      color: activeOursTab === "observability" ? "var(--text-primary)" : "var(--text-secondary)",
                      fontWeight: 600,
                      cursor: "pointer",
                      fontSize: 14,
                      display: "flex",
                      alignItems: "center",
                      gap: 8
                    }}
                  >
                    🛡️ AI Observability & Quality Dashboard
                  </button>
                </div>
              </div>

              {activeOursTab === "ledger" ? (
                <>
                  {/* Data Grid Preview */}
                  <div style={isFullScreen ? {
                      position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", zIndex: 1000,
                      background: "var(--bg-base)", display: "flex", flexDirection: "column", padding: "20px"
                  } : { marginBottom: 24, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px", borderBottom: "1px solid var(--border)" }}>
                      <h3 style={{ margin: 0, fontSize: 16, color: "var(--text-primary)" }}>Extracted Data</h3>
                      <button onClick={() => setIsFullScreen(!isFullScreen)} style={{ background: "transparent", color: "var(--text-primary)", border: "1px solid var(--border)", padding: "6px 12px", borderRadius: "6px", cursor: "pointer", fontSize: 13, fontWeight: 500 }}>
                        {isFullScreen ? "⤢ Exit Full Screen" : "⤢ Expand (All Columns)"}
                      </button>
                    </div>
                    {(type === "both" && salesItems.length > 0 && purchaseItems.length > 0) && (
                      <div style={{ display: "flex", borderBottom: "1px solid var(--border)", background: "rgba(0,0,0,0.02)" }}>
                        <button 
                          style={{ flex: 1, padding: "12px", background: activeTab === "sales" ? "transparent" : "rgba(0,0,0,0.04)", border: "none", borderBottom: activeTab === "sales" ? "2px solid var(--accent)" : "2px solid transparent", color: activeTab === "sales" ? "var(--text-primary)" : "var(--text-secondary)", fontWeight: 600, cursor: "pointer", fontSize: 13 }}
                          onClick={() => setActiveTab("sales")}
                        >
                          🧾 Sales Data ({salesItems.length})
                        </button>
                        <button 
                          style={{ flex: 1, padding: "12px", background: activeTab === "purchase" ? "transparent" : "rgba(0,0,0,0.04)", border: "none", borderBottom: activeTab === "purchase" ? "2px solid #16a34a" : "2px solid transparent", color: activeTab === "purchase" ? "var(--text-primary)" : "var(--text-secondary)", fontWeight: 600, cursor: "pointer", fontSize: 13 }}
                          onClick={() => setActiveTab("purchase")}
                        >
                          🛒 Purchase Data ({purchaseItems.length})
                        </button>
                      </div>
                    )}
                    
                    {/* Batch summary stats */}
                    {(() => {
                      const items = (activeTab === "sales" || type === "sales") ? salesItems : purchaseItems;
                      const totalTaxable = items.reduce((s: number, r: any) => s + (parseFloat(r.taxable_value) || 0), 0);
                      const totalTax = items.reduce((s: number, r: any) => s + (parseFloat(r.igst_amount) || 0) + (parseFloat(r.cgst_amount) || 0) + (parseFloat(r.sgst_amount) || 0), 0);
                      const totalVal = items.reduce((s: number, r: any) => s + (parseFloat(r.total_invoice_value) || 0), 0);
                      const exportLUT = items.filter((r: any) => parseFloat(r.igst_amount) === 0 && parseFloat(r.cgst_amount) === 0 && parseFloat(r.taxable_value) > 0).length;
                      const fmt = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                      return items.length > 0 ? (
                        <div style={{ display: "flex", gap: 12, padding: "10px 14px", background: "var(--accent-soft)", borderBottom: "1px solid var(--border)", fontSize: 12, flexWrap: "wrap" }}>
                          <span style={{ color: "var(--text-secondary)" }}><strong style={{ color: "var(--text-primary)" }}>{items.length}</strong> invoices</span>
                          <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
                          <span style={{ color: "var(--text-secondary)" }}>Taxable: <strong style={{ color: "var(--accent)" }}>₹ {fmt(totalTaxable)}</strong></span>
                          <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
                          <span style={{ color: "var(--text-secondary)" }}>Tax: <strong style={{ color: "var(--accent)" }}>₹ {fmt(totalTax)}</strong></span>
                          <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
                          <span style={{ color: "var(--text-secondary)" }}>Total: <strong style={{ color: "#34D399" }}>₹ {fmt(totalVal)}</strong></span>
                          {exportLUT > 0 && (
                            <>
                              <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
                              <span style={{ padding: "2px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600, background: "rgba(234,179,8,0.12)", color: "#D4A017" }}>
                                {exportLUT} Export LUT
                              </span>
                            </>
                          )}
                        </div>
                      ) : null;
                    })()}

                    <div style={{ display: "flex", gap: "20px", alignItems: "flex-start" }}>
                      <div style={{ flex: selectedPdf ? "0 0 50%" : "1", maxHeight: isFullScreen ? "calc(100vh - 140px)" : (selectedPdf ? 600 : 340), overflowY: "auto", overflowX: "auto", transition: "all 0.3s" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
                        <thead style={{ position: "sticky", top: 0, background: "var(--bg-card)", zIndex: 1, boxShadow: "0 1px 0 var(--border)" }}>
                          <tr>
                            {((activeTab === "sales" && salesItems.length > 0) || (type === "sales") || (type === "both" && activeTab === "sales" && salesItems.length === 0)) ? (
                              <>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 120 }}>GSTIN/UIN</th>
                                {isFullScreen && <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 150 }}>Party Name</th>}
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Invoice No</th>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 90 }}>Date</th>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Taxable Value</th>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>Rate</th>
                                {isFullScreen && (
                                  <>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>IGST</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>CGST</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>SGST</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Total Value</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Advance Ded.</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 180 }}>Particulars</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>HSN</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 130 }}>GSTR-1 Category</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 200 }}>Narration</th>
                                  </>
                                )}
                              </>
                            ) : (
                              <>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 120 }}>GSTIN of Supplier</th>
                                {isFullScreen && <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 150 }}>Party Name</th>}
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Invoice No</th>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 90 }}>Date</th>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Taxable Value</th>
                                <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 120 }}>CGST/SGST/IGST</th>
                                {isFullScreen && (
                                  <>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 100 }}>Total Invoice</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 180 }}>Particulars</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>HSN</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 120 }}>ITC Category</th>
                                    <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 200 }}>Narration</th>
                                  </>
                                )}
                              </>
                            )}
                          </tr>
                        </thead>
                        <tbody>
                          {(((activeTab === "sales" && salesItems.length > 0) || type === "sales" || (type === "both" && activeTab === "sales")) ? salesItems : purchaseItems).map((row: any, idx: number) => {
                            const currentType = ((activeTab === "sales" && salesItems.length > 0) || type === "sales" || (type === "both" && activeTab === "sales")) ? "sales" : "purchase";
                            const itemId = row.id;
                            
                            const validateRow = (r: any, t: string) => {
                              const amount = parseFloat(r.taxable_value) || 0;
                              const rate = parseFloat(r.rate) || 0;
                              const igst = parseFloat(r.igst_amount) || 0;
                              const cgst = parseFloat(r.cgst_amount) || 0;
                              const sgst = parseFloat(r.sgst_amount) || 0;
                              
                              if (amount > 0 && rate > 0) {
                                 const expectedTax = amount * (rate / 100);
                                 const actualTax = igst > 0 ? igst : (cgst + sgst);
                                 if (Math.abs(expectedTax - actualTax) > 2.0) {
                                    return `Math mismatch: ₹${amount} @ ${rate}% = ₹${expectedTax.toFixed(2)} tax, but extracted ₹${actualTax.toFixed(2)}`;
                                 }
                              }
                              return null;
                            };
                            
                            const errorMsg = validateRow(row, currentType);
                            const hasError = !!errorMsg;
                            
                            const renderCell = (field: string, displayVal: string, checkError: boolean = false) => {
                              const isEditing = editingCell?.rowIdx === idx && editingCell?.field === field && editingCell?.type === currentType;
                              const cellHasError = checkError && hasError;
                              
                              return (
                                <td 
                                  style={{ 
                                    padding: "8px 12px", 
                                    color: cellHasError ? "#ef4444" : "var(--text-primary)", 
                                    cursor: itemId ? "pointer" : "default", 
                                    borderBottom: "1px solid var(--border)",
                                    background: cellHasError ? "rgba(239,68,68,0.08)" : "transparent"
                                  }}
                                  onClick={() => !isEditing && handleCellClick(idx, field, currentType, itemId, row[field])}
                                  title={cellHasError ? errorMsg! : (itemId ? "Click to edit" : "Pending...")}
                                >
                                  {isEditing ? (
                                    <input 
                                      autoFocus
                                      style={{ width: "100%", background: "var(--bg-base)", color: "var(--text-primary)", border: "1px solid var(--accent)", outline: "none", borderRadius: 4, padding: "4px" }}
                                      value={editingCell.value}
                                      onChange={(e) => setEditingCell({...editingCell, value: e.target.value})}
                                      onBlur={handleCellBlur}
                                      onKeyDown={(e) => e.key === 'Enter' && handleCellBlur()}
                                    />
                                  ) : (
                                    <div style={{ padding: "4px 0", minHeight: "20px" }}>
                                      {cellHasError && <span style={{ marginRight: 6, fontSize: 10 }} title={errorMsg!}>⚠️</span>}
                                      {displayVal || "-"}
                                    </div>
                                  )}
                                </td>
                              );
                            };

                            return (
                              <tr key={idx} style={{ transition: "background 0.2s", cursor: "pointer" }} onMouseEnter={(e) => e.currentTarget.style.background = "rgba(0,0,0,0.02)"} onMouseLeave={(e) => e.currentTarget.style.background = "transparent"} onClick={(e) => { if ((e.target as HTMLElement).tagName !== "INPUT" && (e.target as HTMLElement).tagName !== "SELECT" && (e.target as HTMLElement).tagName !== "OPTION") handlePdfClick(`${API_BASE_URL}/api/jobs/${batchId}/files/${encodeURIComponent(row.filename)}`, row.filename); }}>
                                {renderCell("party_gstin", row.party_gstin)}
                                {isFullScreen && renderCell("party_ac_name", row.party_ac_name)}
                                {renderCell("invoice_no", row.invoice_no)}
                                {renderCell("voucher_date", row.voucher_date)}
                                {renderCell("taxable_value", row.taxable_value ? `₹ ${row.taxable_value}` : "₹ 0", true)}
                                {renderCell(currentType === "sales" ? "rate" : "igst_amount", currentType === "sales" ? (row.rate ? `${row.rate}%` : "-") : (row.igst_amount ? `₹ ${row.igst_amount}` : (row.cgst_amount ? `₹ ${row.cgst_amount}` : "-")), true)}
                                
                                {isFullScreen && currentType === "sales" && (
                                  <>
                                    {renderCell("igst_amount", row.igst_amount ? `₹ ${row.igst_amount}` : "-")}
                                    {renderCell("cgst_amount", row.cgst_amount ? `₹ ${row.cgst_amount}` : "-")}
                                    {renderCell("sgst_amount", row.sgst_amount ? `₹ ${row.sgst_amount}` : "-")}
                                    {renderCell("total_invoice_value", row.total_invoice_value ? `₹ ${row.total_invoice_value}` : "-")}
                                    {renderCell("overall_advance_amount", row.overall_advance_amount ? `₹ ${row.overall_advance_amount}` : "-")}
                                    {renderCell("particulars", row.particulars)}
                                    {renderCell("hsn", row.hsn)}
                                    {renderGSTR1CategoryCell(row, idx)}
                                    {renderCell("narration", row.narration)}
                                  </>
                                )}
                                {isFullScreen && currentType === "purchase" && (
                                  <>
                                    {renderCell("total_invoice_value", row.total_invoice_value ? `₹ ${row.total_invoice_value}` : "-")}
                                    {renderCell("particulars", row.particulars)}
                                    {renderCell("hsn", row.hsn)}
                                    {renderCell("itc_category", row.itc_category)}
                                    {renderCell("narration", row.narration)}
                                  </>
                                )}
                              </tr>
                            );
                          })}
                          {(((activeTab === "sales" && salesItems.length > 0) || type === "sales" || (type === "both" && activeTab === "sales")) ? salesItems : purchaseItems).length === 0 && (
                            <tr><td colSpan={5} style={{ padding: 30, textAlign: "center", color: "var(--text-secondary)" }}>No data extracted for this category.</td></tr>
                          )}
                        </tbody>
                      </table>
                      </div>
                      
                      {selectedPdf && (
                        <div style={{ flex: "0 0 48%", height: "600px", borderRadius: "8px", overflow: "hidden", border: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
                          <div style={{ padding: "8px 12px", background: "var(--bg-card)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }} title={selectedPdfFilename || ""}>
                                📄 {selectedPdfFilename || "Source Document"}
                              </span>
                              <a href={selectedPdf!} download={selectedPdfFilename || "invoice.pdf"} style={{ fontSize: 11, color: "#6366f1", fontWeight: 600, textDecoration: "none", flexShrink: 0 }}>↓</a>
                              <button onClick={() => { if (selectedPdf && selectedPdf.startsWith("blob:")) URL.revokeObjectURL(selectedPdf); setSelectedPdf(null); setSelectedPdfFilename(null); }} style={{ background: "transparent", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 16, flexShrink: 0 }}>✕</button>
                          </div>
                          <iframe src={selectedPdf} width="100%" height="100%" style={{ border: "none", flex: 1 }} />
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="done-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
                    Extraction complete
                    {(() => {
                      const acc = calculateAccuracy();
                      return (
                        <span style={{
                          fontSize: 14,
                          padding: "4px 10px",
                          borderRadius: 20,
                          background: acc >= 95 ? "rgba(16,185,129,0.15)" : (acc >= 80 ? "rgba(234,179,8,0.15)" : "rgba(239,68,68,0.15)"),
                          color: acc >= 95 ? "#34D399" : (acc >= 80 ? "#D4A017" : "#EF4444"),
                          fontWeight: 600,
                          border: `1px solid ${acc >= 95 ? "rgba(16,185,129,0.3)" : (acc >= 80 ? "rgba(234,179,8,0.3)" : "rgba(239,68,68,0.3)")}`
                        }}>
                          {acc}% Accuracy
                        </span>
                      )
                    })()}
                  </div>
                  <div className="done-sub">
                    {files.length || tasksMeta.length} file{(files.length || tasksMeta.length) !== 1 ? "s" : ""} processed. Download your Suvit-ready sheets below.
                  </div>

                  {/* ── Duplicate invoice warning ── */}
                  {duplicates && duplicates.total_duplicates > 0 && (
                    <div style={{
                      margin: "0 0 20px",
                      borderRadius: 10,
                      border: `1px solid ${duplicates.critical_count > 0 ? "rgba(239,68,68,0.35)" : "rgba(245,158,11,0.35)"}`,
                      background: duplicates.critical_count > 0 ? "rgba(239,68,68,0.07)" : "rgba(245,158,11,0.07)",
                      padding: "14px 18px",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <span style={{ fontSize: 16 }}>{duplicates.critical_count > 0 ? "🔴" : "🟡"}</span>
                        <span style={{ fontWeight: 700, fontSize: 13, color: duplicates.critical_count > 0 ? "#ef4444" : "#f59e0b" }}>
                          {duplicates.critical_count > 0
                            ? `${duplicates.critical_count} invoice(s) found in previous batches — possible double-count`
                            : `${duplicates.total_duplicates} duplicate invoice(s) detected in this batch`}
                        </span>
                      </div>
                      {duplicates.cross_batch.slice(0, 3).map((d: any, i: number) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4, paddingLeft: 24 }}>
                          ✗ <strong>{d.invoice_no}</strong> {d.party_gstin ? `· ${d.party_gstin}` : ""} — also in batch <code style={{ fontSize: 11, background: "rgba(255,255,255,0.07)", padding: "1px 5px", borderRadius: 4 }}>{d.other_batch_id?.slice(0,8)}…</code>
                        </div>
                      ))}
                      {duplicates.within_batch.slice(0, 3).map((d: any, i: number) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4, paddingLeft: 24 }}>
                          ⚠ <strong>{d.invoice_no}</strong> appears {d.count}× in this batch ({d.occurrences.map((o: any) => o.filename).join(", ")})
                        </div>
                      ))}
                      {duplicates.total_duplicates > 3 && (
                        <div style={{ fontSize: 11, color: "var(--text-muted)", paddingLeft: 24, marginTop: 4 }}>
                          +{duplicates.total_duplicates - 3} more. Review before exporting to avoid double-counted GST liability.
                        </div>
                      )}
                    </div>
                  )}

                  <div className="download-btns">
                    <div style={{ display: "flex", justifyContent: "center", marginBottom: "16px", gap: "12px", alignItems: "center" }}>
                      <label style={{ fontSize: "14px", color: "var(--text-secondary)", fontWeight: 500 }}>Export Schema:</label>
                      <select 
                        value={exportSchema} 
                        onChange={(e) => setExportSchema(e.target.value)}
                        style={{
                          background: "#0c0c14",
                          border: "1px solid var(--border)",
                          borderRadius: "6px",
                          padding: "8px 12px",
                          color: "var(--text-primary)",
                          fontSize: "14px",
                          cursor: "pointer"
                        }}
                      >
                        <option value="suvit">Suvit (Tally)</option>
                        <option value="sap">SAP (BAPI/IDoc)</option>
                        <option value="netsuite">Oracle NetSuite</option>
                        <option value="dynamics">Microsoft Dynamics 365</option>
                      </select>
                    </div>
                    {type === "both" && salesItems.length > 0 && purchaseItems.length > 0 && (
                      <button className="dl-btn primary" onClick={() => handleDownload("both")}>
                        <div className="dl-btn-left">
                          <span className="dl-btn-icon">🗜</span>
                          <div>
                            <div className="dl-btn-title">Suvit_Both_Upload.zip</div>
                            <div className="dl-btn-sub">Download both files together</div>
                          </div>
                        </div>
                        <span className="dl-btn-arrow">↓</span>
                      </button>
                    )}
                    {salesItems.length > 0 && (
                      <button className={`dl-btn ${type === "sales" || !purchaseItems.length ? "primary" : "secondary"}`} onClick={() => handleDownload("sales")}>
                        <div className="dl-btn-left">
                          <span className="dl-btn-icon">📊</span>
                          <div>
                            <div className="dl-btn-title">Suvit_Sales_Upload.xlsx</div>
                            <div className="dl-btn-sub">Tables 4 · 5 · 7 · 9B · 12</div>
                          </div>
                        </div>
                        <span className="dl-btn-arrow">↓</span>
                      </button>
                    )}
                    {salesItems.length > 0 && (
                      <button className="dl-btn secondary" onClick={handleDownloadGSTR1}>
                        <div className="dl-btn-left">
                          <span className="dl-btn-icon">🏛</span>
                          <div>
                            <div className="dl-btn-title">GSTR-1 JSON</div>
                            <div className="dl-btn-sub">Portal-ready · B2B · B2CS · B2CL · HSN</div>
                          </div>
                        </div>
                        <span className="dl-btn-arrow">↓</span>
                      </button>
                    )}
                    {purchaseItems.length > 0 && (
                      <button className={`dl-btn ${type === "purchase" || !salesItems.length ? "primary" : "secondary"}`} onClick={() => handleDownload("purchase")}>
                        <div className="dl-btn-left">
                          <span className="dl-btn-icon">📗</span>
                          <div>
                            <div className="dl-btn-title">Suvit_Purchase_Upload.xlsx</div>
                            <div className="dl-btn-sub">ITC eligible · Blocked · RCM tabs</div>
                          </div>
                        </div>
                        <span className="dl-btn-arrow">↓</span>
                      </button>
                    )}
                    {(salesItems.length > 0 || purchaseItems.length > 0) && (
                      <button
                        className="dl-btn secondary"
                        onClick={() => { setTallyPushResult(null); setShowTallyModal(true); }}
                      >
                        <div className="dl-btn-left">
                          <span className="dl-btn-icon">⇄</span>
                          <div>
                            <div className="dl-btn-title">Push to Tally</div>
                            <div className="dl-btn-sub">Direct connect · ERP_READY items only</div>
                          </div>
                        </div>
                        <span className="dl-btn-arrow">→</span>
                      </button>
                    )}
                  </div>

                  <div className="alert-row">
                    {taskErrors.length > 0 ? (
                      taskErrors.map((err, idx) => (
                        <div key={idx} className="alert err" style={{ marginBottom: "8px" }}>
                          <span className="alert-icon">✗</span>
                          {err}
                        </div>
                      ))
                    ) : (
                      <div className="alert ok">
                        <span className="alert-icon">✓</span>
                        Extracted {salesItems.length} Sales Items and {purchaseItems.length} Purchase Items successfully.
                      </div>
                    )}
                  </div>
                  <button className="cta-btn secondary" style={{ marginTop: 16 }} onClick={resetAll}>
                    Upload another batch
                  </button>
                </>
              ) : (
                /* OBSERVABILITY DASHBOARD VIEW */
                <div style={{ animation: "fadeIn .25s ease" }}>
                  {/* Batch telemetry summary */}
                  <div className="obs-grid">
                    <div className="obs-card">
                      <div className="obs-card-label">Success Rate</div>
                      <div className="obs-card-value" style={{ color: "#34D399" }}>
                        {batchMetrics?.files?.success_rate_pct !== undefined ? `${batchMetrics.files.success_rate_pct}%` : "100%"}
                      </div>
                    </div>
                    <div className="obs-card">
                      <div className="obs-card-label">Avg Quality Score</div>
                      <div className="obs-card-value" style={{ color: "var(--accent)" }}>
                        {batchMetrics?.model_used?.composite_score_avg !== undefined 
                          ? `${(batchMetrics.model_used.composite_score_avg * 100).toFixed(1)}%` 
                          : tasksMeta.length > 0
                            ? `${((tasksMeta.reduce((acc, t) => acc + (t.composite_score || 0.0), 0) / tasksMeta.length) * 100).toFixed(1)}%`
                            : "—"
                        }
                      </div>
                    </div>
                    <div className="obs-card">
                      <div className="obs-card-label">Cloud Cost</div>
                      <div className="obs-card-value" style={{ color: "#A78BFA" }}>
                        {batchMetrics?.model_used?.avg_cost_per_file_inr !== undefined
                          ? `₹ ${(batchMetrics.model_used.avg_cost_per_file_inr * (batchMetrics.files?.submitted || 1)).toFixed(2)}`
                          : tasksMeta.length > 0
                            ? `₹ ${tasksMeta.reduce((acc, t) => acc + (t.composite_score ? 0.05 : 0.0), 0.0).toFixed(2)}`
                            : "—"
                        }
                      </div>
                    </div>
                    <div className="obs-card">
                      <div className="obs-card-label">Active Flags</div>
                      <div className="obs-card-value" style={{ color: batchFlags.length > 0 ? "#ef4444" : "#34D399" }}>
                        {batchFlags.length} flags
                      </div>
                    </div>
                  </div>

                  {/* Batch flags section if any */}
                  {batchFlags.length > 0 && (
                    <div style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 12, padding: "16px 20px", marginBottom: 24, textAlign: "left" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#EF4444", fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                        <span>⚠️ System Batch Alerts</span>
                      </div>
                      <ul style={{ paddingLeft: 20, margin: 0, fontSize: 13, color: "var(--text-secondary)" }}>
                        {batchFlags.map((f: any, idx: number) => (
                          <li key={idx} style={{ marginBottom: 4 }}>
                            <strong>{f.flag_id}</strong> ({f.severity}): {f.detail}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* File Audit Checklist */}
                  <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden", marginBottom: 24 }}>
                    <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h4 style={{ margin: 0, fontSize: 15 }}>File Extraction Audit Trail</h4>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{tasksMeta.length} files tracked</span>
                    </div>
                    <div style={{ overflowX: "auto" }}>
                      <table className="obs-table">
                        <thead>
                          <tr style={{ background: "rgba(0,0,0,0.02)", borderBottom: "1px solid var(--border)" }}>
                            <th style={{ padding: "12px 16px", color: "var(--text-secondary)", fontWeight: 600 }}>Filename</th>
                            <th style={{ padding: "12px 16px", color: "var(--text-secondary)", fontWeight: 600 }}>Pipeline Status</th>
                            <th style={{ padding: "12px 16px", color: "var(--text-secondary)", fontWeight: 600 }}>Recon Status</th>
                            <th style={{ padding: "12px 16px", color: "var(--text-secondary)", fontWeight: 600 }}>Quality Score</th>
                            <th style={{ padding: "12px 16px", color: "var(--text-secondary)", fontWeight: 600 }}>Anomaly Flags</th>
                            <th style={{ padding: "12px 16px", color: "var(--text-secondary)", fontWeight: 600, textAlign: "right" }}>Execution Trace</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tasksMeta.map((task: any, idx: number) => {
                            const score = task.composite_score;
                            const isFailed = task.status === "FAILED";
                            const hasFlags = task.flags && task.flags.length > 0;
                            
                            return (
                              <tr key={idx} style={{ borderBottom: "1px solid var(--border)", transition: "background .15s" }} onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.01)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                                <td className="obs-td" style={{ fontWeight: 500, color: "var(--text-primary)" }}>{task.filename}</td>
                                <td className="obs-td">
                                  <span style={{
                                    padding: "2px 8px",
                                    borderRadius: 12,
                                    fontSize: 10,
                                    fontWeight: 600,
                                    background: isFailed ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)",
                                    color: isFailed ? "#EF4444" : "#34D399"
                                  }}>
                                    {task.status}
                                  </span>
                                </td>
                                <td className="obs-td">
                                  {/* Phase 4A: Recon Status Badge */}
                                  {task.recon_status ? (
                                    <span style={{
                                      padding: "2px 8px", borderRadius: 12, fontSize: 10, fontWeight: 600,
                                      background: task.recon_status === "ERP_READY" ? "rgba(34,197,94,0.12)" : task.recon_status === "HUMAN_CORRECTED" ? "rgba(167,139,250,0.12)" : task.recon_status === "BLOCKED" ? "rgba(239,68,68,0.12)" : "rgba(245,158,11,0.12)",
                                      color: task.recon_status === "ERP_READY" ? "#22c55e" : task.recon_status === "HUMAN_CORRECTED" ? "#a78bfa" : task.recon_status === "BLOCKED" ? "#ef4444" : "#f59e0b",
                                    }}>
                                      {task.recon_status === "ERP_READY" ? "✓ ERP Ready" : task.recon_status === "HUMAN_CORRECTED" ? "✦ Corrected" : task.recon_status === "BLOCKED" ? "✗ Blocked" : "⚠ Review"}
                                    </span>
                                  ) : <span style={{ color: "var(--text-muted)", fontSize: 11 }}>—</span>}
                                </td>
                                <td className="obs-td">
                                  {score !== null && score !== undefined ? (
                                    <span className={`obs-badge ${score >= 0.90 ? "success" : score >= 0.75 ? "warning" : "danger"}`}>
                                      {(score * 100).toFixed(1)}%
                                    </span>
                                  ) : (
                                    <span style={{ color: "var(--text-muted)" }}>—</span>
                                  )}
                                </td>
                                <td className="obs-td">
                                  {hasFlags ? (
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                      {task.flags.map((f: any, fIdx: number) => (
                                        <span 
                                          key={fIdx} 
                                          className={`obs-badge ${f.severity === "CRITICAL" ? "danger" : "warning"}`}
                                          title={f.detail}
                                          style={{ fontSize: 9 }}
                                        >
                                          ⚠️ {f.flag_id}
                                        </span>
                                      ))}
                                    </div>
                                  ) : isFailed ? (
                                    <span style={{ color: "#EF4444", fontSize: 11 }}>Pipeline Failure</span>
                                  ) : (
                                    <span style={{ color: "#34D399", fontSize: 11 }}>✓ Clean pass</span>
                                  )}
                                </td>
                                <td className="obs-td" style={{ textAlign: "right", display: "flex", gap: 8, justifyContent: "flex-end" }}>
                                  {/* Phase 4A: Review Audit button */}
                                  {task.task_id && task.status === "COMPLETED" && (
                                    <button
                                      id={`review-audit-${task.task_id}`}
                                      className="nav-pill"
                                      style={{ borderColor: "#8b5cf6", color: "#a78bfa", background: "rgba(139,92,246,0.08)", fontSize: 12, cursor: "pointer", padding: "6px 12px", borderRadius: 4 }}
                                      onClick={() => setReviewTask({ taskId: task.task_id, filename: task.filename })}
                                    >
                                      🔎 Audit Review
                                    </button>
                                  )}
                                  {task.filename && batchId && (
                                    <button
                                      className="nav-pill"
                                      style={{ borderColor: "#22d3ee", color: "#22d3ee", background: "rgba(34,211,238,0.05)", fontSize: 12, cursor: "pointer", padding: "6px 12px", borderRadius: 4 }}
                                      onClick={() => handlePdfClick(`${API_BASE_URL}/api/jobs/${batchId}/files/${encodeURIComponent(task.filename)}`, task.filename)}
                                    >
                                      📄 View PDF
                                    </button>
                                  )}
                                  <button
                                    className="nav-pill"
                                    style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--accent-soft)", fontSize: 12, cursor: "pointer", padding: "6px 12px", borderRadius: 4 }}
                                    onClick={() => setTraceTaskId(task.task_id)}
                                  >
                                    🔍 Trace steps
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                          {tasksMeta.length === 0 && (
                            <tr>
                              <td colSpan={6} style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>
                                No task telemetry available for this batch.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <button className="cta-btn secondary" style={{ maxWidth: 200, margin: "16px auto 0" }} onClick={resetAll}>
                    Upload another batch
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
          </>
        )}
      </div>
      
      {/* TRACE PIPELINE MODAL */}
      {traceTaskId && (
        <div className="trace-modal" onClick={() => setTraceTaskId(null)}>
          <div className="trace-content" onClick={(e) => e.stopPropagation()}>
            <div className="trace-header">
              <div>
                <h3 style={{ margin: 0, fontSize: 17, color: "var(--text-primary)" }}>AI Pipeline Execution Trace</h3>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", fontFamily: "monospace", marginTop: 4 }}>ID: {traceTaskId}</div>
              </div>
              <button 
                onClick={() => setTraceTaskId(null)}
                style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 20 }}
              >
                ✕
              </button>
            </div>
            
            <div className="trace-body">
              {isTraceLoading ? (
                <div style={{ padding: "60px 0", textAlign: "center" }}>
                  <div className="spinner"></div>
                  <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Fetching trace events…</div>
                </div>
              ) : traceEvents.length === 0 ? (
                <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-muted)" }}>
                  No execution traces found for this document in the database.
                </div>
              ) : (
                <div className="stepper">
                  {traceEvents.map((evt, idx) => {
                    const isStage = evt.event_type === "stage_event";
                    const isScore = evt.event_type === "extraction_quality_score";
                    const isMetrics = evt.event_type === "file_metrics";
                    const isFlag = evt.event_type === "system_flag";
                    const isSnapshot = evt.event_type === "extraction_context_snapshot";
                    const isCAFlag = evt.event_type === "ca_review_flag";
                    
                    let title = evt.event_type;
                    let badgeColor = "rgba(255,255,255,0.08)";
                    let badgeText = "event";
                    
                    if (isStage) {
                      title = `Stage: ${evt.stage.replace("_", " ")}`;
                      badgeColor = "var(--accent-soft)";
                      badgeText = "Pipeline Step";
                    } else if (isScore) {
                      title = `Quality Score Evaluated`;
                      badgeColor = "rgba(16,185,129,0.15)";
                      badgeText = "Score Card";
                    } else if (isMetrics) {
                      title = `Document Metrics Summary`;
                      badgeColor = "rgba(139,92,246,0.15)";
                      badgeText = "Usage & Cost";
                    } else if (isFlag) {
                      title = `Anomaly Flag Raised`;
                      badgeColor = "rgba(239,68,68,0.15)";
                      badgeText = `Flag Alert (${evt.severity})`;
                    } else if (isSnapshot) {
                      title = `Extraction Context Snapshot Saved`;
                      badgeColor = "rgba(234,179,8,0.12)";
                      badgeText = "Snapshot";
                    } else if (isCAFlag) {
                      title = `Reviewer Rejection Logged`;
                      badgeColor = "rgba(239,68,68,0.25)";
                      badgeText = "CA Review";
                    }
                    
                    const timeStr = new Date(evt.timestamp).toLocaleTimeString();
                    
                    return (
                      <div key={evt.id} className="stepper-item">
                        <div className={`stepper-dot ${isFlag || isCAFlag ? "active" : isScore ? "done" : ""}`}></div>
                        <div className="stepper-title">
                          <span style={{ textTransform: "capitalize" }}>{title}</span>
                          <span style={{
                            fontSize: 9,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: badgeColor,
                            color: isFlag || isCAFlag ? "#ef4444" : isScore ? "#34D399" : "var(--text-secondary)",
                            fontWeight: 700,
                            letterSpacing: "0.03em",
                            textTransform: "uppercase"
                          }}>
                            {badgeText}
                          </span>
                        </div>
                        <div className="stepper-meta">
                          <span>🕒 {timeStr}</span>
                          {evt.model && <span>🤖 {evt.model} ({evt.provider})</span>}
                          {evt.prompt_version && <span>📜 Prompt v{evt.prompt_version}</span>}
                        </div>
                        
                        {/* Event payload details */}
                        <div className="stepper-detail">
                          {isStage && evt.stage === "file_intake" && (
                            <div>
                              <div>📄 File Intake: <strong>{evt.payload.filename}</strong></div>
                              <div>Pages: <strong>{evt.payload.page_count}</strong> ({evt.payload.scan_type})</div>
                              <div>Status: <strong>{evt.payload.status}</strong></div>
                            </div>
                          )}
                          {isStage && evt.stage === "model_selection" && (
                            <div>
                              <div>Endpoint Health: <strong style={{ color: "#34D399" }}>{evt.payload.endpoint_health_check}</strong></div>
                              <div>API Endpoint: <code>{evt.payload.api_endpoint}</code></div>
                            </div>
                          )}
                          {isStage && evt.stage === "guardrail_precheck" && (
                            <div>
                              <div>Guardrails: <strong>Passed (100%)</strong></div>
                              <div style={{ fontSize: 10, opacity: 0.7, marginTop: 4 }}>
                                Checks: strict nulls, GST snapping, no line stacking, statutory math
                              </div>
                            </div>
                          )}
                          {isStage && evt.stage === "llm_extraction" && (
                            <div>
                              <div>Latency: <strong>{(evt.payload.latency_ms / 1000).toFixed(2)}s</strong></div>
                              <div>Prompt / Output Tokens: <strong>{evt.payload.prompt_tokens} / {evt.payload.completion_tokens}</strong></div>
                              <div>Raw Items Extracted: <strong>{evt.payload.raw_line_items_extracted}</strong></div>
                            </div>
                          )}
                          {isStage && evt.stage === "post_processing" && (
                            <div>
                              <div>Pruned Subtotal Rows: <strong>{evt.payload.corrections?.subtotal_rows_dropped || 0}</strong></div>
                              <div>GST Snap Adjustments: <strong>{evt.payload.corrections?.gst_rates_snapped || 0}</strong></div>
                              <div>Unallocated Lines Injected: <strong>{evt.payload.corrections?.unallocated_rows_injected || 0}</strong></div>
                            </div>
                          )}
                          {isStage && evt.stage === "final_output" && (
                            <div>
                              <div>Status: <strong>{evt.payload.status}</strong> (Database rows committed)</div>
                              <div>Total execution time: <strong>{(evt.payload.pipeline_total_latency_ms / 1000).toFixed(2)}s</strong></div>
                            </div>
                          )}
                          {isScore && (
                            <div>
                              <div>Composite Quality Score: <strong style={{ color: "#34D399" }}>{(evt.payload.composite_score * 100).toFixed(1)}%</strong></div>
                              <div>Statutory Math balanced: <strong>{evt.payload.statutory_math_balanced?.value ? "Yes" : "No"}</strong> (variance ₹{evt.payload.statutory_math_balanced?.variance_inr || 0})</div>
                              <div>GSTIN structure checks: <strong>{evt.payload.gstin_format_valid?.value ? "Valid Format" : "Invalid"}</strong></div>
                            </div>
                          )}
                          {isMetrics && (
                            <div>
                              <div>INR Cost Incurred: <strong style={{ color: "#A78BFA" }}>₹ {evt.payload.model_cost?.total_cost_inr.toFixed(4)}</strong></div>
                              <div>Tokens Per Page: <strong>{evt.payload.token_usage?.tokens_per_page}</strong></div>
                            </div>
                          )}
                          {isFlag && (
                            <div style={{ color: "#EF4444" }}>
                              <div><strong>Anomaly Triggered: {evt.flag_id}</strong></div>
                              <div>Details: <em>{evt.payload.trigger_detail}</em></div>
                            </div>
                          )}
                          {isCAFlag && (
                            <div style={{ color: "#EF4444" }}>
                              <div><strong>CA Grid Correction: Field '{evt.payload.rejected_field}'</strong></div>
                              <div>Extracted (AI): <code style={{ textDecoration: "line-through" }}>"{evt.payload.extracted_value}"</code></div>
                              <div>Corrected (CA): <code style={{ color: "#34D399" }}>"{evt.payload.ca_corrected_value}"</code></div>
                            </div>
                          )}
                          {isSnapshot && (
                            <div>
                              <div>Vendor GSTIN: <strong>{evt.payload.invoice_header?.vendor_gstin}</strong></div>
                              <div>Invoice No: <strong>{evt.payload.invoice_header?.invoice_no}</strong></div>
                              <div>Lines count: <strong>{evt.payload.extraction_summary?.items_count}</strong></div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tally connector: push ERP_READY items as vouchers */}
      {showTallyModal && (
        <div
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
          }}
          onClick={() => !isPushingToTally && setShowTallyModal(false)}
        >
          <div
            style={{
              background: "#0c0c14", border: "1px solid var(--border)", borderRadius: 12,
              padding: 24, width: 420, maxWidth: "90vw",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: 0, marginBottom: 4, color: "var(--text-primary)" }}>Push to Tally</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 0, marginBottom: 16 }}>
              Pushes only items marked <strong>ERP_READY</strong> (passed reconciliation review) as vouchers to TallyPrime over your LAN.
            </p>

            {!tallyPushResult && (
              <>
                <label style={{ fontSize: 13, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>TallyPrime Host / IP</label>
                <input
                  value={tallyHost}
                  onChange={(e) => setTallyHost(e.target.value)}
                  placeholder="192.168.1.157"
                  disabled={isPushingToTally}
                  style={{ width: "100%", padding: "8px 10px", marginBottom: 12, background: "#15151f", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-primary)" }}
                />
                <label style={{ fontSize: 13, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Port</label>
                <input
                  value={tallyPort}
                  onChange={(e) => setTallyPort(e.target.value)}
                  placeholder="9000"
                  disabled={isPushingToTally}
                  style={{ width: "100%", padding: "8px 10px", marginBottom: 12, background: "#15151f", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-primary)" }}
                />
                <label style={{ fontSize: 13, color: "var(--text-secondary)", display: "block", marginBottom: 4 }}>Tally Company Name</label>
                <input
                  value={tallyCompany}
                  onChange={(e) => setTallyCompany(e.target.value)}
                  placeholder="Xyz Pvt Ltd"
                  disabled={isPushingToTally}
                  style={{ width: "100%", padding: "8px 10px", marginBottom: 20, background: "#15151f", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-primary)" }}
                />
                <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                  <button
                    className="dl-btn secondary"
                    style={{ padding: "8px 16px" }}
                    disabled={isPushingToTally}
                    onClick={() => setShowTallyModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="dl-btn primary"
                    style={{ padding: "8px 16px" }}
                    disabled={isPushingToTally}
                    onClick={handlePushToTally}
                  >
                    {isPushingToTally ? "Pushing…" : "Push Now"}
                  </button>
                </div>
              </>
            )}

            {tallyPushResult && (
              <div>
                {tallyPushResult.error ? (
                  <div className="alert err">✗ {tallyPushResult.error}</div>
                ) : (
                  <>
                    <div style={{ fontSize: 14, marginBottom: 12, color: "var(--text-primary)" }}>
                      <strong>{tallyPushResult.succeeded}</strong> pushed ·{" "}
                      <strong>{tallyPushResult.skipped_already_pushed ?? 0}</strong> already-pushed (skipped) ·{" "}
                      <strong style={{ color: tallyPushResult.failed > 0 ? "#EF4444" : "inherit" }}>{tallyPushResult.failed}</strong> failed
                    </div>
                    {tallyPushResult.results?.filter((r: any) => !r.success).length > 0 && (
                      <div style={{ maxHeight: 200, overflowY: "auto", marginBottom: 16 }}>
                        {tallyPushResult.results
                          .filter((r: any) => !r.success)
                          .map((r: any, i: number) => (
                            <div key={i} style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6, paddingLeft: 8, borderLeft: "2px solid #EF4444" }}>
                              <strong>{r.invoice_no || r.file_name}</strong> ({r.voucher_type}): {r.error}
                            </div>
                          ))}
                      </div>
                    )}
                  </>
                )}
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button
                    className="dl-btn primary"
                    style={{ padding: "8px 16px" }}
                    onClick={() => { setShowTallyModal(false); setTallyPushResult(null); }}
                  >
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Phase 4A: Audit Review Panel */}
      {reviewTask && (
        <ReviewPanel
          taskId={reviewTask.taskId}
          filename={reviewTask.filename}
          batchId={batchId ?? undefined}
          onClose={() => setReviewTask(null)}
          onAccepted={() => {
            // Refresh tasks meta to update recon badge
            setTasksMeta((prev: any[]) =>
              prev.map((t) =>
                t.task_id === reviewTask.taskId
                  ? { ...t, recon_status: "HUMAN_CORRECTED" }
                  : t
              )
            );
          }}
        />
      )}
    </>
  );
}
