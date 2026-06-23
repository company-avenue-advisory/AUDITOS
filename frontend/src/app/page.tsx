"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Upload,
  FileSpreadsheet,
  AlertTriangle,
  CheckCircle,
  Loader2,
  Download,
  Trash2,
  Plus,
  RefreshCw,
  ChevronDown,
  Cpu,
  Cloud,
  Zap,
  Sparkles,
} from "lucide-react";

/* ─────────── Types ─────────── */
interface LineItem {
  supplier_inv: string;
  invoice_date: string;
  gst_no: string;
  party_ac_name: string;
  place_of_supply: string;
  particulars: string;
  amount: number;
  sgst: number;
  cgst: number;
  igst: number;
  total_amount: number;
  hsn: string;
  narration: string;
  errors?: string[];
}
interface ModelOption { id: string; name: string; description: string; }

interface ReconcileSummary {
  counts: { matched: number, mismatch: number, missing_in_2b: number, not_in_books: number };
  amounts: { matched: number, mismatch: number, missing_in_2b: number, not_in_books: number };
  itc_at_risk: number;
  matched_itc: number;
  total_rows: number;
}
interface ReconcileResult {
  rows: any[];
  extra: any[];
  summary: ReconcileSummary;
}
/* ─────────── Config ─────────── */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const MODEL_CAUTIONS: Record<string, { level: "warn" | "info" | "ok"; icon: string; msg: string }> = {
  "auto":               { level: "info", icon: "⚡", msg: "Smart routing: ≤ 5 pages → Groq cloud, > 5 pages → local Ollama. Requires GROQ_API_KEY and Ollama for full coverage." },
  "groq-llama-3.3-70b": { level: "warn", icon: "☁️", msg: "Cloud model — Groq rate limits apply (~30 req/min free tier). Wait 2–3 min between large batches." },
  "groq-llama-4-scout": { level: "warn", icon: "☁️", msg: "Cloud vision model — best for scanned PDFs. Lower rate limits than text models." },
  "ollama":             { level: "ok",   icon: "🖥️", msg: "Fully private, no rate limits. Ollama must be running locally. Start with: ollama serve" },
};

const FALLBACK_MODELS: ModelOption[] = [
  { id: "auto",               name: "⚡ Auto (Smart Routing)",     description: "≤5 pages → Groq, >5 pages → Ollama" },
  { id: "groq-llama-3.3-70b", name: "☁️ Groq — Llama 3.3 70B",   description: "Fast cloud, best for standard invoices" },
  { id: "groq-llama-4-scout", name: "☁️ Groq — Llama 4 Scout",    description: "Vision model, great for scanned PDFs" },
  { id: "ollama",             name: "🖥️ Local Ollama",             description: "Private, unlimited, runs on your machine" },
];

/* ─────────── Component ─────────── */
export default function Home() {
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles]           = useState<File[]>([]);
  const [items, setItems]           = useState<LineItem[]>([]);
  const [loading, setLoading]       = useState(false);
  const [progressMsg, setProgressMsg] = useState("");
  const [error, setError]           = useState("");
  const [success, setSuccess]       = useState("");
  const [models, setModels]         = useState<ModelOption[]>(FALLBACK_MODELS);
  const [selectedModel, setSelectedModel] = useState("auto");
  const [dropOpen, setDropOpen]     = useState(false);

  // GSTR-2B Reconciliation State
  const [gstr2bFile, setGstr2bFile]     = useState<File | null>(null);
  const [reconResult, setReconResult]   = useState<ReconcileResult | null>(null);
  const [reconLoading, setReconLoading] = useState(false);
  const [reconError, setReconError]     = useState("");
  const gstr2bRef = useRef<HTMLInputElement>(null);

  const fileRef    = useRef<HTMLInputElement>(null);
  const dropRef    = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/models`)
      .then(r => r.json())
      .then(d => { if (d.models?.length) setModels(d.models); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setDropOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  /* ── Drag / file handlers ── */
  const onDrag = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    setDragActive(e.type === "dragenter" || e.type === "dragover");
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setDragActive(false);
    const picked = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith(".pdf"));
    if (picked.length) { setFiles(picked); setError(""); }
    else setError("Only PDF files are accepted.");
  };
  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files || []).filter(f => f.name.toLowerCase().endsWith(".pdf"));
    setFiles(picked); setError("");
  };

  /* ── Extraction ── */
  const startExtraction = async () => {
    if (!files.length) return;
    setLoading(true); setError(""); setSuccess("");
    const label = models.find(m => m.id === selectedModel)?.name || selectedModel;
    setProgressMsg(`Processing via ${label}…`);
    const fd = new FormData();
    files.forEach(f => fd.append("files", f));
    try {
      const res = await fetch(`${API_BASE_URL}/api/extract?model=${encodeURIComponent(selectedModel)}`, {
        method: "POST", body: fd,
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Extraction failed."); }
      const data = await res.json();
      setItems(data.items || []);
      setSuccess(`${data.items?.length || 0} line items extracted successfully.`);
    } catch (e: any) {
      setError(e.message || "Unexpected error during extraction.");
    } finally { setLoading(false); setProgressMsg(""); }
  };

  /* ── Table editing ── */
  const handleCell = (idx: number, field: keyof LineItem, val: any) => {
    const u = [...items];
    const numFields = ["amount","sgst","cgst","igst","total_amount"];
    if (numFields.includes(field)) {
      const p = parseFloat(val);
      u[idx] = { ...u[idx], [field]: isNaN(p) ? 0 : p };
    } else {
      u[idx] = { ...u[idx], [field]: val };
    }
    u[idx].errors = revalidate(u[idx]);
    setItems(u);
  };

  const revalidate = (item: LineItem): string[] => {
    const errs: string[] = [];
    if (!item.supplier_inv) errs.push("Missing invoice number");
    if (!item.invoice_date) errs.push("Missing invoice date");
    if (!item.gst_no) errs.push("Missing supplier GSTIN");
    else if (item.gst_no.trim().length !== 15) errs.push("GSTIN must be 15 characters");
    const expected = (item.amount||0)+(item.sgst||0)+(item.cgst||0)+(item.igst||0);
    if (Math.abs(expected - (item.total_amount||0)) > 2)
      errs.push(`Math mismatch: ${expected.toFixed(2)} ≠ ${item.total_amount?.toFixed(2)}`);
    return errs;
  };

  const addRow = () => setItems([...items, {
    supplier_inv:"", invoice_date:"", gst_no:"", party_ac_name:"",
    place_of_supply:"", particulars:"New Item", amount:0, sgst:0, cgst:0,
    igst:0, total_amount:0, hsn:"", narration:"",
    errors:["New row — complete details"]
  }]);

  const deleteRow = (i: number) => setItems(items.filter((_, idx) => idx !== i));

  const handleExport = async () => {
    if (!items.length) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/export`, {
        method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({items}),
      });
      if (!res.ok) throw new Error("Export failed.");
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = Object.assign(document.createElement("a"), { href:url, download:"invoices_audited.xlsx" });
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e: any) { setError(e.message || "Download failed."); }
  };

  /* ── GSTR-2B Reconciliation ── */
  const onGstr2bChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.name.toLowerCase().endsWith(".json")) {
      setGstr2bFile(file);
      setReconError("");
      setReconResult(null); // Reset result on new file
    } else {
      setReconError("Please upload a valid JSON file.");
    }
  };

  const startReconciliation = async () => {
    if (!items.length || !gstr2bFile) return;
    setReconLoading(true); setReconError("");
    
    try {
      const text = await gstr2bFile.text();
      // Ensure it's parsable JSON before sending
      let parsed;
      try { parsed = JSON.parse(text); } catch { throw new Error("Invalid JSON file structure."); }

      const res = await fetch(`${API_BASE_URL}/api/reconcile`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items, gstr2b: parsed })
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Reconciliation failed."); }
      const data = await res.json();
      setReconResult(data);
    } catch (e: any) {
      setReconError(e.message || "Failed to run reconciliation.");
    } finally {
      setReconLoading(false);
    }
  };

  const exportReconciliation = async () => {
    if (!items.length || !gstr2bFile) return;
    try {
      const text = await gstr2bFile.text();
      const res = await fetch(`${API_BASE_URL}/api/reconcile/export`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ items, gstr2b: JSON.parse(text) }),
      });
      if (!res.ok) throw new Error("Export failed.");
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = Object.assign(document.createElement("a"), { href:url, download:"gstr2b_reconciliation.xlsx" });
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e: any) { setReconError(e.message || "Download failed."); }
  };

  /* ── Metrics ── */
  const totalRows    = items.length;
  const cleanRows    = items.filter(i => !i.errors?.length).length;
  const accuracy     = totalRows > 0 ? Math.round((cleanRows / totalRows) * 100) : 100;
  const caution      = MODEL_CAUTIONS[selectedModel];
  const selectedLabel = models.find(m => m.id === selectedModel)?.name || "⚡ Auto";

  /* ── Colour helpers ── */
  const accuracyColor = accuracy >= 90 ? "#22c55e" : accuracy >= 70 ? "#f59e0b" : "#ef4444";

  return (
    <main style={{ minHeight:"100vh", padding:"48px 24px 80px" }}>
      <div style={{ maxWidth:1160, margin:"0 auto", display:"flex", flexDirection:"column", gap:32 }}>

        {/* ══ HERO HEADER ══ */}
        <header className="animate-fade-up" style={{ textAlign:"center", paddingBottom:8 }}>
          {/* Pill badge */}
          <div style={{
            display:"inline-flex", alignItems:"center", gap:6,
            background:"rgba(99,102,241,0.12)", border:"1px solid rgba(99,102,241,0.25)",
            borderRadius:99, padding:"5px 14px", fontSize:12, color:"#a5b4fc",
            fontWeight:500, marginBottom:20, letterSpacing:"0.02em"
          }}>
            <Sparkles size={12} />
            AI-Powered · GST-Compliant · Audit-Ready
          </div>

          <h1 style={{ fontSize:"clamp(36px, 6vw, 64px)", fontWeight:800, letterSpacing:"-0.04em", lineHeight:1.05, margin:0 }}>
            <span className="shimmer-text">Invoice Extractor</span>
            <br />
            <span style={{ color:"var(--text-primary)", fontWeight:700 }}>&amp; Auditor</span>
          </h1>
          <p style={{ marginTop:16, color:"var(--text-secondary)", fontSize:16, fontWeight:400, maxWidth:520, margin:"16px auto 0", lineHeight:1.6 }}>
            Drop your merged PDF invoices. AI extracts, validates, and exports a clean Excel audit sheet — in seconds.
          </p>
        </header>

        {/* ══ STATS ROW ══ */}
        <div className="animate-fade-up" style={{
          display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:16,
          animationDelay:"0.05s"
        }}>
          {[
            { label:"Supported Format", val:"PDF", sub:"Any merged invoice" },
            { label:"Cloud Models",     val:"Groq",  sub:"Llama 3.3 / 4 Scout" },
            { label:"Local Models",     val:"Ollama", sub:"Private & unlimited" },
          ].map(s => (
            <div key={s.label} className="glass" style={{
              borderRadius:"var(--radius-lg)", padding:"20px 24px", textAlign:"center"
            }}>
              <div style={{ fontSize:22, fontWeight:700, color:"var(--text-primary)", letterSpacing:"-0.02em" }}>{s.val}</div>
              <div style={{ fontSize:12, fontWeight:600, color:"var(--text-secondary)", marginTop:2 }}>{s.label}</div>
              <div style={{ fontSize:11, color:"var(--text-muted)", marginTop:1 }}>{s.sub}</div>
            </div>
          ))}
        </div>

        {/* ══ NOTICES ══ */}
        <div className="animate-fade-up" style={{
          display:"grid", gridTemplateColumns:"1fr 1fr", gap:12,
          animationDelay:"0.1s"
        }}>
          <div style={{
            background:"var(--amber-soft)", border:"1px solid rgba(245,158,11,0.2)",
            borderRadius:"var(--radius-md)", padding:"14px 18px",
            display:"flex", gap:12, alignItems:"flex-start"
          }}>
            <AlertTriangle size={15} style={{ color:"var(--amber)", marginTop:2, flexShrink:0 }} />
            <div>
              <div style={{ fontSize:13, fontWeight:600, color:"#fcd34d", marginBottom:2 }}>Rate Limit Advice</div>
              <div style={{ fontSize:12, color:"#fde68a", lineHeight:1.5 }}>Wait 2–3 min between consecutive uploads on cloud models.</div>
            </div>
          </div>
          <div style={{
            background:"var(--blue-soft)", border:"1px solid rgba(96,165,250,0.2)",
            borderRadius:"var(--radius-md)", padding:"14px 18px",
            display:"flex", gap:12, alignItems:"flex-start"
          }}>
            <FileSpreadsheet size={15} style={{ color:"var(--blue)", marginTop:2, flexShrink:0 }} />
            <div>
              <div style={{ fontSize:13, fontWeight:600, color:"#93c5fd", marginBottom:2 }}>Large Documents</div>
              <div style={{ fontSize:12, color:"#bfdbfe", lineHeight:1.5 }}>Consider splitting very large PDFs before uploading for best results.</div>
            </div>
          </div>
        </div>

        {/* ══ MODEL SELECTION ══ */}
        <section className="glass animate-fade-up" style={{
          borderRadius:"var(--radius-xl)", padding:"28px 32px",
          animationDelay:"0.15s"
        }}>
          {/* Section label */}
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:20 }}>
            <div style={{
              width:34, height:34, borderRadius:10,
              background:"var(--accent-soft)", border:"1px solid rgba(99,102,241,0.25)",
              display:"flex", alignItems:"center", justifyContent:"center"
            }}>
              <Cpu size={16} style={{ color:"var(--accent)" }} />
            </div>
            <div>
              <div style={{ fontSize:15, fontWeight:700, color:"var(--text-primary)", letterSpacing:"-0.01em" }}>AI Model</div>
              <div style={{ fontSize:12, color:"var(--text-muted)" }}>Choose before uploading</div>
            </div>
          </div>

          {/* Dropdown */}
          <div style={{ position:"relative" }} ref={dropRef}>
            <button
              id="model-selector"
              onClick={() => setDropOpen(v => !v)}
              style={{
                width:"100%", display:"flex", alignItems:"center", justifyContent:"space-between",
                background:"rgba(255,255,255,0.05)", border:"1px solid var(--border-strong)",
                borderRadius:"var(--radius-md)", padding:"14px 18px",
                fontSize:14, fontWeight:600, color:"var(--text-primary)", cursor:"pointer",
                transition:"border-color 0.15s ease, background 0.15s ease",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.08)")}
              onMouseLeave={e => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}
            >
              <span>{selectedLabel}</span>
              <ChevronDown size={16} style={{
                color:"var(--text-muted)",
                transform: dropOpen ? "rotate(180deg)" : "rotate(0deg)",
                transition:"transform 0.2s ease"
              }} />
            </button>

            {dropOpen && (
              <div style={{
                position:"absolute", top:"calc(100% + 8px)", left:0, right:0, zIndex:50,
                background:"#111116", border:"1px solid var(--border-strong)",
                borderRadius:"var(--radius-md)", overflow:"hidden",
                boxShadow:"0 24px 48px rgba(0,0,0,0.6)"
              }}>
                {models.map((m, i) => (
                  <button
                    key={m.id}
                    id={`model-opt-${m.id}`}
                    onClick={() => { setSelectedModel(m.id); setDropOpen(false); }}
                    style={{
                      width:"100%", textAlign:"left", padding:"14px 18px",
                      display:"flex", flexDirection:"column", gap:2, cursor:"pointer",
                      background: selectedModel === m.id ? "var(--accent-soft)" : "transparent",
                      borderBottom: i < models.length - 1 ? "1px solid var(--border)" : "none",
                      transition:"background 0.12s ease",
                    }}
                    onMouseEnter={e => { if (selectedModel !== m.id) e.currentTarget.style.background = "rgba(255,255,255,0.04)"; }}
                    onMouseLeave={e => { if (selectedModel !== m.id) e.currentTarget.style.background = "transparent"; }}
                  >
                    <span style={{ fontSize:13, fontWeight:600, color: selectedModel === m.id ? "#a5b4fc" : "var(--text-primary)" }}>{m.name}</span>
                    <span style={{ fontSize:11, color:"var(--text-muted)" }}>{m.description}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Caution banner */}
          {caution && (
            <div style={{
              marginTop:14, borderRadius:"var(--radius-sm)", padding:"12px 16px",
              display:"flex", gap:10, alignItems:"flex-start",
              background: caution.level === "warn" ? "var(--amber-soft)"
                        : caution.level === "ok"   ? "var(--green-soft)"
                        : "var(--blue-soft)",
              border: `1px solid ${caution.level === "warn" ? "rgba(245,158,11,0.25)" : caution.level === "ok" ? "rgba(34,197,94,0.2)" : "rgba(96,165,250,0.2)"}`,
            }}>
              {caution.level === "warn"
                ? <AlertTriangle size={14} style={{ color:"var(--amber)", marginTop:1, flexShrink:0 }} />
                : caution.level === "ok"
                ? <Cpu size={14} style={{ color:"var(--green)", marginTop:1, flexShrink:0 }} />
                : <Cloud size={14} style={{ color:"var(--blue)", marginTop:1, flexShrink:0 }} />}
              <span style={{
                fontSize:12, lineHeight:1.55,
                color: caution.level === "warn" ? "#fde68a" : caution.level === "ok" ? "#86efac" : "#bfdbfe"
              }}>{caution.msg}</span>
            </div>
          )}

          {selectedModel === "ollama" && (
            <div style={{
              marginTop:8, borderRadius:"var(--radius-sm)", padding:"12px 16px",
              background:"var(--red-soft)", border:"1px solid rgba(239,68,68,0.2)",
              display:"flex", gap:10, alignItems:"flex-start"
            }}>
              <AlertTriangle size={14} style={{ color:"var(--red)", flexShrink:0, marginTop:1 }} />
              <span style={{ fontSize:12, color:"#fca5a5", lineHeight:1.55 }}>
                Ollama not running? Extraction will fail. Run{" "}
                <code style={{ background:"rgba(255,255,255,0.08)", padding:"1px 6px", borderRadius:4, fontFamily:"monospace", fontSize:11 }}>ollama serve</code>
                {" "}then{" "}
                <code style={{ background:"rgba(255,255,255,0.08)", padding:"1px 6px", borderRadius:4, fontFamily:"monospace", fontSize:11 }}>ollama pull qwen2.5:7b</code>
              </span>
            </div>
          )}
        </section>

        {/* ══ UPLOAD ══ */}
        <section className="glass animate-fade-up" style={{
          borderRadius:"var(--radius-xl)", padding:"28px 32px",
          animationDelay:"0.2s"
        }}>
          {/* Drop zone */}
          <div
            onDragEnter={onDrag} onDragLeave={onDrag} onDragOver={onDrag} onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            style={{
              border: `2px dashed ${dragActive ? "var(--accent)" : "var(--border-strong)"}`,
              borderRadius:"var(--radius-lg)", padding:"48px 24px",
              display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center",
              cursor:"pointer", textAlign:"center", gap:12,
              background: dragActive ? "var(--accent-soft)" : "transparent",
              transition:"border-color 0.15s ease, background 0.15s ease",
            }}
          >
            <input ref={fileRef} type="file" multiple accept=".pdf" style={{ display:"none" }} onChange={onChange} />

            {/* Upload icon ring */}
            <div style={{
              width:56, height:56, borderRadius:16,
              background:"rgba(99,102,241,0.12)", border:"1px solid rgba(99,102,241,0.3)",
              display:"flex", alignItems:"center", justifyContent:"center",
            }}>
              <Upload size={24} style={{ color:"var(--accent)" }} />
            </div>

            <div>
              <div style={{ fontSize:16, fontWeight:600, color:"var(--text-primary)", marginBottom:4 }}>
                {files.length > 0
                  ? `${files.length} PDF${files.length > 1 ? "s" : ""} selected`
                  : "Drop your invoices here"}
              </div>
              <div style={{ fontSize:13, color:"var(--text-muted)" }}>
                {files.length > 0
                  ? files.map(f => f.name).join(", ")
                  : "or click to browse · PDF only"}
              </div>
            </div>
          </div>

          {/* Action row */}
          <div style={{ marginTop:20, display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
            <button
              id="start-extraction-btn"
              className="btn-primary"
              onClick={startExtraction}
              disabled={!files.length || loading}
              style={{ padding:"13px 28px", fontSize:14, display:"flex", alignItems:"center", gap:8, cursor: files.length && !loading ? "pointer" : "not-allowed" }}
            >
              {loading
                ? <><Loader2 size={16} className="animate-spin" /><span>Extracting…</span></>
                : <><Zap size={16} /><span>Start Audit Extraction</span></>}
            </button>

            {loading && (
              <div style={{ display:"flex", alignItems:"center", gap:8, fontSize:13, color:"var(--text-muted)" }}
                className="animate-pulse-slow">
                <RefreshCw size={14} className="animate-spin" style={{ color:"var(--accent)" }} />
                <span>{progressMsg}</span>
              </div>
            )}
          </div>
        </section>

        {/* ══ FEEDBACK ══ */}
        {error && (
          <div className="animate-fade-up" style={{
            background:"var(--red-soft)", border:"1px solid rgba(239,68,68,0.25)",
            borderRadius:"var(--radius-md)", padding:"14px 18px",
            display:"flex", gap:12, alignItems:"flex-start"
          }}>
            <AlertTriangle size={15} style={{ color:"var(--red)", flexShrink:0, marginTop:1 }} />
            <span style={{ fontSize:13, color:"#fca5a5", lineHeight:1.5 }}>{error}</span>
          </div>
        )}
        {success && (
          <div className="animate-fade-up" style={{
            background:"var(--green-soft)", border:"1px solid rgba(34,197,94,0.2)",
            borderRadius:"var(--radius-md)", padding:"14px 18px",
            display:"flex", gap:12, alignItems:"center"
          }}>
            <CheckCircle size={15} style={{ color:"var(--green)", flexShrink:0 }} />
            <span style={{ fontSize:13, color:"#86efac" }}>{success}</span>
          </div>
        )}

        {/* ══ RESULTS TABLE ══ */}
        {items.length > 0 && (
          <section className="glass animate-fade-up" style={{
            borderRadius:"var(--radius-xl)", overflow:"hidden",
            animationDelay:"0.05s"
          }}>
            {/* Table header bar */}
            <div style={{
              padding:"24px 28px", borderBottom:"1px solid var(--border)",
              display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:16
            }}>
              <div>
                <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                  <span style={{ fontSize:17, fontWeight:700, color:"var(--text-primary)", letterSpacing:"-0.02em" }}>Audited Line Items</span>
                  <span style={{
                    fontSize:11, fontWeight:600, color:"var(--text-muted)",
                    background:"rgba(255,255,255,0.07)", border:"1px solid var(--border)",
                    borderRadius:99, padding:"2px 10px"
                  }}>{items.length} rows</span>
                </div>
                <div style={{ fontSize:12, color:"var(--text-muted)", marginTop:4 }}>
                  Click any cell to edit · Validations update live
                </div>
              </div>

              <div style={{ display:"flex", alignItems:"center", gap:12 }}>
                {/* Accuracy pill */}
                <div style={{
                  background:"rgba(255,255,255,0.05)", border:"1px solid var(--border)",
                  borderRadius:"var(--radius-sm)", padding:"8px 16px", textAlign:"center"
                }}>
                  <div style={{ fontSize:11, color:"var(--text-muted)", marginBottom:2 }}>Quality</div>
                  <div style={{ fontSize:20, fontWeight:800, color:accuracyColor, letterSpacing:"-0.03em" }}>{accuracy}%</div>
                </div>

                <button id="add-row-btn" className="btn-ghost" onClick={addRow}
                  style={{ padding:"8px 14px", fontSize:12, display:"flex", alignItems:"center", gap:6 }}>
                  <Plus size={13} /><span>Add Row</span>
                </button>
                <button id="export-btn" onClick={handleExport}
                  style={{
                    padding:"8px 16px", fontSize:12, fontWeight:600,
                    background:"var(--green-soft)", border:"1px solid rgba(34,197,94,0.25)",
                    borderRadius:"var(--radius-sm)", color:"#86efac", cursor:"pointer",
                    display:"flex", alignItems:"center", gap:6,
                    transition:"background 0.15s ease"
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = "rgba(34,197,94,0.18)"}
                  onMouseLeave={e => e.currentTarget.style.background = "var(--green-soft)"}
                >
                  <Download size={13} /><span>Export Excel</span>
                </button>
              </div>
            </div>

            {/* Scrollable table */}
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                <thead>
                  <tr style={{ background:"rgba(0,0,0,0.25)", borderBottom:"1px solid var(--border)" }}>
                    {["","Invoice ID","Date","GSTIN","Party Name","Particulars","Amount","SGST","CGST","IGST","Total","HSN",""].map((h, i) => (
                      <th key={i} style={{
                        padding:"10px 10px", textAlign: (i === 0 || i === 12) ? "center" : i >= 6 && i <= 10 ? "right" : "left",
                        color:"var(--text-muted)", fontWeight:600, letterSpacing:"0.06em", fontSize:10,
                        textTransform:"uppercase", whiteSpace:"nowrap"
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => {
                    const hasErr = item.errors && item.errors.length > 0;
                    return (
                      <tr key={idx} style={{
                        borderBottom:"1px solid var(--border)",
                        background: hasErr ? "rgba(245,158,11,0.04)" : "transparent",
                        transition:"background 0.12s ease"
                      }}
                        onMouseEnter={e => e.currentTarget.style.background = hasErr ? "rgba(245,158,11,0.08)" : "rgba(255,255,255,0.025)"}
                        onMouseLeave={e => e.currentTarget.style.background = hasErr ? "rgba(245,158,11,0.04)" : "transparent"}
                      >
                        {/* Status */}
                        <td style={{ padding:"8px 12px", textAlign:"center", width:36 }}>
                          {hasErr ? (
                            <div style={{ position:"relative", display:"inline-block" }} className="group">
                              <AlertTriangle size={14} style={{ color:"var(--amber)", cursor:"help", display:"block" }} />
                              <div style={{
                                position:"absolute", left:"calc(100% + 8px)", top:"50%", transform:"translateY(-50%)",
                                background:"#18181f", border:"1px solid var(--border-strong)",
                                borderRadius:"var(--radius-sm)", padding:"10px 14px",
                                width:260, zIndex:99, pointerEvents:"none",
                                boxShadow:"0 16px 40px rgba(0,0,0,0.5)",
                                display:"none"
                              }} className="group-tooltip">
                                <div style={{ fontSize:11, fontWeight:700, color:"var(--amber)", marginBottom:6 }}>Issues detected</div>
                                {item.errors?.map((e, i) => (
                                  <div key={i} style={{ fontSize:11, color:"var(--text-secondary)", marginBottom:3, display:"flex", gap:6 }}>
                                    <span style={{ color:"var(--amber)", flexShrink:0 }}>·</span>{e}
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <CheckCircle size={14} style={{ color:"var(--green)", display:"block", margin:"0 auto" }} />
                          )}
                        </td>

                        {/* Editable cells */}
                        {(["supplier_inv","invoice_date","gst_no","party_ac_name","particulars"] as (keyof LineItem)[]).map(f => (
                          <td key={f} style={{ padding:"4px 6px" }}>
                            <input className="cell-input"
                              value={(item[f] as string) || ""}
                              onChange={e => handleCell(idx, f, e.target.value)}
                              style={{ fontFamily: f === "gst_no" ? "monospace" : "inherit", textTransform: f === "gst_no" ? "uppercase" : "none" }}
                            />
                          </td>
                        ))}

                        {/* Numeric cells */}
                        {(["amount","sgst","cgst","igst","total_amount"] as (keyof LineItem)[]).map(f => (
                          <td key={f} style={{ padding:"4px 6px" }}>
                            <input className="cell-input" type="number" step="any"
                              value={(item[f] as number) || 0}
                              onChange={e => handleCell(idx, f, e.target.value)}
                              style={{ textAlign:"right", fontFamily:"monospace" }}
                            />
                          </td>
                        ))}

                        {/* HSN */}
                        <td style={{ padding:"4px 6px" }}>
                          <input className="cell-input" value={item.hsn || ""}
                            onChange={e => handleCell(idx, "hsn", e.target.value)}
                            style={{ fontFamily:"monospace" }}
                          />
                        </td>

                        {/* Delete */}
                        <td style={{ padding:"4px 12px", textAlign:"center", width:36 }}>
                          <button onClick={() => deleteRow(idx)}
                            style={{
                              background:"none", border:"none", cursor:"pointer", padding:4, borderRadius:6,
                              color:"var(--text-muted)", transition:"color 0.12s ease",
                              display:"flex", alignItems:"center", justifyContent:"center"
                            }}
                            onMouseEnter={e => e.currentTarget.style.color = "var(--red)"}
                            onMouseLeave={e => e.currentTarget.style.color = "var(--text-muted)"}
                          >
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ══ GSTR-2B RECONCILIATION ══ */}
        {items.length > 0 && (
          <section className="animate-fade-up glass" style={{
            borderRadius:"var(--radius-xl)", overflow:"hidden", padding:"24px 28px",
            animationDelay:"0.1s", marginTop: 16
          }}>
            <div style={{ marginBottom: 20 }}>
              <h2 style={{ fontSize:17, fontWeight:700, color:"var(--text-primary)", letterSpacing:"-0.02em", marginBottom: 4 }}>GSTR-2B Reconciliation</h2>
              <p style={{ fontSize:12, color:"var(--text-muted)", margin:0 }}>Upload the GSTR-2B JSON from the GST portal to verify extracted invoices against government records.</p>
            </div>

            {reconError && (
               <div style={{
                  background:"var(--red-soft)", border:"1px solid rgba(239,68,68,0.25)",
                  borderRadius:"var(--radius-md)", padding:"12px 16px", marginBottom: 16,
                  display:"flex", gap:10, alignItems:"center", fontSize:13, color:"#fca5a5"
               }}>
                 <AlertTriangle size={14} style={{ color:"var(--red)", flexShrink:0 }} /> {reconError}
               </div>
            )}

            <div style={{ display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
               <input type="file" accept=".json" ref={gstr2bRef} style={{ display:"none" }} onChange={onGstr2bChange} />
               <button className="btn-ghost" onClick={() => gstr2bRef.current?.click()} style={{ padding:"10px 18px", fontSize:13, display:"flex", alignItems:"center", gap:8, border:"1px solid var(--border)" }}>
                  <Upload size={14} />
                  <span>{gstr2bFile ? gstr2bFile.name : "Select GSTR-2B JSON"}</span>
               </button>

               <button className="btn-primary" onClick={startReconciliation} disabled={!gstr2bFile || reconLoading}
                 style={{ padding:"10px 18px", fontSize:13, display:"flex", alignItems:"center", gap:8, cursor: gstr2bFile && !reconLoading ? "pointer" : "not-allowed", opacity: (!gstr2bFile || reconLoading) ? 0.6 : 1 }}>
                 {reconLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                 <span>Run Match</span>
               </button>

               {reconResult && (
                 <button className="btn-ghost" onClick={exportReconciliation}
                   style={{ padding:"10px 18px", fontSize:13, display:"flex", alignItems:"center", gap:8, background:"var(--green-soft)", color:"#86efac", border:"1px solid rgba(34,197,94,0.25)" }}>
                   <Download size={14} /> <span style={{fontWeight:600}}>Export Audit Report</span>
                 </button>
               )}
            </div>

            {/* Reconciliation Summary Cards */}
            {reconResult && (
               <div style={{ display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:12, marginTop: 24 }}>
                 {[
                   { label: "Matched", count: reconResult.summary.counts.matched, val: reconResult.summary.amounts.matched, col: "#22c55e", bg: "var(--green-soft)" },
                   { label: "Amount Mismatch", count: reconResult.summary.counts.mismatch, val: reconResult.summary.amounts.mismatch, col: "#f59e0b", bg: "var(--amber-soft)" },
                   { label: "Missing in 2B (Risk)", count: reconResult.summary.counts.missing_in_2b, val: reconResult.summary.amounts.missing_in_2b, col: "#ef4444", bg: "var(--red-soft)" },
                   { label: "Not Booked (in 2B)", count: reconResult.summary.counts.not_in_books, val: reconResult.summary.amounts.not_in_books, col: "#60a5fa", bg: "var(--blue-soft)" },
                 ].map(s => (
                   <div key={s.label} style={{ background: s.bg, border:`1px solid ${s.col}33`, borderRadius: "var(--radius-md)", padding:"16px", textAlign:"center" }}>
                      <div style={{ fontSize:11, fontWeight:600, color: s.col, textTransform:"uppercase", letterSpacing:"0.05em", marginBottom:4 }}>{s.label}</div>
                      <div style={{ fontSize:22, fontWeight:700, color: "var(--text-primary)" }}>{s.count}</div>
                      <div style={{ fontSize:12, color: s.col, opacity: 0.8, marginTop:2 }}>₹ {s.val.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                   </div>
                 ))}
               </div>
            )}
            
            {/* Reconciliation Preview Rows */}
            {reconResult && (
               <div style={{ marginTop: 24, overflowX:"auto" }}>
                 <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
                   <thead>
                     <tr style={{ background:"rgba(0,0,0,0.25)", borderBottom:"1px solid var(--border)", textAlign:"left", color:"var(--text-muted)" }}>
                       <th style={{ padding:"10px 8px", fontWeight:600 }}>Status</th>
                       <th style={{ padding:"10px 8px", fontWeight:600 }}>Invoice</th>
                       <th style={{ padding:"10px 8px", fontWeight:600 }}>GSTIN</th>
                       <th style={{ padding:"10px 8px", fontWeight:600, textAlign:"right" }}>Books Amount</th>
                       <th style={{ padding:"10px 8px", fontWeight:600, textAlign:"right" }}>2B Amount</th>
                       <th style={{ padding:"10px 8px", fontWeight:600, textAlign:"right" }}>Diff</th>
                     </tr>
                   </thead>
                   <tbody>
                     {(reconResult.rows.slice(0, 5) as any[]).map((r, i) => {
                       const st = r.recon_status;
                       const color = st === 'matched' ? '#22c55e' : st === 'mismatch' ? '#f59e0b' : '#ef4444';
                       const label = st === 'matched' ? 'Matched' : st === 'mismatch' ? 'Mismatch' : 'Missing 2B';
                       return (
                         <tr key={i} style={{ borderBottom:"1px solid var(--border)" }}>
                           <td style={{ padding:8, color, fontWeight:600 }}>{label}</td>
                           <td style={{ padding:8, color:"var(--text-secondary)" }}>{r.supplier_inv || '-'}</td>
                           <td style={{ padding:8, fontFamily:"monospace", color:"var(--text-secondary)" }}>{r.gst_no || r.gstin || '-'}</td>
                           <td style={{ padding:8, textAlign:"right", color:"var(--text-primary)" }}>{r.total_amount ? r.total_amount.toFixed(2) : '-'}</td>
                           <td style={{ padding:8, textAlign:"right", color:"var(--text-primary)" }}>{r['2b_total_val'] ? r['2b_total_val'].toFixed(2) : '-'}</td>
                           <td style={{ padding:8, textAlign:"right", color: r.diff_amount && Math.abs(r.diff_amount) > 2 ? '#ef4444' : 'var(--text-primary)' }}>{r.diff_amount ? r.diff_amount.toFixed(2) : '-'}</td>
                         </tr>
                       )
                     })}
                     {reconResult.rows.length > 5 && (
                       <tr><td colSpan={6} style={{ padding:10, textAlign:"center", color:"var(--text-muted)", fontStyle:"italic" }}>... and {reconResult.rows.length - 5} more rows (Export to see full detail)</td></tr>
                     )}
                   </tbody>
                 </table>
               </div>
            )}
          </section>
        )}

        {/* ══ FOOTER ══ */}
        <footer style={{ textAlign:"center", paddingTop:8 }}>
          <p style={{ fontSize:12, color:"var(--text-muted)" }}>
            Backend{" "}
            <a href="https://yugshri--ai-invoice-extractor-fastapi-app.modal.run/docs" target="_blank" rel="noreferrer"
              style={{ color:"var(--accent)", textDecoration:"none", fontWeight:500 }}>
              modal.run
            </a>
            {" · "}Frontend{" "}
            <a href="http://localhost:3000" target="_blank" rel="noreferrer"
              style={{ color:"var(--accent)", textDecoration:"none", fontWeight:500 }}>
              localhost:3000
            </a>
          </p>
        </footer>

      </div>

      {/* Tooltip show-on-hover — pure CSS via style tag, zero JS */}
      <style>{`
        .group:hover .group-tooltip { display:block !important; }
      `}</style>
    </main>
  );
}
