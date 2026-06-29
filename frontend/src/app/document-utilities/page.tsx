"use client";

import React, { useState, useRef } from "react";
import {
  Lock,
  Scissors,
  Sparkles,
  Zap,
  Cpu,
  Loader2,
  UploadCloud,
  Download,
  Copy,
  CheckCircle,
  AlertTriangle,
  FileText,
  DollarSign,
  TrendingDown,
  Info as InfoIcon,
} from "lucide-react";

/* ─────────── Config ─────────── */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ActiveTab = "bank" | "splitter" | "enhancer" | "compressor" | "ocr";

export default function DocumentUtilitiesPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("bank");
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  // Tab 1: Bank Statement Locker State
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [bankPassword, setBankPassword] = useState("");
  const [transactions, setTransactions] = useState<any[]>([]);

  // Tab 2: Portal Splitter State
  const [splitterFile, setSplitterFile] = useState<File | null>(null);
  const [targetSize, setTargetSize] = useState(4.5);
  const [zipUrl, setZipUrl] = useState<string | null>(null);
  const [zipName, setZipName] = useState("");

  // Tab 3: Scan Enhancer State
  const [enhancerFile, setEnhancerFile] = useState<File | null>(null);
  const [enhancedUrl, setEnhancedUrl] = useState<string | null>(null);
  const [enhancedName, setEnhancedName] = useState("");

  // Tab 4: PDF Compressor State
  const [compressorFile, setCompressorFile] = useState<File | null>(null);
  const [quality, setQuality] = useState(50);
  const [compressedUrl, setCompressedUrl] = useState<string | null>(null);
  const [compressedName, setCompressedName] = useState("");
  const [originalSize, setOriginalSize] = useState<number | null>(null);
  const [compressedSize, setCompressedSize] = useState<number | null>(null);

  // Tab 5: Local OCR State
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrText, setOcrText] = useState("");
  const [ocrProvider, setOcrProvider] = useState("auto");
  const [ocrProviderUsed, setOcrProviderUsed] = useState("");
  const [copied, setCopied] = useState(false);

  // Drag and drop states for each tab
  const [dragActive, setDragActive] = useState(false);

  const resetMessages = () => {
    setSuccessMsg("");
    setErrorMsg("");
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  // Helper to format bytes
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  /* ─────────── Actions ─────────── */

  // 1. Bank Parse Action
  const handleBankParse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bankFile) return;
    setLoading(true);
    resetMessages();
    setTransactions([]);

    const formData = new FormData();
    formData.append("file", bankFile);
    formData.append("password", bankPassword);

    try {
      const res = await fetch(`${API_BASE_URL}/api/docs/bank-parse`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Statement parsing failed.");
      }

      const data = await res.json();
      setTransactions(data.transactions || []);
      const summary = data.summary || {};
      const summaryText = `Extracted ${data.transactions?.length || 0} transactions. ` +
        `SURE: ${summary.sure || 0}, PROBABLE: ${summary.probable || 0}, UNCERTAIN: ${summary.uncertain || 0}`;
      setSuccessMsg(summaryText);
    } catch (e: any) {
      setErrorMsg(e.message || "Could not parse bank statement. Ensure correct password.");
    } finally {
      setLoading(false);
    }
  };

  const downloadBankCSV = () => {
    if (!transactions.length) return;
    const headers = ["Date", "Narration", "Debit", "Credit", "Balance\r"];
    const rows = transactions.map((t) => [
      t.date || "",
      `"${(t.narration || "").replace(/"/g, '""')}"`,
      t.debit || "",
      t.credit || "",
      `${t.balance || ""}\r`,
    ]);
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = Object.assign(document.createElement("a"), {
      href: encodedUri,
      download: `${bankFile?.name.replace(".pdf", "")}_extracted.csv`,
    });
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // 2. Portal Splitter Action
  const handleSplitPortal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!splitterFile) return;
    setLoading(true);
    resetMessages();
    setZipUrl(null);

    const formData = new FormData();
    formData.append("file", splitterFile);
    formData.append("target_mb", targetSize.toString());

    try {
      const res = await fetch(`${API_BASE_URL}/api/docs/split-portal`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "PDF splitting failed.");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setZipUrl(url);
      const name = `${splitterFile.name.replace(".pdf", "")}_split.zip`;
      setZipName(name);
      setSuccessMsg(`Successfully split document into chunks. Ready for download.`);
    } catch (e: any) {
      setErrorMsg(e.message || "An error occurred during file splitting.");
    } finally {
      setLoading(false);
    }
  };

  // 3. Scan Enhancer Action
  const handleEnhanceScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enhancerFile) return;
    setLoading(true);
    resetMessages();
    setEnhancedUrl(null);

    const formData = new FormData();
    formData.append("file", enhancerFile);

    try {
      const res = await fetch(`${API_BASE_URL}/api/docs/enhance-scan`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Enhancement failed.");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setEnhancedUrl(url);
      const name = `${enhancerFile.name.substring(0, enhancerFile.name.lastIndexOf(".")) || enhancerFile.name}_enhanced.pdf`;
      setEnhancedName(name);
      setSuccessMsg(`Contrast enhanced successfully. Decoded vector PDF ready.`);
    } catch (e: any) {
      setErrorMsg(e.message || "An error occurred during image enhancement.");
    } finally {
      setLoading(false);
    }
  };

  // 4. PDF Compressor Action
  const handleCompressPDF = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!compressorFile) return;
    setLoading(true);
    resetMessages();
    setCompressedUrl(null);
    setOriginalSize(null);
    setCompressedSize(null);

    const formData = new FormData();
    formData.append("file", compressorFile);
    formData.append("quality", quality.toString());

    try {
      const res = await fetch(`${API_BASE_URL}/api/docs/compress`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Compression failed.");
      }

      // Read custom response headers
      const orig = res.headers.get("X-Original-Size");
      const comp = res.headers.get("X-Compressed-Size");
      if (orig) setOriginalSize(parseInt(orig));
      if (comp) setCompressedSize(parseInt(comp));

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setCompressedUrl(url);
      const name = `${compressorFile.name.replace(".pdf", "")}_compressed.pdf`;
      setCompressedName(name);
      setSuccessMsg(`PDF compressed successfully.`);
    } catch (e: any) {
      setErrorMsg(e.message || "An error occurred during compression.");
    } finally {
      setLoading(false);
    }
  };

  // 5. Local OCR Reader Action
  const handleOCRExtract = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ocrFile) return;
    setLoading(true);
    resetMessages();
    setOcrText("");
    setOcrProviderUsed("");

    const formData = new FormData();
    formData.append("file", ocrFile);
    formData.append("provider", ocrProvider);

    try {
      const res = await fetch(`${API_BASE_URL}/api/invoice-metadata`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "OCR extraction failed.");
      }

      const data = await res.json();
      setOcrText(data.text || "");
      setOcrProviderUsed(data.provider_used || "");
      const charCount = data.char_count || 0;
      const msg = charCount > 0
        ? `✓ Extracted ${charCount} characters using ${data.provider_used || "OCR"}`
        : `⚠ No text extracted. Try: 1) Upload a different file, 2) Use Scan Enhancer first`;
      setSuccessMsg(msg);
    } catch (e: any) {
      setErrorMsg(e.message || "OCR extraction failed — try a different provider.");
    } finally {
      setLoading(false);
    }
  };

  const copyOcrToClipboard = () => {
    if (!ocrText) return;
    navigator.clipboard.writeText(ocrText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main style={{ minHeight: "100vh", padding: "48px 16px 80px" }}>
      <div
        style={{
          maxWidth: 1220,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 32,
        }}
      >
        {/* Header */}
        <header className="animate-fade-up">
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: "rgba(99,102,241,0.12)",
              border: "1px solid rgba(99,102,241,0.25)",
              borderRadius: 99,
              padding: "5px 14px",
              fontSize: 12,
              color: "#a5b4fc",
              fontWeight: 500,
              marginBottom: 16,
            }}
          >
            <Cpu size={12} />
            CA Document Utility Workspace
          </div>

          <h1
            style={{
              fontSize: "clamp(32px, 5vw, 44px)",
              fontWeight: 800,
              letterSpacing: "-0.04em",
              lineHeight: 1.1,
              margin: 0,
            }}
          >
            <span className="shimmer-text">Document Utility Suite</span>
          </h1>
          <p
            style={{
              marginTop: 10,
              color: "var(--text-secondary)",
              fontSize: 14,
              fontWeight: 400,
              maxWidth: 720,
              lineHeight: 1.6,
            }}
          >
            Secure, local administrative tools for Indian audit desks. Perform bank statement parsing, PDF splitting, image contrast enhancement, file compression, and offline local OCR.
          </p>
        </header>

        {/* Tab Navigation */}
        <nav
          style={{
            display: "flex",
            gap: 4,
            padding: 4,
            background: "rgba(255,255,255,0.02)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
            alignSelf: "flex-start",
          }}
          className="animate-fade-up"
        >
          {[
            { id: "bank", label: "Bank Statement Locker", icon: Lock },
            { id: "splitter", label: "Portal Splitter (5MB)", icon: Scissors },
            { id: "enhancer", label: "Scan Enhancer", icon: Sparkles },
            { id: "compressor", label: "PDF Compressor", icon: TrendingDown },
            { id: "ocr", label: "Local OCR Reader", icon: FileText },
          ].map((tab) => {
            const Icon = tab.icon;
            const isSel = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  resetMessages();
                }}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  background: isSel ? "var(--accent-soft)" : "transparent",
                  border: isSel ? "1px solid rgba(99,102,241,0.25)" : "1px solid transparent",
                  borderRadius: "var(--radius-sm)",
                  padding: "8px 16px",
                  color: isSel ? "#a5b4fc" : "var(--text-secondary)",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <Icon size={13} />
                {tab.label}
              </button>
            );
          })}
        </nav>

        {/* Global Notifications */}
        {successMsg && (
          <div
            style={{
              background: "var(--green-soft)",
              border: "1px solid rgba(34,197,94,0.25)",
              color: "#86efac",
              padding: "12px 18px",
              borderRadius: "var(--radius-md)",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <CheckCircle size={15} style={{ color: "var(--green)" }} />
            <span>{successMsg}</span>
          </div>
        )}

        {errorMsg && (
          <div
            style={{
              background: "var(--red-soft)",
              border: "1px solid rgba(239,68,68,0.25)",
              color: "#fca5a5",
              padding: "12px 18px",
              borderRadius: "var(--radius-md)",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <AlertTriangle size={15} style={{ color: "var(--red)" }} />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Workspace Active Card */}
        <section
          className="glass animate-fade-up"
          style={{
            borderRadius: "var(--radius-lg)",
            padding: "32px",
            animationDelay: "0.08s",
          }}
        >
          {loading && (
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: "rgba(6,6,10,0.7)",
                backdropFilter: "blur(4px)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 12,
                borderRadius: "var(--radius-lg)",
                zIndex: 10,
              }}
            >
              <Loader2 size={36} className="animate-spin" style={{ color: "var(--accent)" }} />
              <div style={{ fontSize: 14, fontWeight: 700 }}>Processing Document Locally...</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>This may take a few seconds</div>
            </div>
          )}

          {/* TAB 1: BANK STATEMENT LOCKER */}
          {activeTab === "bank" && (
            <form onSubmit={handleBankParse} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px 0" }}>Bank Statement Locker</h3>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Upload a password-protected bank statement PDF to extract transaction ledgers locally.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                {/* File Drop Area */}
                <div
                  onDragOver={handleDrag}
                  onDragLeave={handleDrag}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files?.[0]) setBankFile(e.dataTransfer.files[0]);
                  }}
                  onClick={() => document.getElementById("bank-input")?.click()}
                  style={{
                    border: "2px dashed var(--border-strong)",
                    borderRadius: "var(--radius-md)",
                    padding: "24px",
                    textAlign: "center",
                    cursor: "pointer",
                    background: "rgba(255,255,255,0.01)",
                  }}
                >
                  <input
                    type="file"
                    id="bank-input"
                    accept=".pdf"
                    onChange={(e) => setBankFile(e.target.files?.[0] || null)}
                    style={{ display: "none" }}
                  />
                  <UploadCloud size={24} style={{ color: "var(--text-secondary)", margin: "0 auto 8px" }} />
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {bankFile ? bankFile.name : "Drag bank PDF here or browse"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    {bankFile ? formatBytes(bankFile.size) : "Standard encrypted/decrypted bank PDFs"}
                  </div>
                </div>

                {/* Password Input & Run Button */}
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 16 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>
                      PDF Decryption Password (if applicable)
                    </label>
                    <input
                      type="password"
                      placeholder="Enter statement password"
                      value={bankPassword}
                      onChange={(e) => setBankPassword(e.target.value)}
                      style={{
                        width: "100%",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid var(--border-strong)",
                        borderRadius: "var(--radius-sm)",
                        padding: "10px 14px",
                        fontSize: 13,
                        color: "#fff",
                        outline: "none",
                      }}
                    />
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={!bankFile}
                    style={{ padding: "12px 20px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, cursor: bankFile ? "pointer" : "not-allowed" }}
                  >
                    <Lock size={14} />
                    Decrypt & Extract Ledger
                  </button>
                </div>
              </div>

              {/* Transactions Table Output */}
              {transactions.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h4 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>Extracted Bank Transactions</h4>
                    <button
                      type="button"
                      onClick={downloadBankCSV}
                      className="btn-ghost"
                      style={{ padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}
                    >
                      <Download size={13} />
                      Export CSV Ledger
                    </button>
                  </div>

                  <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                      <thead>
                        <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                          <th style={{ padding: "10px 12px", textAlign: "left", color: "var(--text-muted)" }}>Date</th>
                          <th style={{ padding: "10px 12px", textAlign: "left", color: "var(--text-muted)" }}>Narration / Particulars</th>
                          <th style={{ padding: "10px 12px", textAlign: "right", color: "var(--text-muted)" }}>Debit / Withdrawal (₹)</th>
                          <th style={{ padding: "10px 12px", textAlign: "right", color: "var(--text-muted)" }}>Credit / Deposit (₹)</th>
                          <th style={{ padding: "10px 12px", textAlign: "right", color: "var(--text-muted)" }}>Balance (₹)</th>
                          <th style={{ padding: "10px 12px", textAlign: "center", color: "var(--text-muted)" }}>Confidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {transactions.map((tx, idx) => {
                          const confColor =
                            tx.confidence === "SURE" ? "#10b981" :
                            tx.confidence === "PROBABLE" ? "#f59e0b" :
                            "#ef4444";
                          return (
                            <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                              <td style={{ padding: "10px 12px", whiteSpace: "nowrap" }}>{tx.date}</td>
                              <td style={{ padding: "10px 12px" }}>{tx.narration}</td>
                              <td style={{ padding: "10px 12px", textAlign: "right", color: "var(--red)", fontFamily: "monospace" }}>{tx.debit || "—"}</td>
                              <td style={{ padding: "10px 12px", textAlign: "right", color: "var(--green)", fontFamily: "monospace" }}>{tx.credit || "—"}</td>
                              <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: "monospace", fontWeight: 600 }}>{tx.balance || "—"}</td>
                              <td style={{ padding: "10px 12px", textAlign: "center" }}>
                                <span style={{ fontSize: 11, fontWeight: 600, padding: "4px 8px", borderRadius: 4, background: `${confColor}20`, color: confColor }}>
                                  {tx.confidence || "—"}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </form>
          )}

          {/* TAB 2: PORTAL SPLITTER (5MB CAP) */}
          {activeTab === "splitter" && (
            <form onSubmit={handleSplitPortal} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px 0" }}>Portal Splitter (5MB Compliance Cap)</h3>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Estimate byte sizes and split a heavy PDF document into individual sub-5MB chunks, returning them bundled as a zip.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                {/* File selector */}
                <div
                  onDragOver={handleDrag}
                  onDragLeave={handleDrag}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files?.[0]) setSplitterFile(e.dataTransfer.files[0]);
                  }}
                  onClick={() => document.getElementById("splitter-input")?.click()}
                  style={{
                    border: "2px dashed var(--border-strong)",
                    borderRadius: "var(--radius-md)",
                    padding: "24px",
                    textAlign: "center",
                    cursor: "pointer",
                    background: "rgba(255,255,255,0.01)",
                  }}
                >
                  <input
                    type="file"
                    id="splitter-input"
                    accept=".pdf"
                    onChange={(e) => setSplitterFile(e.target.files?.[0] || null)}
                    style={{ display: "none" }}
                  />
                  <UploadCloud size={24} style={{ color: "var(--text-secondary)", margin: "0 auto 8px" }} />
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {splitterFile ? splitterFile.name : "Drag heavy PDF here or browse"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    {splitterFile ? formatBytes(splitterFile.size) : "PDF files exceeding portal file limits"}
                  </div>
                </div>

                {/* Configuration Slider & Actions */}
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 20 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                      <span>Statutory Portal Limit Cap</span>
                      <span style={{ color: "var(--accent)" }}>{targetSize.toFixed(1)} MB</span>
                    </div>
                    <input
                      type="range"
                      min="1.0"
                      max="4.8"
                      step="0.1"
                      value={targetSize}
                      onChange={(e) => setTargetSize(parseFloat(e.target.value))}
                      style={{
                        width: "100%",
                        accentColor: "var(--accent)",
                        cursor: "pointer",
                      }}
                    />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--text-muted)", marginTop: 4 }}>
                      <span>1.0 MB</span>
                      <span>Target safety margin</span>
                      <span>4.8 MB</span>
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={!splitterFile}
                    style={{ padding: "12px 20px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, cursor: splitterFile ? "pointer" : "not-allowed" }}
                  >
                    <Scissors size={14} />
                    Estimate & Split Document
                  </button>
                </div>
              </div>

              {/* ZIP Download Output */}
              {zipUrl && (
                <div
                  style={{
                    background: "rgba(99,102,241,0.06)",
                    border: "1px solid rgba(99,102,241,0.18)",
                    borderRadius: "var(--radius-md)",
                    padding: "18px 24px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginTop: 12,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--accent-soft)", display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "center" }}>
                      <FileText size={18} style={{ color: "var(--accent)" }} />
                    </div>
                    <div>
                      <h4 style={{ fontSize: 13, fontWeight: 700, margin: 0 }}>Portal Chunks Bundled Successfully</h4>
                      <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "2px 0 0 0" }}>{zipName}</p>
                    </div>
                  </div>

                  <a
                    href={zipUrl}
                    download={zipName}
                    className="btn-primary"
                    style={{ textDecoration: "none", padding: "10px 18px", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}
                  >
                    <Download size={14} />
                    Download ZIP Archive
                  </a>
                </div>
              )}
            </form>
          )}

          {/* TAB 3: SCAN ENHANCER */}
          {activeTab === "enhancer" && (
            <form onSubmit={handleEnhanceScan} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px 0" }}>WhatsApp Scan Enhancer</h3>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Upload low-contrast mobile snapshots or scans. Adaptive thresholding increases contrast and converts them to crisp black-and-white vector PDFs.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                {/* File selector */}
                <div
                  onDragOver={handleDrag}
                  onDragLeave={handleDrag}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files?.[0]) setEnhancerFile(e.dataTransfer.files[0]);
                  }}
                  onClick={() => document.getElementById("enhancer-input")?.click()}
                  style={{
                    border: "2px dashed var(--border-strong)",
                    borderRadius: "var(--radius-md)",
                    padding: "24px",
                    textAlign: "center",
                    cursor: "pointer",
                    background: "rgba(255,255,255,0.01)",
                  }}
                >
                  <input
                    type="file"
                    id="enhancer-input"
                    accept="image/*"
                    onChange={(e) => setEnhancerFile(e.target.files?.[0] || null)}
                    style={{ display: "none" }}
                  />
                  <UploadCloud size={24} style={{ color: "var(--text-secondary)", margin: "0 auto 8px" }} />
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {enhancerFile ? enhancerFile.name : "Drag scan image here or browse"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    {enhancerFile ? formatBytes(enhancerFile.size) : "JPG, PNG, JPEG snapshots"}
                  </div>
                </div>

                {/* Actions */}
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 20 }}>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={!enhancerFile}
                    style={{ padding: "12px 20px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, cursor: enhancerFile ? "pointer" : "not-allowed" }}
                  >
                    <Sparkles size={14} />
                    Enhance & Convert to PDF
                  </button>
                </div>
              </div>

              {/* PDF Output */}
              {enhancedUrl && (
                <div
                  style={{
                    background: "rgba(34,197,94,0.06)",
                    border: "1px solid rgba(34,197,94,0.18)",
                    borderRadius: "var(--radius-md)",
                    padding: "18px 24px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginTop: 12,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--green-soft)", display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "center" }}>
                      <FileText size={18} style={{ color: "var(--green)" }} />
                    </div>
                    <div>
                      <h4 style={{ fontSize: 13, fontWeight: 700, margin: 0 }}>Document Scan Enhanced</h4>
                      <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "2px 0 0 0" }}>{enhancedName}</p>
                    </div>
                  </div>

                  <a
                    href={enhancedUrl}
                    download={enhancedName}
                    className="btn-primary"
                    style={{ textDecoration: "none", background: "linear-gradient(135deg, #22c55e, #15803d)", border: "none", boxShadow: "0 0 16px rgba(34,197,94,0.2)", padding: "10px 18px", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}
                  >
                    <Download size={14} />
                    Download Enhanced PDF
                  </a>
                </div>
              )}
            </form>
          )}

          {/* TAB 4: PDF COMPRESSOR */}
          {activeTab === "compressor" && (
            <form onSubmit={handleCompressPDF} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px 0" }}>PDF Compressor</h3>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Optimizes PDF size by downscaling images and cleaning up garbage page trees. Shows exact byte savings.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                {/* File selector */}
                <div
                  onDragOver={handleDrag}
                  onDragLeave={handleDrag}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files?.[0]) setCompressorFile(e.dataTransfer.files[0]);
                  }}
                  onClick={() => document.getElementById("compressor-input")?.click()}
                  style={{
                    border: "2px dashed var(--border-strong)",
                    borderRadius: "var(--radius-md)",
                    padding: "24px",
                    textAlign: "center",
                    cursor: "pointer",
                    background: "rgba(255,255,255,0.01)",
                  }}
                >
                  <input
                    type="file"
                    id="compressor-input"
                    accept=".pdf"
                    onChange={(e) => setCompressorFile(e.target.files?.[0] || null)}
                    style={{ display: "none" }}
                  />
                  <UploadCloud size={24} style={{ color: "var(--text-secondary)", margin: "0 auto 8px" }} />
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {compressorFile ? compressorFile.name : "Drag PDF here or browse"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    {compressorFile ? formatBytes(compressorFile.size) : "Standard bulky PDF files"}
                  </div>
                </div>

                {/* Slider and action */}
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 20 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                      <span>Image Downscale Quality</span>
                      <span style={{ color: "var(--accent)" }}>{quality}%</span>
                    </div>
                    <input
                      type="range"
                      min="10"
                      max="90"
                      step="5"
                      value={quality}
                      onChange={(e) => setQuality(parseInt(e.target.value))}
                      style={{
                        width: "100%",
                        accentColor: "var(--accent)",
                        cursor: "pointer",
                      }}
                    />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--text-muted)", marginTop: 4 }}>
                      <span>10% (Max compression)</span>
                      <span>50% (Recommended)</span>
                      <span>90% (Max clarity)</span>
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={!compressorFile}
                    style={{ padding: "12px 20px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, cursor: compressorFile ? "pointer" : "not-allowed" }}
                  >
                    <TrendingDown size={14} />
                    Compress PDF File
                  </button>
                </div>
              </div>

              {/* Compression Results & Download */}
              {compressedUrl && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
                  {/* Visual Savings Bar */}
                  {originalSize && compressedSize && (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
                      <div className="glass" style={{ padding: "14px 18px", borderRadius: "var(--radius-sm)", textAlign: "center" }}>
                        <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>Original Size</div>
                        <div style={{ fontSize: 16, fontWeight: 800, color: "var(--text-secondary)", marginTop: 4, fontFamily: "monospace" }}>{formatBytes(originalSize)}</div>
                      </div>
                      <div className="glass" style={{ padding: "14px 18px", borderRadius: "var(--radius-sm)", textAlign: "center", border: "1px solid rgba(34,197,94,0.18)" }}>
                        <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>Compressed Size</div>
                        <div style={{ fontSize: 16, fontWeight: 800, color: "var(--green)", marginTop: 4, fontFamily: "monospace" }}>{formatBytes(compressedSize)}</div>
                      </div>
                      <div className="glass" style={{ padding: "14px 18px", borderRadius: "var(--radius-sm)", textAlign: "center", background: "var(--green-soft)" }}>
                        <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase" }}>Compaction Savings</div>
                        <div style={{ fontSize: 16, fontWeight: 800, color: "var(--green)", marginTop: 4, fontFamily: "monospace" }}>
                          {Math.round(((originalSize - compressedSize) / originalSize) * 100)}%
                        </div>
                      </div>
                    </div>
                  )}

                  <div
                    style={{
                      background: "rgba(99,102,241,0.06)",
                      border: "1px solid rgba(99,102,241,0.18)",
                      borderRadius: "var(--radius-md)",
                      padding: "18px 24px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--accent-soft)", display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "center" }}>
                        <FileText size={18} style={{ color: "var(--accent)" }} />
                      </div>
                      <div>
                        <h4 style={{ fontSize: 13, fontWeight: 700, margin: 0 }}>Compressed Document Ready</h4>
                        <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "2px 0 0 0" }}>{compressedName}</p>
                      </div>
                    </div>

                    <a
                      href={compressedUrl}
                      download={compressedName}
                      className="btn-primary"
                      style={{ textDecoration: "none", padding: "10px 18px", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}
                    >
                      <Download size={14} />
                      Download Compressed PDF
                    </a>
                  </div>
                </div>
              )}
            </form>
          )}

          {/* TAB 5: LOCAL OCR READER */}
          {activeTab === "ocr" && (
            <form onSubmit={handleOCRExtract} style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 4px 0" }}>Local OCR Reader</h3>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Extract text from scanned, flat PDF documents completely offline using the local AI PyTorch model.
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                {/* File selector */}
                <div
                  onDragOver={handleDrag}
                  onDragLeave={handleDrag}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files?.[0]) setOcrFile(e.dataTransfer.files[0]);
                  }}
                  onClick={() => document.getElementById("ocr-input")?.click()}
                  style={{
                    border: "2px dashed var(--border-strong)",
                    borderRadius: "var(--radius-md)",
                    padding: "24px",
                    textAlign: "center",
                    cursor: "pointer",
                    background: "rgba(255,255,255,0.01)",
                  }}
                >
                  <input
                    type="file"
                    id="ocr-input"
                    accept=".pdf"
                    onChange={(e) => setOcrFile(e.target.files?.[0] || null)}
                    style={{ display: "none" }}
                  />
                  <UploadCloud size={24} style={{ color: "var(--text-secondary)", margin: "0 auto 8px" }} />
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {ocrFile ? ocrFile.name : "Drag scanned PDF here or browse"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    {ocrFile ? formatBytes(ocrFile.size) : "Non-searchable scanned PDF files"}
                  </div>
                </div>

                {/* Actions */}
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 20 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>OCR Provider</label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {[
                        { value: "auto", label: "Auto (fast → slow)", desc: "PyMuPDF → Tesseract → EasyOCR" },
                        { value: "pymupdf", label: "PyMuPDF (native)", desc: "Instant, PDF text layer only" },
                        { value: "tesseract", label: "Tesseract (CPU)", desc: "~1-2s per page, if available" },
                        { value: "easyocr", label: "EasyOCR (ML)", desc: "Best accuracy, ~30-60s" },
                      ].map((opt) => (
                        <label key={opt.value} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 12 }}>
                          <input
                            type="radio"
                            name="ocr-provider"
                            value={opt.value}
                            checked={ocrProvider === opt.value}
                            onChange={(e) => setOcrProvider(e.target.value)}
                          />
                          <div>
                            <div style={{ fontWeight: 600 }}>{opt.label}</div>
                            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{opt.desc}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={!ocrFile || loading}
                    style={{ padding: "12px 20px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, cursor: (ocrFile && !loading) ? "pointer" : "not-allowed" }}
                  >
                    <Cpu size={14} />
                    {loading ? "Extracting..." : "Run OCR Extraction"}
                  </button>
                </div>
              </div>

              {/* Text Output Block */}
              {ocrText && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h4 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>Extracted Plain Text</h4>
                    <button
                      type="button"
                      onClick={copyOcrToClipboard}
                      className="btn-ghost"
                      style={{ padding: "6px 14px", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}
                    >
                      {copied ? (
                        <>
                          <CheckCircle size={13} style={{ color: "var(--green)" }} />
                          Copied!
                        </>
                      ) : (
                        <>
                          <Copy size={13} />
                          Copy Text
                        </>
                      )}
                    </button>
                  </div>

                  <textarea
                    readOnly
                    value={ocrText}
                    style={{
                      width: "100%",
                      height: 240,
                      background: "rgba(0,0,0,0.25)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      padding: "16px",
                      fontSize: 12,
                      fontFamily: "monospace",
                      color: "var(--text-primary)",
                      resize: "vertical",
                      outline: "none",
                      lineHeight: 1.5,
                    }}
                  />
                </div>
              )}
            </form>
          )}
        </section>

        {/* Auditor utility suite notes */}
        <section
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            padding: "24px 28px",
            display: "flex",
            gap: 16,
            alignItems: "flex-start",
          }}
          className="animate-fade-up"
        >
          <InfoIcon size={20} style={{ color: "var(--accent)", marginTop: 2, flexShrink: 0 }} />
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>
              Local Processing & Information Security Standards
            </h3>
            <ul
              style={{
                fontSize: 13,
                color: "var(--text-secondary)",
                lineHeight: 1.6,
                paddingLeft: 18,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <li>
                <strong>Zero Cloud Storage:</strong> All document utility operations are executed purely on your local CPU. Under no circumstances are statement passwords, transaction lists, or scanned pages transmitted over the internet.
              </li>
              <li>
                <strong>Portal Compliant Splitting:</strong> The portal splitter estimates sizes dynamically and splits the PDF strictly page-by-page. For multi-megabyte files, target <strong>4.5 MB</strong> as a buffer against server-side padding checks.
              </li>
              <li>
                <strong>Vector PDFs:</strong> WhatsApp scan enhancers and image thresholding tools do not simply output images. They convert them into clean vector PDF wrappers that preserve scaling when uploaded to government portals.
              </li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}
