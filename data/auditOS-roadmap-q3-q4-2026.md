# AuditOS — Product & Technical Roadmap: Q3–Q4 2026 (3–6 Months)

**Date:** June 29, 2026  
**Horizon:** July 2026 → December 2026  
**Basis:** Competitive intelligence on AI Accountant and MindBridge  
**North Star:** Become the dominant AI audit tool for Indian CA firms by winning on accuracy, Indian compliance depth, and CA-native workflow design — not by matching generic accounting automation.

---

## Competitive Context: Why This Roadmap Exists

| Finding | Strategic Implication |
|---|---|
| AI Accountant's real extraction accuracy is 60–70% overall (their own blog admits it); headline "99%" is field-level on clean docs only | Beat them on a published, reproducible accuracy benchmark |
| AI Accountant has no disclosed vector DB, no embedding-based CoA mapping, no semantic search | Build semantic intelligence layer as a technical moat they can't replicate without an architecture rewrite |
| AI Accountant explicitly has no 43B(h) MSME vendor payment tracking | Ship this feature first and loudest |
| AI Accountant requires a 2–4 week model learning period before hitting peak accuracy | Zero-shot accuracy from day one is a direct differentiator |
| MindBridge has SOC 2 Type 2 + ISO 27001/17/18 (6 certifications) — required by enterprise audit clients | Begin SOC 2 Type 2 readiness now; it takes 6–12 months minimum |
| MindBridge uses an explainability-first ensemble (each flag shows exactly why) | Every extraction and reconciliation decision in AuditOS must be explainable |
| MindBridge has zero Tally support, zero GST coverage, zero Indian market presence | The entire Indian CA / SME market is uncontested at the enterprise level |
| AI Accountant covers GSTR-1/2A/2B/3B/9/9C, e-invoice IRP, TDS, PF/ESIC, MCA | Full Indian compliance stack is table stakes for market leadership; we're behind on TDS and payroll |

---

## Current State (as of June 30, 2026)

**Shipped and working:**
- 9-stage extraction pipeline + 8-stage deterministic reconciliation
- GSTR-2B reconciliation (backend engine complete)
- ITC Section 17(5) deterministic rules + ITC eligibility Excel export
- GSTR-1 JSON export
- Multi-tenant schema (Tenant model, tenant_id on all entities, admin CRUD)
- Session persistence (BatchJob resume across app restarts)
- Duplicate invoice detection
- SHA-256 Redis PDF cache (7-day TTL, instant dedup)
- Async OCR via Celery (dedicated `ocr` queue, EasyOCR in ThreadPoolExecutor)
- Sentry observability + structured JSON request logging
- JWT auth hardening + circuit breaker
- Place-of-supply auto-derivation from buyer GSTIN
- Firm Settings page, sidebar firm name display

**Remaining from current sprint (must close before new initiatives):**
1. IRN / e-invoice QR verification
2. GSTR-2B reconciliation UI
3. Role management in Firm Settings (CA admin → staff → client)
4. Celery worker health badge in dashboard

---

## Roadmap Overview

```
JULY        AUGUST       SEPTEMBER    OCTOBER      NOVEMBER     DECEMBER
│           │            │            │            │            │
▼ PHASE 1 ──┼── PHASE 2 ─┼────────────┼── PHASE 3 ─┼────────────┼──▶
Sprint      Semantic     CA Platform  ERP          Compliance   API &
Closeout    Intelligence Features     Expansion    & Security   Enterprise
& Accuracy  Layer                                  Readiness    Layer
```

---

## Phase 1 — Sprint Closeout + Accuracy Foundation
### July 2026 (Weeks 1–4)

**Goal:** Ship the four remaining items, then establish an accuracy baseline that definitively beats AI Accountant's 60–70% overall figure.

---

### 1.1 Close Remaining Sprint Items

| Task | File / Area | Priority |
|---|---|---|
| IRN / e-invoice QR verification | `backend/core/extraction/extractor/` + IRP API | P0 |
| GSTR-2B reconciliation UI | `frontend/src/app/reconciliation/page.tsx` | P0 |
| Role management (CA admin / staff / viewer) | `frontend/src/app/firm-settings/` + `backend/services/auth.py` | P0 |
| Celery worker health badge | `frontend/src/components/Sidebar.tsx` + `/api/health/workers` | P1 |

---

### 1.2 Establish Accuracy Benchmark (Competitive Weapon)

**Why:** AI Accountant claims 99% but their own blog reveals 60–70% overall. Capterra users report ~80% on handwritten docs. We need a published, honest benchmark that becomes our primary sales differentiator.

**Implementation:**
- Build a labeled test dataset: 200 invoices across clean PDFs, scanned invoices, handwritten, and bilingual docs
- Run the extraction pipeline against this set; record field-level vs. document-level accuracy
- Define three tiers matching AI Accountant's own categories: critical fields (GSTIN, totals), line items, overall (all fields correct)
- Target: >85% overall document accuracy on clean PDFs; >75% on scanned; publish these numbers honestly

**Where it lands in the stack:** New `backend/core/extraction/benchmarks/` module; CLI script that runs the labeled set and outputs a JSON accuracy report.

---

### 1.3 Confidence-Tier Routing (Match AI Accountant's Three-Tier System)

**Why:** AI Accountant routes documents by confidence (≥90% auto-approve, 70–90% quick review, <70% detailed review). We need parity or better.

**Implementation:**
- Add a `confidence_score` field to `InvoiceTask` model (`backend/models.py`)
- Extraction pipeline computes per-field confidence; aggregates to document-level score
- API response includes confidence tier: `AUTO` / `QUICK_REVIEW` / `DETAIL_REVIEW`
- Frontend `ReviewPanel` shows confidence badge per invoice

---

### 1.4 Bank Statement Processing (Phase 1 of 150+ Format Support)

**Why:** AI Accountant supports 150+ Indian bank statement formats. This is a major gap. Start with the top 10 banks by SME market share (SBI, HDFC, ICICI, Axis, Kotak).

**Implementation:**
- Add `document_type: "bank_statement"` routing in `backend/core/extraction/pipeline.py`
- Build bank-specific prompt in `item_extractor.py`: extracts date, narration, debit, credit, balance, transaction reference
- UPI/IFSC/NEFT pattern extraction from narration column
- Output: structured `BankTransaction` model + Excel export with ledger mapping
- New endpoint: `POST /api/bank/upload` → `GET /api/bank/jobs/{id}/transactions`

---

## Phase 2 — Semantic Intelligence Layer
### August – September 2026 (Weeks 5–12)

**Goal:** Build the technical moat AI Accountant does not have — a vector-embedding-based semantic intelligence layer for CoA mapping, vendor classification, and anomaly detection. This is the architecture they'd need 6–12 months to replicate.

---

### 2.1 pgvector on PostgreSQL + Embedding Pipeline

**Why:** AI Accountant disclosed zero vector DB or embedding architecture. Adding pgvector to our existing PostgreSQL (Supabase) is a 1-day infrastructure change that unlocks the entire semantic layer.

**Implementation:**
- Enable `pgvector` extension on Supabase: `CREATE EXTENSION IF NOT EXISTS vector;`
- Add `CoAEntry` model: `id`, `tenant_id`, `ledger_name`, `description`, `embedding vector(1536)`, `parent_group`, `is_active`
- Add `VendorProfile` model: `id`, `tenant_id`, `vendor_name`, `gstin`, `embedding vector(1536)`, `default_ledger_id`, `industry_category`, `avg_invoice_value`
- Embedding generation: `backend/services/embedding_service.py` — wraps Claude or OpenAI embedding API; caches embeddings in Redis (7-day TTL, keyed by `sha256(text)`)
- Migration script: generate embeddings for all existing CoA entries on first install

---

### 2.2 Semantic Chart of Accounts Mapping

**Why:** AI Accountant's CoA mapping "learns from corrections over time" but has a 2–4 week ramp. We can achieve better zero-shot accuracy using semantic similarity before any learning occurs.

**Current state:** Extraction pipeline sends raw vendor + line item description to the LLM and asks it to guess the ledger. This is prompt-dependent and inconsistent across tenants.

**New approach:**
1. Client uploads their CoA (CSV or synced from Tally via XML)
2. Each CoA entry gets an embedding stored in `CoAEntry.embedding`
3. At extraction time: embed the invoice line item description → `cosine_similarity()` search against tenant's CoA → return top-3 matches with similarity scores
4. LLM receives: extracted text + top-3 candidate ledgers + their similarity scores → makes final mapping with this context
5. User corrections stored as `UserAnnotation` (already in models) → retrain embedding alignment over time

**API:** `POST /api/coa/upload`, `GET /api/coa/entries`, `POST /api/coa/suggest` (takes line item text, returns ranked ledger suggestions)

**Files:** `backend/services/embedding_service.py` (new), `backend/services/coa_mapper.py` (new), `backend/core/extraction/llm_call.py` (modify to use CoA context)

---

### 2.3 MSME 43B(h) Vendor Payment Tracker

**Why:** This is the clearest feature gap in the market. AI Accountant does not have an explicit 43B(h) tracker. It is a compliance obligation for every CA managing MSME clients — payments to MSME vendors must be settled within 45 days or the buyer loses the expense deduction.

**Implementation:**
- Add `vendor_msme_status` field to `VendorProfile`: `MICRO / SMALL / MEDIUM / NOT_REGISTERED / UNKNOWN`
- MSME verification: GSTIN-based lookup (GSTN Udyam portal API or manual flag from CA)
- Add `payment_due_date` and `payment_status` to `PurchaseLineItem`
- Compute: `payment_due_date = invoice_date + 45 days`; flag any unpaid items past 45 days
- New dashboard widget: "43B(h) Risk Exposure — ₹X of expense deductions at risk (Y vendors)"
- Excel export: "43B(h) Compliance Sheet" — vendor, invoice date, due date, amount, status

**Files:** `backend/services/msme_tracker.py` (new), `backend/models.py` (add fields), `frontend/src/app/invoice-extractor/page.tsx` (risk widget)

---

### 2.4 Ensemble Anomaly Detection for ITC & GL

**Why:** MindBridge's core moat is a 60+ algorithm ensemble. We don't need 60 algorithms — we need 10–12 high-signal ones tuned for Indian GST workflows, with per-flag explainability so every anomaly shows *why* it was flagged.

**Algorithms to implement (Phase 2, focus on ITC and AP):**

| Algorithm | Detection Target | Implementation |
|---|---|---|
| ITC Claim Z-Score | ITC amount significantly above tenant's historical mean | Per-vendor rolling mean + stddev stored in `VendorProfile` |
| Benford's Law (1-digit) | Invoice amount digit frequency fraud | Run on batch totals; flag deviations >15% from Benford distribution |
| Duplicate Invoice Detection | Same vendor + amount + date within 30-day window | Already shipped — extend with fuzzy GSTIN matching |
| Reverse Charge Anomaly | RCM marked on invoice where vendor is GST-registered | Cross-check GSTIN registration status |
| ITC on Blocked Supplies | Section 17(5) violations | Already shipped deterministically — add confidence score |
| Unusual GSTIN Pattern | Buyer/seller GSTIN state mismatch vs. place of supply | Already have POS derivation — add cross-check |
| Round-Amount Bias | Disproportionate round-number invoices (fraud signal) | Flag invoices where amount mod 500 = 0 at unusual rates |
| Missing IRN on Large Invoices | E-invoicing mandatory above ₹5L threshold | Check IRN presence for all invoices ≥ ₹500,000 |

**Explainability:** Every anomaly flag must include: `rule_name`, `description`, `severity` (LOW/MEDIUM/HIGH), `evidence` (the specific data that triggered it), `recommended_action`. This is stored in `ObservabilityLog` and surfaces in the UI as an expandable flag.

**Files:** `backend/services/anomaly_detector.py` (new), `backend/models.py` (add AnomalyFlag model), `frontend/src/components/ReviewPanel.tsx` (expandable flag cards)

---

### 2.5 Natural Language Financial Query Interface

**Why:** AI Accountant and MindBridge both confirmed NL query interfaces. For AuditOS, this means CAs can type "Show me all invoices from vendor X where ITC was blocked this quarter" instead of filtering tables.

**Implementation:**
- `POST /api/query` endpoint: accepts `{ "q": "natural language question", "batch_id": "..." }`
- LLM converts NL question → SQL query scoped to tenant's data (with strict parameterized queries to prevent injection)
- Returns structured JSON + a human-readable summary sentence
- Frontend: floating query bar in `invoice-extractor/page.tsx` with response card

**Scope:** Phase 2 query targets are `InvoiceTask`, `PurchaseLineItem`, `SalesLineItem`, `AnomalyFlag`. No cross-tenant queries ever.

---

## Phase 3 — ERP Expansion + CA Platform Features
### October 2026 (Weeks 13–17)

**Goal:** Add Zoho Books as a second ERP integration (AI Accountant's secondary primary), and build the CA firm portfolio features that differentiate AuditOS from single-client tools.

---

### 3.1 Zoho Books Integration

**Why:** AI Accountant's second major integration after Tally is Zoho Books (OAuth API). This covers CA firms whose clients use Zoho instead of Tally — a meaningful segment of mid-size Indian businesses.

**Implementation:**
- OAuth 2.0 flow: `backend/services/zoho_connector.py`
- Sync: Chart of Accounts, Vendor list, Purchase Bills, Payment records
- Bi-directional: read from Zoho Books → extract → reconcile → post mapped entries back via Zoho Books API
- Credential storage: encrypted per-tenant in database (not in .env)

---

### 3.2 Multi-Client Portfolio Dashboard for CAs

**Why:** CA firms manage 30–100+ client entities. AI Accountant has a portfolio-level dashboard; we need to match and exceed it with audit-specific views.

**Implementation:**
- New route: `frontend/src/app/portfolio/page.tsx`
- Per-client cards: last sync date, pending review count, anomaly count, GSTR-2B match rate, 43B(h) risk exposure
- Sortable by: "Most anomalies", "Oldest pending review", "43B(h) risk amount"
- Bulk action: trigger extraction for multiple clients in one click
- SLA tracking: invoices pending review for >24h surface as overdue (matching AI Accountant's exception queue SLA tiers)

---

### 3.3 Tally Sync Improvements

**Current:** XML over HTTP via local connector.  
**Needed:** Match AI Accountant's documented feature set.

- Incremental sync using `AlterID` / `LastAlterID` (only fetch changed records) — implement if not already done
- Write-back: post reconciled vouchers to Tally with voucher type, cost centre, narration
- Support TallyPrime + Tally ERP 9 multi-company configurations
- Sync status indicator in UI: last sync timestamp, records synced, pending write-backs

---

### 3.4 Handwriting & Regional Language Support

**Why:** AI Accountant claims 95%+ on handwritten invoices (Capterra puts it at ~80%). Handwritten invoices are extremely common in Indian B2B trade — kiranas, small manufacturers, transporters.

**Implementation:**
- Upgrade OCR pipeline: add a dedicated ICR (Intelligent Character Recognition) pass for handwriting detection
- Language detection layer: identify if invoice contains Devanagari, Tamil, Telugu, Kannada, or Bengali scripts → route to appropriate OCR model
- EasyOCR already supports 80+ languages including Devanagari — enable language list in `document_core.py`
- Confidence penalty applied to handwritten/regional docs; route to DETAIL_REVIEW tier automatically

---

## Phase 4 — Compliance, Security & Enterprise Readiness
### November – December 2026 (Weeks 18–26)

**Goal:** Build the trust infrastructure that MindBridge has and AI Accountant lacks. SOC 2 Type 2 readiness is the primary enterprise unlock.

---

### 4.1 SOC 2 Type 2 Readiness

**Why:** MindBridge has SOC 1/2/3 Type 2 + three ISO certifications. AI Accountant has ISO 27001 + SOC 2. Any CA firm managing enterprise clients will require at minimum SOC 2 Type 2 before signing an annual contract. The observation period for SOC 2 Type 2 is typically 6 months — starting now means earliest certification is mid-2027.

**Initiative (November 2026 start):**
- Engage a SOC 2 audit firm (A-LIGN or equivalent)
- Map existing controls against SOC 2 Trust Service Criteria: Security, Availability, Processing Integrity, Confidentiality
- Gap analysis: identify missing controls (penetration testing, change management, vendor risk, incident response, access reviews)
- Implement gaps: formal access review process, penetration test (annual), incident response runbook, vendor security questionnaires, data retention + deletion policy, backup testing

**Controls already partially in place:** Immutable audit logs, RBAC, JWT auth hardening, Sentry observability, Redis cache, multi-tenant isolation.

**Controls to implement:**
- Formal change management process (PR review gates, staging environment mandatory)
- Penetration test by qualified third party
- Data classification policy
- Employee security training documentation
- DPDP Act (India's data protection law) compliance map

---

### 4.2 GSTR-9 / GSTR-9C Annual Return Reconciliation

**Why:** AI Accountant supports GSTR-9 and GSTR-9C. Annual return season (March–June every year) is the highest-value CA engagement period. Not supporting this leaves AuditOS unusable for the most important workflow of the year.

**Implementation:**
- GSTR-9 data model: 19 tables / schedules from the annual return
- Reconciliation logic: aggregate GSTR-1 filed data vs. books vs. GSTR-3B vs. GSTR-2B over the full financial year
- Delta detection: flag discrepancies across monthly filings for the year
- Output: Summary of ITC differences, output tax differences, unclaimed ITC carryforward, late-fee liability

---

### 4.3 TDS Automation (Phase 1)

**Why:** AI Accountant covers TDS under Section 192 (salary) + 194 series (vendor payments), Form 24Q, 26Q, Form 16/16A, TRACES integration. TDS automation is part of every CA's monthly compliance cycle for all clients.

**Phase 1 scope (December 2026):**
- TDS deductibility detection on purchase invoices: identify payments above threshold for Sections 194C (contractors), 194J (professionals), 194H (commission)
- Flag invoices where TDS should have been deducted but wasn't
- TDS calculation: deduct correct rate, compute net payable
- Monthly TDS liability summary report per client

**Phase 2 (post-roadmap):** Form 26Q generation, TRACES filing integration, challan deposit, Form 16A generation.

---

### 4.4 On-Premise / Hybrid Deployment Option

**Why:** AI Accountant is cloud-only. MindBridge offers on-prem (though discourages it). Enterprise CA firms managing RBI-regulated clients, NBFCs, or listed companies often cannot send financial data to a third-party SaaS. This segment is completely unserved.

**Implementation:**
- Docker Compose production manifest: `FastAPI + PostgreSQL + Redis + Celery workers` all containerized
- `docker-compose.prod.yml` with volume mounts for GCS-equivalent local blob storage (MinIO)
- Environment switch: `DEPLOYMENT_MODE=onprem` skips GCS, routes to local MinIO
- Licensing model: on-prem license key validation (annual renewal, offline grace period of 30 days)
- Minimum hardware spec to publish: 8 vCPU, 32 GB RAM, 500 GB SSD (comparable to MindBridge's published spec)

---

### 4.5 REST API Layer for CA Firm Integrations

**Why:** MindBridge has a 130+ endpoint REST API with a Python SDK (pip-installable), OpenAPI/Swagger specs, and a proprietary query language (MQL). This enables enterprise CA firms and ERP vendors to embed AuditOS into their own workflows.

**Phase 4 scope:**
- OpenAPI 3.0 spec generation from FastAPI routes (FastAPI does this natively — just expose `/openapi.json`)
- API key management: `ApiKey` model (tenant-scoped, revocable, rate-limited)
- New endpoints behind API key auth: batch upload, job status poll, results export (structured JSON)
- Webhook support: `POST /api/webhooks/register` — push notification on batch completion / anomaly detected
- Rate limiting: `100 req/min` per API key (using Redis sliding window)
- `GET /api/openapi.json` and interactive Swagger UI at `/api/docs`

---

## Success Metrics by Phase

| Phase | Key Metric | Target |
|---|---|---|
| Phase 1 | Overall extraction accuracy (clean PDFs) | >85% (vs AI Accountant's 60–70%) |
| Phase 1 | Processing time per invoice | <10 seconds P95 |
| Phase 2 | CoA mapping accuracy (zero-shot, first invoice) | >80% correct ledger (vs AI Accountant's 2–4 week ramp) |
| Phase 2 | 43B(h) risk flagged per client per month | Surfaced in dashboard; tracked over time |
| Phase 2 | Anomaly recall (known test cases) | >90% true positives on labeled anomaly set |
| Phase 3 | GSTR-9 reconciliation turnaround | < 30 minutes per client (was: days of manual work) |
| Phase 3 | Bank statement formats supported | Top 10 banks (SBI, HDFC, ICICI, Axis, Kotak, Yes Bank, Kotak, BoB, IDFC, Federal) |
| Phase 4 | SOC 2 Type 2 observation period started | November 2026 |
| Phase 4 | On-prem Docker deployment functional | December 2026 |

---

## Feature → Competitive Positioning Map

| AuditOS Feature | vs AI Accountant | vs MindBridge |
|---|---|---|
| Published accuracy benchmark (>85% overall) | Beats their real 60–70% figure; exposes inflated claims | Not applicable (MindBridge doesn't do document extraction) |
| Zero-shot CoA mapping via embeddings | Eliminates their 2–4 week learning ramp | Not applicable |
| 43B(h) MSME tracker | Feature they don't have — first mover | Feature they don't have — first mover |
| Ensemble anomaly detection (8 rules, explainable) | Matches their ITC anomaly claims with proof | Narrower scope but India-tuned; they have 60+ algorithms globally |
| SOC 2 Type 2 (readiness) | They have it — we need parity | They have SOC 1/2/3 — we start catch-up |
| On-prem deployment option | They are cloud-only — we win this segment | They offer on-prem — we match |
| GSTR-9/9C reconciliation | Matches their stated coverage | Not applicable |
| Zoho Books integration | Matches their secondary ERP | Not applicable |
| REST API + webhooks | Not present in their disclosed feature set | They have 130+ endpoints + Python SDK — we build toward this |
| Natural language query | They have a NL dashboard | They have an agentic interface — we build equivalent |

---

## What Not To Build in This Window

The following are out of scope for Q3–Q4 2026. Adding them would dilute focus without competitive payoff:

- **Payroll compliance (PF/ESIC/PT)** — AI Accountant has this but it is not a CA audit workflow; it is a bookkeeping service. AuditOS is an audit tool, not a managed accounting service.
- **ROC/MCA filings** — same rationale; requires regulatory filings infrastructure, not core audit value.
- **Account Aggregator (RBI AA) integration** — high complexity, requires RBI FIU registration, 6–12 month compliance process. Evaluate post-SOC 2.
- **e-commerce integrations (Shopify, Amazon)** — SME bookkeeping, not CA audit.
- **60+ algorithm ensemble (MindBridge-scale)** — 8–12 high-signal India-specific algorithms outperform 60 generic global ones for this market. Depth over breadth.
- **KPMG / Big 4 partnership** — not the target market for the next 6 months.

---

## Initiative Summary Table

| # | Initiative | Phase | Effort | Competitive Basis |
|---|---|---|---|---|
| 1.1 | Close sprint: IRN, GSTR-2B UI, roles, health badge | 1 | S | Current commitments |
| 1.2 | Accuracy benchmark dataset + measurement | 1 | M | Beat AI Accountant's 60–70% |
| 1.3 | Confidence-tier routing (AUTO/QUICK/DETAIL) | 1 | S | Match AI Accountant's three-tier system |
| 1.4 | Bank statement processing (top 10 banks) | 1 | L | Close gap vs AI Accountant's 150+ formats |
| 2.1 | pgvector extension + CoAEntry + VendorProfile models | 2 | S | Infrastructure for entire semantic layer |
| 2.2 | Semantic CoA mapping via embeddings | 2 | L | AI Accountant has no disclosed embedding layer |
| 2.3 | MSME 43B(h) vendor payment tracker | 2 | M | No competitor has this explicitly |
| 2.4 | Ensemble anomaly detection (8 algorithms, explainable) | 2 | L | MindBridge benchmark; India-tuned |
| 2.5 | Natural language financial query interface | 2 | M | Both competitors confirmed this feature |
| 3.1 | Zoho Books integration (OAuth, bi-directional) | 3 | L | AI Accountant's secondary ERP |
| 3.2 | Multi-client portfolio dashboard for CA firms | 3 | M | AI Accountant has portfolio view |
| 3.3 | Tally sync: AlterID incremental + write-back polish | 3 | M | Match AI Accountant's Tally connector |
| 3.4 | Handwriting + regional language OCR | 3 | M | AI Accountant's ICR claim |
| 4.1 | SOC 2 Type 2 readiness (gap analysis + controls) | 4 | XL | MindBridge has 6 certifications; AI Accountant has 2 |
| 4.2 | GSTR-9 / GSTR-9C annual return reconciliation | 4 | L | AI Accountant covers this; critical for CA season |
| 4.3 | TDS detection on purchase invoices (Phase 1) | 4 | M | AI Accountant covers TDS; table stakes |
| 4.4 | On-prem Docker deployment (MinIO + compose) | 4 | L | AI Accountant cloud-only — we win on-prem segment |
| 4.5 | REST API layer + webhooks + API key management | 4 | L | MindBridge benchmark for enterprise integration |

**Effort key:** S = 1–3 days · M = 1–2 weeks · L = 3–4 weeks · XL = ongoing (2–3 months)
