"use client";

import React, { useState, useRef, useEffect } from "react";
import { ChevronLeft } from "lucide-react";

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
  const [showHistory, setShowHistory] = useState(false);
  const [historyData, setHistoryData] = useState<any[]>([]);

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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ field: currentEdit.field, value: currentEdit.value })
      });
    } catch (e) {
      console.error("Failed to update cell", e);
    }
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
              
              const errors = statusData.tasks?.filter((t: any) => t.status === "FAILED" && t.error_message).map((t: any) => `${t.filename}: ${t.error_message}`) || [];
              setTaskErrors(errors);
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

  const handleDownload = async (downloadType: "sales" | "purchase" | "both") => {
    if (!batchId) {
      alert("No active batch to download.");
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/export/${batchId}?type=${downloadType}`);

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
    setStep(1);
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        .app-container { font-family: 'Inter', sans-serif; background: var(--bg-base); min-height: 100vh; color: var(--text-primary); padding: 0; }
        .topnav { display: flex; align-items: center; justify-content: space-between; padding: 14px 28px; border-bottom: 0.5px solid rgba(255,255,255,0.07); }
        .topnav .logo { display: flex; align-items: center; gap: 10px; }
        .logo-mark { width: 28px; height: 28px; border-radius: 7px; background: #1A6BFF; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: #fff; }
        .logo-name { font-size: 14px; font-weight: 600; letter-spacing: -0.02em; color: var(--text-primary); }
        .logo-tag { font-size: 11px; color: var(--text-secondary); margin-left: 2px; }
        .nav-right { display: flex; align-items: center; gap: 8px; }
        .nav-pill { font-size: 11px; padding: 4px 10px; border-radius: 20px; border: 0.5px solid rgba(255,255,255,0.12); color: var(--text-secondary); background: transparent; cursor: pointer; transition: all .15s; }
        .nav-pill:hover { border-color: rgba(255,255,255,0.25); color: var(--text-primary); }
        .step-bar { display: flex; align-items: center; justify-content: center; gap: 0; padding: 20px 28px 0; }
        .step-item { display: flex; align-items: center; gap: 8px; }
        .step-dot { width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: rgba(232,230,224,0.3); transition: all .3s; flex-shrink: 0; }
        .step-dot.done { background: #1A6BFF; border-color: #1A6BFF; color: #fff; }
        .step-dot.active { background: transparent; border-color: #1A6BFF; color: #1A6BFF; }
        .step-label { font-size: 11px; color: var(--text-secondary); transition: color .3s; white-space: nowrap; }
        .step-label.active { color: var(--text-primary); }
        .step-label.done { color: var(--text-secondary); }
        .step-line { width: 36px; height: 0.5px; background: rgba(255,255,255,0.1); margin: 0 8px; flex-shrink: 0; }
        .step-line.done { background: #1A6BFF; }
        .stage { max-width: 640px; margin: 0 auto; padding: 40px 24px 60px; }
        .step-view { animation: fadeIn .25s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .step-heading { font-size: 22px; font-weight: 600; letter-spacing: -0.03em; color: var(--text-primary); margin-bottom: 6px; line-height: 1.2; }
        .step-sub { font-size: 13px; color: var(--text-secondary); margin-bottom: 28px; line-height: 1.5; }
        .type-cards { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 28px; }
        .type-card { border: 1.5px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 20px 14px 16px; cursor: pointer; background: rgba(255,255,255,0.025); transition: all .2s; position: relative; text-align: center; }
        .type-card:hover { border-color: rgba(26,107,255,0.4); background: rgba(26,107,255,0.04); }
        .type-card.selected { border-color: #1A6BFF; background: rgba(26,107,255,0.08); }
        .type-icon { width: 40px; height: 40px; border-radius: 10px; margin: 0 auto 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .type-icon.sales { background: rgba(26,107,255,0.15); }
        .type-icon.purch { background: rgba(16,185,129,0.15); }
        .type-icon.both { background: rgba(139,92,246,0.15); }
        .type-card-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
        .type-card-sub { font-size: 11px; color: var(--text-secondary); line-height: 1.4; }
        .type-check { position: absolute; top: 10px; right: 10px; width: 16px; height: 16px; border-radius: 50%; background: #1A6BFF; display: none; align-items: center; justify-content: center; font-size: 9px; color: #fff; }
        .type-card.selected .type-check { display: flex; }
        .model-section { margin-bottom: 24px; }
        .model-section-label { font-size: 11px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 10px; }
        .model-rows { display: flex; flex-direction: column; gap: 6px; }
        .model-row { display: flex; align-items: center; gap: 12px; border: 0.5px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; cursor: pointer; background: rgba(255,255,255,0.02); transition: all .15s; position: relative; }
        .model-row:hover { border-color: rgba(255,255,255,0.18); }
        .model-row.selected { border-color: #1A6BFF; background: rgba(26,107,255,0.06); }
        .model-dot { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
        .model-dot.auto { background: rgba(234,179,8,0.15); }
        .model-dot.groq { background: rgba(239,68,68,0.12); }
        .model-dot.ollama { background: rgba(16,185,129,0.12); }
        .model-info { flex: 1; }
        .model-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
        .model-desc { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }
        .model-badge { font-size: 10px; padding: 2px 7px; border-radius: 20px; font-weight: 500; flex-shrink: 0; }
        .badge-rec { background: rgba(26,107,255,0.2); color: #6BA6FF; }
        .badge-fast { background: rgba(234,179,8,0.15); color: #D4A017; }
        .badge-priv { background: rgba(16,185,129,0.15); color: #34D399; }
        .model-radio { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.2); flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
        .model-row.selected .model-radio { border-color: #1A6BFF; background: #1A6BFF; }
        .model-row.selected .model-radio::after { content: ''; display: block; width: 6px; height: 6px; border-radius: 50%; background: #fff; }
        .both-hint { border: 0.5px solid rgba(139,92,246,0.3); border-radius: 10px; padding: 12px 14px; background: rgba(139,92,246,0.06); font-size: 12px; color: var(--text-secondary); margin-bottom: 24px; line-height: 1.5; }
        .both-hint span { color: #A78BFA; font-weight: 500; }
        .dropzone { border: 1.5px dashed rgba(255,255,255,0.12); border-radius: 14px; padding: 40px 24px; text-align: center; cursor: pointer; transition: all .2s; margin-bottom: 12px; background: rgba(255,255,255,0.015); position: relative; }
        .dropzone:hover, .dropzone.dragging { border-color: #1A6BFF; background: rgba(26,107,255,0.04); }
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
        .review-val.blue { color: #6BA6FF; }
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
        .proc-step.done .proc-step-dot { background: #1A6BFF; border-color: #1A6BFF; color: #fff; }
        .proc-step.active .proc-step-dot { border-color: #1A6BFF; color: #1A6BFF; }
        .done-wrap { text-align: center; padding: 32px 0 16px; }
        .done-icon { font-size: 40px; margin-bottom: 14px; }
        .done-title { font-size: 20px; font-weight: 600; letter-spacing: -0.02em; color: var(--text-primary); margin-bottom: 6px; }
        .done-sub { font-size: 13px; color: var(--text-secondary); margin-bottom: 28px; }
        .download-btns { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
        .dl-btn { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-radius: 12px; cursor: pointer; transition: all .15s; text-align: left; }
        .dl-btn.primary { background: #1A6BFF; border: none; color: #fff; }
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
        .cta-btn { width: 100%; padding: 14px; border-radius: 12px; background: #1A6BFF; border: none; color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; transition: all .15s; letter-spacing: -0.01em; }
        .cta-btn:hover:not(:disabled) { background: #2277FF; transform: translateY(-1px); }
        .cta-btn:active:not(:disabled) { transform: translateY(0); }
        .cta-btn:disabled { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.25); cursor: not-allowed; transform: none; }
        .cta-btn.secondary { background: transparent; border: 0.5px solid rgba(255,255,255,0.12); color: var(--text-secondary); margin-top: 8px; font-weight: 400; }
        .cta-btn.secondary:hover { border-color: rgba(255,255,255,0.25); color: var(--text-primary); background: transparent; }
        .back-link { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-secondary); cursor: pointer; margin-bottom: 24px; transition: color .15s; background: none; border: none; }
        .back-link:hover { color: var(--text-primary); }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner { width: 36px; height: 36px; border-radius: 50%; border: 2px solid rgba(26,107,255,0.2); border-top-color: #1A6BFF; animation: spin 0.8s linear infinite; margin: 0 auto 20px; }
        .prog-bar { height: 2px; background: rgba(255,255,255,0.06); border-radius: 2px; margin-bottom: 28px; overflow: hidden; }
        .prog-fill { height: 100%; background: #1A6BFF; border-radius: 2px; transition: width 0.5s ease; }
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
              style={{ borderColor: "rgba(26,107,255,0.4)", color: "rgba(26,107,255,0.8)" }}
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
                          style={{ borderColor: "#1A6BFF", color: "#1A6BFF", background: "rgba(26,107,255,0.05)" }}
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
            <div className="step-view">
              <div className="done-wrap">
                <div className="done-icon">✅</div>

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
            style={{ flex: 1, padding: "12px", background: activeTab === "sales" ? "transparent" : "rgba(0,0,0,0.04)", border: "none", borderBottom: activeTab === "sales" ? "2px solid #1A6BFF" : "2px solid transparent", color: activeTab === "sales" ? "var(--text-primary)" : "var(--text-secondary)", fontWeight: 600, cursor: "pointer", fontSize: 13 }}
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
                      <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 180 }}>Particulars</th>
                      <th style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500, minWidth: 80 }}>HSN</th>
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
                        style={{ width: "100%", background: "var(--bg-base)", color: "var(--text-primary)", border: "1px solid #1A6BFF", outline: "none", borderRadius: 4, padding: "4px" }}
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
                <tr key={idx} style={{ transition: "background 0.2s", cursor: "pointer" }} onMouseEnter={(e) => e.currentTarget.style.background = "rgba(0,0,0,0.02)"} onMouseLeave={(e) => e.currentTarget.style.background = "transparent"} onClick={(e) => { if ((e.target as HTMLElement).tagName !== "INPUT") setSelectedPdf(`${API_BASE_URL}/api/jobs/${batchId}/files/${encodeURIComponent(row.filename)}`); }}>
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
                      {renderCell("particulars", row.particulars)}
                      {renderCell("hsn", row.hsn)}
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
            <div style={{ padding: "8px 12px", background: "var(--bg-card)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 500 }}>Source Document</span>
                <button onClick={() => setSelectedPdf(null)} style={{ background: "transparent", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 16 }}>✕</button>
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
                  {files.length} file{files.length !== 1 ? "s" : ""} processed. Download your Suvit-ready sheets below.
                </div>
              </div>

              <div className="download-btns">
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
            </div>
          )}
        </div>
          </>
        )}
      </div>
    </>
  );
}
