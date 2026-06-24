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

    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));

    try {
      // Simulate frontend steps progression
      const interval = setInterval(() => {
        setProcStep((prev) => (prev < procStepsList.length - 1 ? prev + 1 : prev));
      }, 1500);

      const res = await fetch(
        `${API_BASE_URL}/api/extract?model=${encodeURIComponent(
          model
        )}&type=${encodeURIComponent(type || "both")}`,
        { method: "POST", body: fd }
      );

      clearInterval(interval);
      setProcStep(procStepsList.length);

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Extraction failed.");
      }
      const data = await res.json();
      setSalesItems(data.sales_items || []);
      setPurchaseItems(data.purchase_items || []);

      setTimeout(() => {
        setIsProcessing(false);
        setStep(5);
      }, 800);
    } catch (e: any) {
      alert("Error: " + e.message);
      setStep(3); // Go back
    }
  };

  const handleDownload = async (downloadType: "sales" | "purchase" | "both") => {
    try {
      const payload: any = {};
      if (downloadType === "sales" || downloadType === "both") {
        payload.sales_items = salesItems;
      }
      if (downloadType === "purchase" || downloadType === "both") {
        payload.purchase_items = purchaseItems;
      }

      const res = await fetch(`${API_BASE_URL}/api/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
    setStep(1);
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        .app-container { font-family: 'Inter', sans-serif; background: #0C0D0F; min-height: 100vh; color: #E8E6E0; padding: 0; }
        .topnav { display: flex; align-items: center; justify-content: space-between; padding: 14px 28px; border-bottom: 0.5px solid rgba(255,255,255,0.07); }
        .topnav .logo { display: flex; align-items: center; gap: 10px; }
        .logo-mark { width: 28px; height: 28px; border-radius: 7px; background: #1A6BFF; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; color: #fff; }
        .logo-name { font-size: 14px; font-weight: 600; letter-spacing: -0.02em; color: #E8E6E0; }
        .logo-tag { font-size: 11px; color: rgba(232,230,224,0.4); margin-left: 2px; }
        .nav-right { display: flex; align-items: center; gap: 8px; }
        .nav-pill { font-size: 11px; padding: 4px 10px; border-radius: 20px; border: 0.5px solid rgba(255,255,255,0.12); color: rgba(232,230,224,0.5); background: transparent; cursor: pointer; transition: all .15s; }
        .nav-pill:hover { border-color: rgba(255,255,255,0.25); color: #E8E6E0; }
        .step-bar { display: flex; align-items: center; justify-content: center; gap: 0; padding: 20px 28px 0; }
        .step-item { display: flex; align-items: center; gap: 8px; }
        .step-dot { width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: rgba(232,230,224,0.3); transition: all .3s; flex-shrink: 0; }
        .step-dot.done { background: #1A6BFF; border-color: #1A6BFF; color: #fff; }
        .step-dot.active { background: transparent; border-color: #1A6BFF; color: #1A6BFF; }
        .step-label { font-size: 11px; color: rgba(232,230,224,0.35); transition: color .3s; white-space: nowrap; }
        .step-label.active { color: rgba(232,230,224,0.75); }
        .step-label.done { color: rgba(232,230,224,0.5); }
        .step-line { width: 36px; height: 0.5px; background: rgba(255,255,255,0.1); margin: 0 8px; flex-shrink: 0; }
        .step-line.done { background: #1A6BFF; }
        .stage { max-width: 640px; margin: 0 auto; padding: 40px 24px 60px; }
        .step-view { animation: fadeIn .25s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .step-heading { font-size: 22px; font-weight: 600; letter-spacing: -0.03em; color: #E8E6E0; margin-bottom: 6px; line-height: 1.2; }
        .step-sub { font-size: 13px; color: rgba(232,230,224,0.45); margin-bottom: 28px; line-height: 1.5; }
        .type-cards { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 28px; }
        .type-card { border: 1.5px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 20px 14px 16px; cursor: pointer; background: rgba(255,255,255,0.025); transition: all .2s; position: relative; text-align: center; }
        .type-card:hover { border-color: rgba(26,107,255,0.4); background: rgba(26,107,255,0.04); }
        .type-card.selected { border-color: #1A6BFF; background: rgba(26,107,255,0.08); }
        .type-icon { width: 40px; height: 40px; border-radius: 10px; margin: 0 auto 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .type-icon.sales { background: rgba(26,107,255,0.15); }
        .type-icon.purch { background: rgba(16,185,129,0.15); }
        .type-icon.both { background: rgba(139,92,246,0.15); }
        .type-card-title { font-size: 13px; font-weight: 600; color: #E8E6E0; margin-bottom: 4px; }
        .type-card-sub { font-size: 11px; color: rgba(232,230,224,0.4); line-height: 1.4; }
        .type-check { position: absolute; top: 10px; right: 10px; width: 16px; height: 16px; border-radius: 50%; background: #1A6BFF; display: none; align-items: center; justify-content: center; font-size: 9px; color: #fff; }
        .type-card.selected .type-check { display: flex; }
        .model-section { margin-bottom: 24px; }
        .model-section-label { font-size: 11px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: rgba(232,230,224,0.35); margin-bottom: 10px; }
        .model-rows { display: flex; flex-direction: column; gap: 6px; }
        .model-row { display: flex; align-items: center; gap: 12px; border: 0.5px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; cursor: pointer; background: rgba(255,255,255,0.02); transition: all .15s; position: relative; }
        .model-row:hover { border-color: rgba(255,255,255,0.18); }
        .model-row.selected { border-color: #1A6BFF; background: rgba(26,107,255,0.06); }
        .model-dot { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
        .model-dot.auto { background: rgba(234,179,8,0.15); }
        .model-dot.groq { background: rgba(239,68,68,0.12); }
        .model-dot.ollama { background: rgba(16,185,129,0.12); }
        .model-info { flex: 1; }
        .model-name { font-size: 13px; font-weight: 500; color: #E8E6E0; }
        .model-desc { font-size: 11px; color: rgba(232,230,224,0.4); margin-top: 2px; }
        .model-badge { font-size: 10px; padding: 2px 7px; border-radius: 20px; font-weight: 500; flex-shrink: 0; }
        .badge-rec { background: rgba(26,107,255,0.2); color: #6BA6FF; }
        .badge-fast { background: rgba(234,179,8,0.15); color: #D4A017; }
        .badge-priv { background: rgba(16,185,129,0.15); color: #34D399; }
        .model-radio { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.2); flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
        .model-row.selected .model-radio { border-color: #1A6BFF; background: #1A6BFF; }
        .model-row.selected .model-radio::after { content: ''; display: block; width: 6px; height: 6px; border-radius: 50%; background: #fff; }
        .both-hint { border: 0.5px solid rgba(139,92,246,0.3); border-radius: 10px; padding: 12px 14px; background: rgba(139,92,246,0.06); font-size: 12px; color: rgba(232,230,224,0.6); margin-bottom: 24px; line-height: 1.5; }
        .both-hint span { color: #A78BFA; font-weight: 500; }
        .dropzone { border: 1.5px dashed rgba(255,255,255,0.12); border-radius: 14px; padding: 40px 24px; text-align: center; cursor: pointer; transition: all .2s; margin-bottom: 12px; background: rgba(255,255,255,0.015); position: relative; }
        .dropzone:hover, .dropzone.dragging { border-color: #1A6BFF; background: rgba(26,107,255,0.04); }
        .dz-icon { font-size: 32px; margin-bottom: 12px; opacity: 0.6; }
        .dz-title { font-size: 14px; font-weight: 500; color: #E8E6E0; margin-bottom: 4px; }
        .dz-sub { font-size: 12px; color: rgba(232,230,224,0.35); }
        .file-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
        .file-chip { display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.05); border: 0.5px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 4px 10px 4px 8px; font-size: 11px; color: rgba(232,230,224,0.7); }
        .chip-icon { font-size: 12px; opacity: 0.7; }
        .chip-remove { cursor: pointer; opacity: 0.4; font-size: 10px; margin-left: 2px; transition: opacity .15s; }
        .chip-remove:hover { opacity: 0.9; }
        .review-card { border: 0.5px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 20px; background: rgba(255,255,255,0.025); margin-bottom: 14px; }
        .review-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 0.5px solid rgba(255,255,255,0.05); font-size: 13px; }
        .review-row:last-child { border-bottom: none; padding-bottom: 0; }
        .review-label { color: rgba(232,230,224,0.45); }
        .review-val { color: #E8E6E0; font-weight: 500; }
        .review-val.blue { color: #6BA6FF; }
        .review-val.green { color: #34D399; }
        .review-val.purple { color: #A78BFA; }
        .output-tabs { display: flex; flex-direction: column; gap: 6px; margin-top: 16px; }
        .output-tab { display: flex; align-items: center; gap: 10px; border: 0.5px solid rgba(255,255,255,0.07); border-radius: 10px; padding: 10px 14px; background: rgba(255,255,255,0.02); }
        .out-icon { font-size: 16px; }
        .out-name { font-size: 12px; font-weight: 500; color: rgba(232,230,224,0.8); }
        .out-desc { font-size: 11px; color: rgba(232,230,224,0.35); margin-top: 1px; }
        .processing-wrap { text-align: center; padding: 40px 0; }
        .proc-title { font-size: 16px; font-weight: 500; color: #E8E6E0; margin-bottom: 8px; }
        .proc-sub { font-size: 12px; color: rgba(232,230,224,0.4); margin-bottom: 32px; }
        .proc-steps { text-align: left; display: flex; flex-direction: column; gap: 10px; }
        .proc-step { display: flex; align-items: center; gap: 12px; font-size: 13px; color: rgba(232,230,224,0.4); transition: color .3s; }
        .proc-step.done { color: rgba(232,230,224,0.75); }
        .proc-step.active { color: #E8E6E0; }
        .proc-step-dot { width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 9px; }
        .proc-step.done .proc-step-dot { background: #1A6BFF; border-color: #1A6BFF; color: #fff; }
        .proc-step.active .proc-step-dot { border-color: #1A6BFF; color: #1A6BFF; }
        .done-wrap { text-align: center; padding: 32px 0 16px; }
        .done-icon { font-size: 40px; margin-bottom: 14px; }
        .done-title { font-size: 20px; font-weight: 600; letter-spacing: -0.02em; color: #E8E6E0; margin-bottom: 6px; }
        .done-sub { font-size: 13px; color: rgba(232,230,224,0.4); margin-bottom: 28px; }
        .download-btns { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
        .dl-btn { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-radius: 12px; cursor: pointer; transition: all .15s; text-align: left; }
        .dl-btn.primary { background: #1A6BFF; border: none; color: #fff; }
        .dl-btn.primary:hover { background: #2277FF; }
        .dl-btn.secondary { background: transparent; border: 0.5px solid rgba(255,255,255,0.12); color: rgba(232,230,224,0.75); }
        .dl-btn.secondary:hover { border-color: rgba(255,255,255,0.25); color: #E8E6E0; }
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
        .cta-btn.secondary { background: transparent; border: 0.5px solid rgba(255,255,255,0.12); color: rgba(232,230,224,0.6); margin-top: 8px; font-weight: 400; }
        .cta-btn.secondary:hover { border-color: rgba(255,255,255,0.25); color: #E8E6E0; background: transparent; }
        .back-link { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: rgba(232,230,224,0.35); cursor: pointer; margin-bottom: 24px; transition: color .15s; background: none; border: none; }
        .back-link:hover { color: rgba(232,230,224,0.7); }
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
            <button className="nav-pill">GSTR-1</button>
            <button className="nav-pill">GSTR-2B</button>
            <button
              className="nav-pill"
              style={{ borderColor: "rgba(26,107,255,0.4)", color: "rgba(26,107,255,0.8)" }}
              onClick={resetAll}
            >
              New upload
            </button>
          </div>
        </nav>

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

        <div className="stage">
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
                  ? "PDF only. The engine auto-classifies each file as sales or purchase."
                  : "PDF only. Batch uploads supported — mix scanned and digital."}
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
                <div className="dz-sub">PDF · up to 50 files per batch</div>
                <input
                  type="file"
                  multiple
                  accept=".pdf"
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

              <div className="model-section">
                <div className="model-section-label">AI extraction model</div>
                <div className="model-rows">
                  <div
                    className={`model-row ${model === "auto" ? "selected" : ""}`}
                    onClick={() => setModel("auto")}
                  >
                    <div className="model-dot auto">⚡</div>
                    <div className="model-info">
                      <div className="model-name">Auto</div>
                      <div className="model-desc">≤5 pages → Cloud · {">"}5 pages → Local</div>
                    </div>
                    <span className="model-badge badge-rec">Recommended</span>
                    <div className="model-radio"></div>
                  </div>
                  <div
                    className={`model-row ${model === "openrouter-llama-3.3-70b" ? "selected" : ""}`}
                    onClick={() => setModel("openrouter-llama-3.3-70b")}
                  >
                    <div className="model-dot groq">☁</div>
                    <div className="model-info">
                      <div className="model-name">Cloud</div>
                      <div className="model-desc">Llama 3.3 / Gemini · fastest inference</div>
                    </div>
                    <span className="model-badge badge-fast">Fast</span>
                    <div className="model-radio"></div>
                  </div>
                  <div
                    className={`model-row ${model === "ollama" ? "selected" : ""}`}
                    onClick={() => setModel("ollama")}
                  >
                    <div className="model-dot ollama">🔒</div>
                    <div className="model-info">
                      <div className="model-name">Ollama local</div>
                      <div className="model-desc">Private · unlimited · no data leaves machine</div>
                    </div>
                    <span className="model-badge badge-priv">Private</span>
                    <div className="model-radio"></div>
                  </div>
                </div>
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
                  <span className="review-label">AI model</span>
                  <span className="review-val">
                    {model === "auto" ? "Auto (smart routing)" : model === "ollama" ? "Ollama local" : "Cloud Model"}
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
                      width: `${((procStep + 1) / (procStepsList.length + 1)) * 100}%`,
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
                <div className="done-title">Extraction complete</div>
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
                <div className="alert ok">
                  <span className="alert-icon">✓</span>
                  Extracted {salesItems.length} Sales Items and {purchaseItems.length} Purchase Items successfully.
                </div>
              </div>
              <button className="cta-btn secondary" style={{ marginTop: 16 }} onClick={resetAll}>
                Upload another batch
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
