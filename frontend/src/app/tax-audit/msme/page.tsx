"use client";

import React, { useState, useRef } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  CheckCircle,
  Coins,
  Loader2,
  Trash2,
  Plus,
  Info,
  UploadCloud,
  FileText,
} from "lucide-react";

/* ─────────── Types ─────────── */
interface MSMEInvoiceRow {
  id: string;
  partyName: string;
  invoiceNo: string;
  invoiceDate: string;
  paymentDate: string; // empty means unpaid
  udyamNumber: string;
  udyamStatus: "UNKNOWN" | "MICRO" | "SMALL" | "MEDIUM" | "LARGE";
  hasAgreement: boolean;
  amount: number;
  isVerifying?: boolean;
}

/* ─────────── Config ─────────── */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const BANK_RATE = 0.0675; // 6.75%
const INTEREST_RATE = 3 * BANK_RATE; // 20.25% per annum

export default function MSMEAuditPage() {
  const [rows, setRows] = useState<MSMEInvoiceRow[]>([
    {
      id: "1",
      partyName: "Apex Manufacturing Ltd",
      invoiceNo: "INV-2026-001",
      invoiceDate: "2026-04-10",
      paymentDate: "2026-06-15", // 66 days delay (limit is 15 or 45)
      udyamNumber: "UDYAM-MH-12-0089123",
      udyamStatus: "MICRO",
      hasAgreement: true, // limit = 45 days. Delayed by 21 days
      amount: 150000,
    },
    {
      id: "2",
      partyName: "Delta Logistics Solutions",
      invoiceNo: "INV-2026-042",
      invoiceDate: "2026-05-01",
      paymentDate: "2026-05-12", // 11 days delay (limit is 15)
      udyamNumber: "UDYAM-DL-05-0012345",
      udyamStatus: "SMALL",
      hasAgreement: false, // limit = 15 days. Within limit!
      amount: 45000,
    },
    {
      id: "3",
      partyName: "Titan Enterprise Solutions",
      invoiceNo: "INV-2026-099",
      invoiceDate: "2026-05-10",
      paymentDate: "2026-07-20", // 71 days delay
      udyamNumber: "UDYAM-GJ-01-0098765",
      udyamStatus: "MEDIUM", // Medium is exempt from 43B(h) disallowance!
      hasAgreement: false,
      amount: 850000,
    },
    {
      id: "4",
      partyName: "Alpha Consulting Services",
      invoiceNo: "INV-2026-112",
      invoiceDate: "2026-06-01",
      paymentDate: "", // Unpaid
      udyamNumber: "UDYAM-UP-18-0054321",
      udyamStatus: "UNKNOWN", // Unverified status
      hasAgreement: false,
      amount: 120000,
    },
  ]);

  const [activeTab, setActiveTab] = useState<"all" | "disallowed" | "verified">("all");
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [parsingFile, setParsingFile] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Statutory Calculations for a Row
  const calculateRowDetails = (row: MSMEInvoiceRow) => {
    const invDate = new Date(row.invoiceDate);
    const payDate = row.paymentDate ? new Date(row.paymentDate) : new Date(); // use today if unpaid
    
    // Days elapsed
    const diffTime = Math.max(0, payDate.getTime() - invDate.getTime());
    const daysElapsed = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    // Allowed limit
    const limitDays = row.hasAgreement ? 45 : 15;
    const delayDays = Math.max(0, daysElapsed - limitDays);
    
    // Check if 43B(h) applies (only MICRO and SMALL)
    const isMSMEEligible = row.udyamStatus === "MICRO" || row.udyamStatus === "SMALL";
    const isDelayed = delayDays > 0;
    
    // Disallowed Amount
    const disallowedAmount = isMSMEEligible && isDelayed ? row.amount : 0;
    
    // Compound interest calculation: Section 16 of MSMED Act (3x Bank Rate, compounded monthly)
    let interestPenalty = 0;
    if (isMSMEEligible && isDelayed) {
      // Compounded monthly: A = P(1 + r/12)^n
      const P = row.amount;
      const r = INTEREST_RATE;
      const n = daysElapsed / 30.417; // convert days to fractional months
      const compoundedTotal = P * Math.pow(1 + r / 12, n);
      interestPenalty = Math.max(0, compoundedTotal - P);
    }
    
    return {
      daysElapsed,
      limitDays,
      delayDays,
      disallowedAmount,
      interestPenalty,
      isDelayed,
    };
  };

  const handleVerify = async (id: string, udyamNumber: string) => {
    if (!udyamNumber) {
      setErrorMsg("Please enter a valid Udyam Number first.");
      return;
    }
    
    // Set verifying state
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, isVerifying: true } : r))
    );
    setErrorMsg("");
    setSuccessMsg("");

    try {
      const res = await fetch(`${API_BASE_URL}/api/verify-msme`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ udyam_number: udyamNumber }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Verification failed");
      }

      const data = await res.json();
      
      // Update row with returned enterprise status
      setRows((prev) =>
        prev.map((r) =>
          r.id === id
            ? {
                ...r,
                udyamStatus: data.enterprise_type || "UNKNOWN",
                isVerifying: false,
              }
            : r
        )
      );

      setSuccessMsg(`Successfully verified: ${data.enterprise_name} (${data.enterprise_type})`);
    } catch (e: any) {
      setErrorMsg(e.message || "Could not verify MSME status via official API.");
      setRows((prev) =>
        prev.map((r) => (r.id === id ? { ...r, isVerifying: false } : r))
      );
    }
  };

  // PDF Drag and Drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await uploadUdyamPDF(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      await uploadUdyamPDF(e.target.files[0]);
    }
  };

  const uploadUdyamPDF = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setErrorMsg("Only PDF certificates can be parsed.");
      return;
    }

    setParsingFile(true);
    setErrorMsg("");
    setSuccessMsg("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/tax/parse-udyam`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to parse PDF Udyam Certificate");
      }

      const data = await res.json();
      
      // Successfully parsed, add to list as a new verified vendor row
      const newId = (rows.length + 1).toString();
      const newRow: MSMEInvoiceRow = {
        id: newId,
        partyName: data.enterprise_name || "Parsed Supplier",
        invoiceNo: `PARSED-${Math.floor(100 + Math.random() * 900)}`,
        invoiceDate: new Date().toISOString().split("T")[0],
        paymentDate: "",
        udyamNumber: data.udyam_number || "UNKNOWN",
        udyamStatus: data.enterprise_type || "UNKNOWN",
        hasAgreement: false,
        amount: 50000, // Seed a default amount for the CA to edit
      };

      setRows((prev) => [...prev, newRow]);
      setSuccessMsg(`Successfully parsed certificate: ${newRow.partyName} resolved as ${newRow.udyamStatus}`);
    } catch (e: any) {
      setErrorMsg(e.message || "An error occurred while parsing the Udyam Certificate PDF.");
    } finally {
      setParsingFile(false);
    }
  };

  const handleFieldChange = (id: string, field: keyof MSMEInvoiceRow, val: any) => {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: val } : r))
    );
  };

  const addRow = () => {
    const newId = (rows.length + 1).toString();
    setRows([
      ...rows,
      {
        id: newId,
        partyName: "",
        invoiceNo: "",
        invoiceDate: new Date().toISOString().split("T")[0],
        paymentDate: "",
        udyamNumber: "",
        udyamStatus: "UNKNOWN",
        hasAgreement: false,
        amount: 0,
      },
    ]);
  };

  const deleteRow = (id: string) => {
    setRows(rows.filter((r) => r.id !== id));
  };

  // Aggregated Stats
  const stats = rows.reduce(
    (acc, row) => {
      const details = calculateRowDetails(row);
      acc.totalAmount += row.amount;
      acc.disallowedExpense += details.disallowedAmount;
      acc.totalInterest += details.interestPenalty;
      if (row.udyamStatus !== "UNKNOWN") {
        acc.verifiedCount += 1;
      }
      return acc;
    },
    { totalAmount: 0, disallowedExpense: 0, totalInterest: 0, verifiedCount: 0 }
  );

  const filteredRows = rows.filter((row) => {
    if (activeTab === "disallowed") {
      return calculateRowDetails(row).disallowedAmount > 0;
    }
    if (activeTab === "verified") {
      return row.udyamStatus !== "UNKNOWN";
    }
    return true;
  });

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
              background: "var(--accent-soft)",
              border: "1px solid var(--accent-glow)",
              borderRadius: 99,
              padding: "5px 14px",
              fontSize: 12,
              color: "var(--accent)",
              fontWeight: 500,
              marginBottom: 16,
            }}
          >
            <ShieldCheck size={12} />
            Section 43B(h) Statutory Compliance Audit
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
            <span className="shimmer-text">MSME Compliance Audit</span>
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
            Deterministic statutory audit under Income Tax Section 43B(h). Upload a vendor's PDF certificate to extract classifications, flag outstanding dues to Micro & Small enterprises beyond the 15/45-day limits, and calculate interest liabilities.
          </p>
        </header>

        {/* PDF Drag & Drop Upload Zone */}
        <section className="animate-fade-up" style={{ animationDelay: "0.05s" }}>
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragActive ? "var(--accent)" : "var(--border-strong)"}`,
              borderRadius: "var(--radius-lg)",
              padding: "32px 24px",
              textAlign: "center",
              cursor: "pointer",
              background: dragActive ? "var(--accent-soft)" : "rgba(255,255,255,0.015)",
              transition: "all 0.2s ease",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 12,
            }}
            onMouseEnter={(e) => {
              if (!dragActive) e.currentTarget.style.borderColor = "var(--accent)";
            }}
            onMouseLeave={(e) => {
              if (!dragActive) e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf"
              style={{ display: "none" }}
            />
            {parsingFile ? (
              <>
                <Loader2 size={32} className="animate-spin" style={{ color: "var(--accent)" }} />
                <div>
                  <h4 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>Parsing Udyam Certificate...</h4>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 0 0" }}>
                    Extracting text metrics via local offline parser
                  </p>
                </div>
              </>
            ) : (
              <>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 14,
                    background: "var(--accent-soft)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: "1px solid var(--accent-glow)",
                  }}
                >
                  <UploadCloud size={20} style={{ color: "var(--accent)" }} />
                </div>
                <div>
                  <h4 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>
                    Drop vendor's Udyam Registration Certificate here or click to browse
                  </h4>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 0 0" }}>
                    Supports official Ministry of MSME Udyam PDF certificates (determines classification instantly)
                  </p>
                </div>
              </>
            )}
          </div>
        </section>

        {/* Notifications */}
        {successMsg && (
          <div
            style={{
              background: "var(--green-soft)",
              border: "1px solid var(--green)",
              color: "var(--green)",
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
              border: "1px solid var(--red)",
              color: "var(--red)",
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

        {/* Indicators */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 16,
          }}
          className="animate-fade-up"
        >
          {[
            {
              label: "Audited Ledger Value",
              value: `₹${stats.totalAmount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
              icon: Coins,
              color: "var(--accent)",
              bg: "var(--accent-soft)",
            },
            {
              label: "43B(h) Disallowed Amount",
              value: `₹${stats.disallowedExpense.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
              icon: ShieldAlert,
              color: stats.disallowedExpense > 0 ? "var(--red)" : "var(--green)",
              bg: stats.disallowedExpense > 0 ? "var(--red-soft)" : "var(--green-soft)",
            },
            {
              label: "Compounded Interest Penalty",
              value: `₹${stats.totalInterest.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
              icon: AlertTriangle,
              color: stats.totalInterest > 0 ? "var(--amber)" : "var(--text-muted)",
              bg: stats.totalInterest > 0 ? "var(--amber-soft)" : "var(--bg-surface)",
            },
            {
              label: "Verified MSME Vendors",
              value: `${stats.verifiedCount} / ${rows.length}`,
              icon: ShieldCheck,
              color: stats.verifiedCount === rows.length ? "var(--green)" : "var(--amber)",
              bg: stats.verifiedCount === rows.length ? "var(--green-soft)" : "var(--amber-soft)",
            },
          ].map((card, idx) => {
            const Icon = card.icon;
            return (
              <div
                key={idx}
                className="glass"
                style={{
                  borderRadius: "var(--radius-md)",
                  padding: "16px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: card.bg,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: `1px solid ${card.color}25`,
                  }}
                >
                  <Icon size={14} style={{ color: card.color }} />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 800,
                      color: "var(--text-primary)",
                      letterSpacing: "-0.02em",
                      lineHeight: 1.1,
                      fontFamily: "monospace",
                    }}
                  >
                    {card.value}
                  </div>
                  <div
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      marginTop: 4,
                    }}
                  >
                    {card.label}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* MSME Audit Table Container */}
        <section
          className="glass"
          style={{
            borderRadius: "var(--radius-lg)",
            overflow: "hidden",
          }}
        >
          {/* Tabs & Actions Bar */}
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: "rgba(255,255,255,0.01)",
            }}
          >
            <div style={{ display: "flex", gap: 8 }}>
              {[
                { id: "all", label: "All Ledgers" },
                { id: "disallowed", label: "Disallowed Expense ⚠" },
                { id: "verified", label: "Verified Only" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  style={{
                    background: activeTab === tab.id ? "var(--accent-soft)" : "transparent",
                    border: activeTab === tab.id ? "1px solid var(--accent-glow)" : "1px solid transparent",
                    borderRadius: "var(--radius-sm)",
                    padding: "4px 10px",
                    color: activeTab === tab.id ? "var(--accent)" : "var(--text-secondary)",
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <button
              onClick={addRow}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                background: "rgba(255,255,255,0.05)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "6px 12px",
                color: "var(--text-primary)",
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.08)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}
            >
              <Plus size={12} />
              Add Ledger Item
            </button>
          </div>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 11,
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "rgba(255,255,255,0.015)",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <th style={{ ...thStyle, width: "160px" }}>Party Account Name</th>
                  <th style={{ ...thStyle, width: "80px" }}>Invoice No</th>
                  <th style={{ ...thStyle, width: "115px" }}>Inv Date</th>
                  <th style={{ ...thStyle, width: "115px" }}>Pay Date</th>
                  <th style={{ ...thStyle, width: "135px" }}>Udyam Number</th>
                  <th style={{ ...thStyle, width: "100px" }}>Statutory Status</th>
                  <th style={{ ...thStyle, width: "50px", textAlign: "center" }}>Agrmt</th>
                  <th style={{ ...thStyle, width: "95px", textAlign: "right" }}>Ledger Amt (₹)</th>
                  <th style={{ ...thStyle, width: "70px", textAlign: "center" }}>Delay</th>
                  <th style={{ ...thStyle, width: "110px", textAlign: "right" }}>43B(h) Disallowed</th>
                  <th style={{ ...thStyle, width: "100px", textAlign: "right" }}>Interest Penalty</th>
                  <th style={{ ...thStyle, width: "110px", textAlign: "center" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const details = calculateRowDetails(row);
                  const isVerified = row.udyamStatus !== "UNKNOWN";
                  const statusColors = {
                    UNKNOWN: { color: "var(--text-secondary)", bg: "var(--bg-surface)" },
                    MICRO: { color: "var(--red)", bg: "var(--red-soft)" },
                    SMALL: { color: "var(--amber)", bg: "var(--amber-soft)" },
                    MEDIUM: { color: "var(--blue)", bg: "var(--blue-soft)" },
                    LARGE: { color: "var(--green)", bg: "var(--green-soft)" },
                  };
                  
                  return (
                    <tr
                      key={row.id}
                      style={{
                        borderBottom: "1px solid var(--border)",
                        background: details.disallowedAmount > 0 ? "rgba(239,68,68,0.015)" : "transparent",
                        transition: "background 0.15s ease",
                      }}
                    >
                      {/* Party Name */}
                      <td style={tdStyle}>
                        <input
                          type="text"
                          className="cell-input"
                          value={row.partyName}
                          onChange={(e) => handleFieldChange(row.id, "partyName", e.target.value)}
                          placeholder="Party Name"
                          style={{ fontWeight: 600, width: "100%" }}
                        />
                      </td>

                      {/* Invoice No */}
                      <td style={tdStyle}>
                        <input
                          type="text"
                          className="cell-input"
                          value={row.invoiceNo}
                          onChange={(e) => handleFieldChange(row.id, "invoiceNo", e.target.value)}
                          placeholder="INV-XXXX"
                          style={{ width: "100%" }}
                        />
                      </td>

                      {/* Invoice Date */}
                      <td style={tdStyle}>
                        <input
                          type="date"
                          className="cell-input"
                          value={row.invoiceDate}
                          onChange={(e) => handleFieldChange(row.id, "invoiceDate", e.target.value)}
                          style={{ width: "100%" }}
                        />
                      </td>

                      {/* Payment Date */}
                      <td style={tdStyle}>
                        <input
                          type="date"
                          className="cell-input"
                          value={row.paymentDate}
                          onChange={(e) => handleFieldChange(row.id, "paymentDate", e.target.value)}
                          style={{ width: "100%" }}
                        />
                        {!row.paymentDate && (
                          <div style={{ fontSize: 8, color: "var(--red)", marginTop: 2, paddingLeft: 6 }}>
                            Unpaid (Comp. today)
                          </div>
                        )}
                      </td>

                      {/* Udyam Number */}
                      <td style={tdStyle}>
                        <input
                          type="text"
                          className="cell-input"
                          value={row.udyamNumber}
                          onChange={(e) => handleFieldChange(row.id, "udyamNumber", e.target.value.toUpperCase())}
                          placeholder="UDYAM-XX-00-0000000"
                          style={{ fontFamily: "monospace", letterSpacing: "0.02em", width: "100%" }}
                        />
                      </td>

                      {/* Statutory Status Dropdown */}
                      <td style={tdStyle}>
                        <select
                          value={row.udyamStatus}
                          onChange={(e) => handleFieldChange(row.id, "udyamStatus", e.target.value as any)}
                          style={{
                            background: statusColors[row.udyamStatus].bg,
                            color: statusColors[row.udyamStatus].color,
                            border: "1px solid var(--border)",
                            borderRadius: 6,
                            padding: "2px 6px",
                            fontSize: 10,
                            fontWeight: 700,
                            outline: "none",
                            cursor: "pointer",
                            width: "100%",
                          }}
                        >
                          <option value="UNKNOWN">UNKNOWN</option>
                          <option value="MICRO">MICRO</option>
                          <option value="SMALL">SMALL</option>
                          <option value="MEDIUM">MEDIUM</option>
                          <option value="LARGE">LARGE</option>
                        </select>
                      </td>

                      {/* Written Agreement? */}
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        <input
                          type="checkbox"
                          checked={row.hasAgreement}
                          onChange={(e) => handleFieldChange(row.id, "hasAgreement", e.target.checked)}
                          style={{
                            cursor: "pointer",
                            width: 13,
                            height: 13,
                          }}
                        />
                      </td>

                      {/* Ledger Amt */}
                      <td style={tdStyle}>
                        <input
                          type="number"
                          className="cell-input"
                          value={row.amount || ""}
                          onChange={(e) => handleFieldChange(row.id, "amount", parseFloat(e.target.value) || 0)}
                          style={{ fontFamily: "monospace", textAlign: "right", width: "100%" }}
                        />
                      </td>

                      {/* Delay */}
                      <td style={{ ...tdStyle, fontFamily: "monospace", textAlign: "center", whiteSpace: "nowrap" }}>
                        {details.delayDays > 0 ? (
                          <span style={{ color: "var(--red)", fontWeight: 700 }}>
                            {details.delayDays}d
                          </span>
                        ) : (
                          <span style={{ color: "var(--green)" }}>0d</span>
                        )}
                        <span style={{ fontSize: 8, color: "var(--text-muted)", display: "block" }}>
                          ({details.limitDays}d limit)
                        </span>
                      </td>

                      {/* 43B(h) Disallowed */}
                      <td style={{ ...tdStyle, fontFamily: "monospace", textAlign: "right", fontWeight: 700 }}>
                        {details.disallowedAmount > 0 ? (
                          <span style={{ color: "var(--red)" }}>
                            ₹{details.disallowedAmount.toFixed(2)}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-muted)" }}>—</span>
                        )}
                      </td>

                      {/* Interest Penalty */}
                      <td style={{ ...tdStyle, fontFamily: "monospace", textAlign: "right", fontWeight: 700 }}>
                        {details.interestPenalty > 0 ? (
                          <span style={{ color: "var(--amber)" }}>
                            ₹{details.interestPenalty.toFixed(2)}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-muted)" }}>—</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td style={tdStyle}>
                        <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                          <button
                            onClick={() => handleVerify(row.id, row.udyamNumber)}
                            disabled={row.isVerifying || !row.udyamNumber}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 2,
                              background: row.isVerifying
                                ? "transparent"
                                : isVerified
                                ? "var(--green-soft)"
                                : "var(--accent-soft)",
                              border: `1px solid ${
                                isVerified ? "var(--green)" : "var(--accent-glow)"
                              }`,
                              borderRadius: 6,
                              padding: "4px 6px",
                              color: isVerified ? "var(--green)" : "var(--accent)",
                              fontSize: 9,
                              fontWeight: 600,
                              cursor: row.isVerifying || !row.udyamNumber ? "not-allowed" : "pointer",
                              opacity: !row.udyamNumber ? 0.4 : 1,
                            }}
                          >
                            {row.isVerifying ? (
                              <>
                                <Loader2 size={8} className="animate-spin" />
                                verifying...
                              </>
                            ) : isVerified ? (
                              "Re-Verify"
                            ) : (
                              "Verify Portal"
                            )}
                          </button>

                          <button
                            onClick={() => deleteRow(row.id)}
                            style={{
                              background: "var(--red-soft)",
                              border: "1px solid var(--red)",
                              borderRadius: 6,
                              padding: "4px 6px",
                              color: "var(--red)",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                            }}
                            title="Delete Row"
                          >
                            <Trash2 size={10} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* Info Card */}
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
          <Info size={20} style={{ color: "var(--accent)", marginTop: 2, flexShrink: 0 }} />
          <div>
            <h3
              style={{
                fontSize: 15,
                fontWeight: 700,
                color: "var(--text-primary)",
                marginBottom: 6,
              }}
            >
              Auditor Guidance Notes: Section 43B(h) & statutory compounding rules
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
                <strong>Applicability:</strong> Appends strictly to transactions with <strong>Micro</strong> and <strong>Small</strong> enterprises. Under current CBDT guidelines, <strong>Medium</strong> enterprises are exempt from Section 43B(h) disallowances.
              </li>
              <li>
                <strong>Time Limits:</strong> Payment must be made within the agreed term, which cannot exceed <strong>45 days</strong>. If there is no written agreement, payments must occur within <strong>15 days</strong> of vendor acceptance.
              </li>
              <li>
                <strong>Income Tax Disallowance:</strong> If payment is delayed past the limit and remains unpaid at year-end, the purchase value is disallowed as business expenditure in that assessment year.
              </li>
              <li>
                <strong>Section 16 Interest Penalty:</strong> For delays, the buyer is liable to pay compound interest to the supplier from the appointed day at <strong>three times</strong> the bank rate notified by the RBI, compounded monthly.
              </li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}

/* ─────────── CSS Inline Styles ─────────── */
const thStyle: React.CSSProperties = {
  padding: "10px 8px",
  textAlign: "left",
  color: "var(--text-muted)",
  fontWeight: 600,
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "6px 6px",
  verticalAlign: "middle",
};
