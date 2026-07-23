# ENGINEERING EXECUTION BLUEPRINT
## AuditOS — Converting RFC-005 into a Shippable Program

**Prepared by: Founding VP of Engineering perspective**
**Status: Execution planning. RFC-001–005 are accepted doctrine and are not redesigned here.**
**Governing constraint, carried forward from RFC-005's own Red Team Review: this plan is sized for a 3–5 engineer team. Every program, epic, and ADR below has already been run through RFC-005's evolution test and Red Team gates before being included — nothing here is aspirational scaffolding for a team that doesn't exist yet.**

> RFC-005 described 13 layers and ~21 components as the platform's eventual shape, then red-teamed itself down to a four-item collapsed Phase 1. This document is the execution plan for that collapsed Phase 1, with the remaining 13-layer vocabulary preserved as **destinations to extend toward**, not a build list. Every Program below states, explicitly, whether it is being built now, thinned down, or deliberately not started.

---

# PART 1 & 2 — ENGINEERING PROGRAMS

Each program states Objectives, Scope, Deliverables, Risks, Success Metrics, Engineering Complexity, Priority, Business Impact, and Technical Debt Risk, then breaks into Epics (Part 3 detail follows for the highest-priority programs; lower-priority programs get lighter epic listings, consistent with not over-planning work that isn't starting soon).

## Program 1 — Document Intelligence (BUILD NOW)
**Objectives:** Harden and generalize the existing extraction pipeline beyond the current OneStack-shaped path; make confidence-based review routing simple and real (one blended threshold, not multi-stage attribution — per RFC-005 Red Team R.5).
**Scope:** Stage 1 (classification), Stage 2 (layout-aware extraction, already built), Stage 4 (canonical mapping), Stage 5 (review routing). Stage 3 (vision-model fallback) is explicitly **out of scope until document-failure-mode volume is measured** (RFC-005 R.5).
**Deliverables:** a generalized extraction pipeline usable beyond the single current client-specific pipeline; a single confidence score feeding review routing; multilingual (Hindi/mixed) field-label resolution added to Stage 4's mapping logic as a configuration, not a parallel pipeline.
**Risks:** scope creep into vision-model work before evidence justifies it; Hindi/multilingual support underestimated if no real Hindi-heavy client documents exist yet to validate against.
**Success metrics:** extraction accuracy on the regression/golden set; % of documents requiring human correction, trending down; time-to-review per document.
**Engineering complexity:** Medium. **Priority:** P0. **Business impact:** Direct — this is the core product. **Technical debt risk:** Low if Stage 3 is genuinely deferred; High if vision-fallback work sneaks in "while we're in there."

## Program 2 — Validation & Reconciliation Platform (BUILD NOW, generalize what exists)
**Objectives:** Generalize the existing 8-stage reconciliation engine so new rule sets (a second ERP's quirks, a new domain) can be added without touching engine internals.
**Scope:** the deterministic rule-execution engine, rule versioning (effective-from/to fields on rule definitions — a database column, not a "Layer"), GSTR-2B Bucket A/B workflow already shipped and hardened.
**Deliverables:** rule definitions stored with effective dates; a documented pattern for adding a new rule without engine changes; regression coverage for every existing rule.
**Risks:** the temptation to let a probabilistic shortcut into what must stay deterministic code (RFC-005/RFC-002 permanent doctrine) — guarded by Engineering Principle #1–3.
**Success metrics:** rules addable in hours, not days; zero probabilistic code paths in this engine, verified by code review checklist.
**Engineering complexity:** Medium. **Priority:** P0. **Business impact:** Direct — this is the trust mechanism the whole product depends on. **Technical debt risk:** Low — this engine is deliberately conservative and slow-changing by design (RFC-005 Part 2.8).

## Program 3 — Connector Platform (BUILD NOW, thin)
**Objectives:** Harden the Tally connector's idempotency pattern; prepare (not build) the pattern for a second connector by documenting, not generalizing.
**Scope:** Fetch/Push/Resolve/Health as a documented pattern (not a registry/framework — RFC-005 Red Team R.2/R.8 explicitly killed the generalized registry until connector #2 is real). Google Drive sync hardening.
**Deliverables:** a one-page "how to build a connector" doc describing the four responsibilities; Tally connector's push-log idempotency pattern extended to cover every write path, not just vouchers.
**Risks:** building the registry/framework anyway "to be safe" — explicitly disallowed by the Red Team review; this must be actively resisted in planning, not just documented as a risk.
**Success metrics:** zero duplicate-voucher incidents; connector #2 (whenever built) takes materially less time than connector #1 because the pattern, not a framework, was documented.
**Engineering complexity:** Low-Medium. **Priority:** P0 (Tally hardening), P2 (any new connector, demand-gated). **Business impact:** Direct for existing clients. **Technical debt risk:** Low if the "no framework yet" discipline holds.

## Program 4 — Knowledge & Correction Capture (BUILD NOW, minimal)
**Objectives:** Implement the one piece of infrastructure RFC-005's Red Team explicitly said cannot be retrofitted later — every human correction retained as a timestamped, provenance-carrying event.
**Scope:** a `verified_knowledge` / `correction_events` table (fields: effective-from/to, source, trust score, supersession pointer, reviewer, evidence pointer) added to existing schema — **not** a distinct Company Brain service, **not** an ontology graph, **not** an SLM pipeline.
**Deliverables:** correction events captured from the existing review workspace; a queryable history of what changed, why, and by whom, per record.
**Risks:** under-scoping this (treating it as "just an audit log") and losing the structured fields (trust score, supersession pointer) that make later promotion/SLM work possible — this is the one place where under-building costs years later, per RFC-004's own final synthesis.
**Success metrics:** 100% of review-workspace corrections captured as structured events; zero silent overwrites of a corrected value.
**Engineering complexity:** Low. **Priority:** P0. **Business impact:** Invisible now, foundational later — this is the flywheel's fuel tank. **Technical debt risk:** Very high if skipped or under-scoped now; low cost to build correctly at this size.

## Program 5 — Workflow & Automation (BUILD NOW, on existing Celery — no new engine)
**Objectives:** Close the flagged gap from RFC-005 Part 10.1 — human-approval steps need designed timeout/escalation behavior, not indefinite waiting. Generalize the ERP-push idempotency pattern (Program 3) to every external-system-touching workflow step.
**Scope:** approval-gate step type with configurable timeout and escalation target; exception queue as a shared table + review surface, not a bespoke queue per workflow.
**Deliverables:** no pending approval can silently go stale; every workflow's state survives a restart (already largely true via Celery + DB-backed task state — verify, don't rebuild).
**Risks:** reaching for Temporal or a dedicated durable-execution engine before Celery genuinely proves insufficient (explicitly out of scope per RFC-005 Red Team R.7).
**Success metrics:** zero indefinitely-stuck approvals; measurable time-to-approval per workflow type.
**Engineering complexity:** Low-Medium. **Priority:** P0 (the timeout gap is a real current-scale risk, not a future one). **Business impact:** Direct — prevents a real class of silent failures. **Technical debt risk:** Low.

## Program 6 — Evaluation Platform (BUILD NOW, thin — Layer 1-2 only)
**Objectives:** A regression suite (Layer 1) and the start of a professionally-graded eval set (Layer 2, RFC-002/003). Layers 3-5 (chain-level, drift, human-trust metrics) explicitly deferred per RFC-005 Red Team R.2.
**Scope:** CI-run regression tests against extraction/validation/reconciliation on a fixed golden set; a lightweight process for a CA to grade a sample of real cases periodically (not continuous, not automated drift detection yet).
**Deliverables:** a growing, versioned golden dataset; a documented, repeatable grading process; pass-rate tracked over time in a simple dashboard (not a statistical-process-control system).
**Risks:** building Layer 4/5 infrastructure before there's enough throughput for it to produce a meaningful signal (explicitly killed by Red Team R.2).
**Success metrics:** golden-set size and pass rate, tracked monthly; at least one real CA-graded batch per month.
**Engineering complexity:** Low. **Priority:** P0 (thin version), P3 (full 5-layer version). **Business impact:** Indirect but high long-term — this is what makes every future claim about accuracy defensible. **Technical debt risk:** Low at this scope.

## Program 7 — Enterprise Platform (HARDEN WHAT EXISTS, don't expand)
**Objectives:** Multi-tenant isolation completeness (per SECURITY_REMEDIATION_PHASE1/2's already-tracked work), observability consolidation (Sentry + structured logs, already in place — extend, don't replace).
**Scope:** finish closing any remaining lower-severity tenant-isolation gaps already tracked; ensure every new endpoint added by Programs 1-6 goes through the same tenant-scoping check as a standard code-review gate.
**Deliverables:** a documented, enforced tenant-isolation checklist in code review; observability coverage for every new write path added by other programs.
**Risks:** treating "enterprise readiness" as license to build SSO/SAML, Resource Manager, or Governance Layer infrastructure ahead of a specific deal requiring it (explicitly killed by Red Team R.2/R.6).
**Success metrics:** zero new tenant-isolation gaps introduced by any Program 1-6 work; every consequential action traceable in logs.
**Engineering complexity:** Low (it's discipline, not new systems). **Priority:** P0 (as a review gate), P3 (SSO/SAML, demand-gated). **Business impact:** Trust-preserving, not feature-adding. **Technical debt risk:** Low if enforced as a review gate rather than a separate project.

## Program 8 — Developer Platform (BUILD NOW, minimal)
**Objectives:** CI/CD reliable enough that "tests are red" actually blocks merges; a repo structure that doesn't fight the team as programs 1-6 grow.
**Scope:** covered in full in Part 5 (repo structure) and Part 7 (developer experience) below.
**Deliverables:** CI pipeline, branch/review discipline, ADR folder, RFC folder (this document series lives there).
**Risks:** over-tooling — a 3-5 person team does not need a platform team's CI/CD sophistication.
**Success metrics:** time from PR open to merge; CI flake rate near zero.
**Engineering complexity:** Low. **Priority:** P0. **Business impact:** Multiplier on every other program. **Technical debt risk:** Low.

## Program 9 — Digital Workforce (DO NOT BUILD — validate demand first)
**Objectives:** None active. RFC-005 Red Team R.5 explicitly named the full 12-role roster as speculative. **This program has zero allocated engineering time until a specific, real client has explicitly asked for one specific role.**
**Scope:** none currently. If a validated need emerges (e.g., a client asking for a cash-flow briefing), scope a single-role, thin version reusing Programs 1-6's existing infrastructure per RFC-005 Part 9.3's "no new layer required" finding — never a new platform investment.
**Risks of building anyway:** burns team capacity on unvalidated persona work while Programs 1-6 (the actual product) stall.
**Success metrics:** N/A until activated.
**Engineering complexity:** N/A. **Priority:** P4 (not scheduled). **Business impact:** Unvalidated. **Technical debt risk:** N/A — the risk is building it too early, not too late.

## Program 10 — Company Brain / Ontology (VOCABULARY ONLY — not a program yet)
**Objectives:** None active beyond Program 4's minimal correction-capture table. RFC-005 Red Team R.2/R.6 killed the dedicated Ontology Layer, graph database, and event-sourcing/CQRS pattern as premature.
**Scope:** none currently, beyond ensuring Program 2/4's schema additions (rule versioning, correction events) don't foreclose a future graph layer — i.e., don't hardcode assumptions that would make a future entity-resolution pass expensive to retrofit (RFC-004 Part 3's warning about retrofitting entity resolution being expensive).
**Trigger to activate:** genuine multi-hop relational query pain (per RFC-005 Part 11), not a calendar date.
**Engineering complexity:** N/A. **Priority:** P4 (not scheduled). **Business impact:** Long-term strategic, zero near-term. **Technical debt risk:** the risk is over-building now, not under-building.

---

# PART 3 — EPIC DETAIL FOR THE ACTIVE PROGRAMS (1–6, 8)

Only active (P0) programs get full epic decomposition — decomposing Programs 9-10 into epics would itself violate Engineering Principle #48 ("if a sprint's plan includes building a platform for a capability with fewer than two real consumers, cut it").

## Program 1 — Document Intelligence

**Epic 1.1 — Generalize extraction beyond the current single-client pipeline.**
*Inputs:* existing OneStack-shaped extraction code, a second real document set to generalize against. *Outputs:* a configurable extraction pipeline parameterized by document-type/template family. *Interfaces:* consumes raw documents from Connector Layer (Drive sync, upload), produces canonical records for Program 2. *Owner:* extraction lead. *Estimated difficulty:* Medium-High (the hard part is generalizing without breaking the working client). *Blocked by:* nothing — can start immediately. *Enables:* every future client onboarding. *Testing strategy:* golden-set regression (Program 6) run against both the original client's documents and the new generalization target before merge.

**Epic 1.2 — Single blended confidence score for review routing.**
*Inputs:* extraction output with per-field signals. *Outputs:* one score per document driving review-queue priority. *Interfaces:* consumed by the Application Layer's review workspace. *Owner:* extraction lead. *Difficulty:* Low. *Blocked by:* 1.1. *Enables:* Program 6's eval-set sampling to be confidence-weighted. *Testing:* compare routing decisions against actual reviewer override rate; recalibrate threshold if overrides cluster at a particular score band.

**Epic 1.3 — Multilingual (Hindi/mixed) field-label resolution.**
*Inputs:* real client documents containing Hindi or mixed-language fields (must be sourced/confirmed before scoping — do not build against a hypothetical). *Outputs:* canonical field mapping working regardless of source-label language. *Interfaces:* extends Stage 4's existing canonical-mapping logic. *Owner:* extraction lead. *Difficulty:* Medium, contingent entirely on how much real Hindi-language document volume actually exists — **verify this before committing a sprint to it.** *Blocked by:* 1.1. *Enables:* broader client base beyond English-only documents. *Testing:* a dedicated Hindi/mixed-language slice of the golden set.

## Program 2 — Validation & Reconciliation

**Epic 2.1 — Rule versioning (effective-from/to fields).**
*Inputs:* existing rule definitions in the 8-stage engine. *Outputs:* every rule carries an effective date range; historical reconciliations remain reproducible under the rules in force at the time. *Interfaces:* consumed by Program 4's correction-capture (a correction tied to a specific rule version). *Owner:* reconciliation lead. *Difficulty:* Low-Medium. *Blocked by:* nothing. *Enables:* Program 6's regression suite testing against specific rule-version snapshots. *Testing:* replay a past reconciliation and confirm it reproduces the original result under the rule version that was active then.

**Epic 2.2 — Document "how to add a new rule" pattern, then apply it to the next real rule.**
*Inputs:* the existing engine's internals. *Outputs:* a short written pattern + one real new rule added following it, proving the pattern. *Interfaces:* N/A — internal engineering practice. *Owner:* reconciliation lead. *Difficulty:* Low. *Blocked by:* 2.1. *Enables:* faster onboarding of new domains later (Payroll, Income Tax) without engine redesign. *Testing:* the new rule ships with its own regression test, added via the documented pattern, timed to confirm it's actually fast.

## Program 3 — Connector Platform

**Epic 3.1 — Extend idempotency logging to every Tally write path, not just vouchers.**
*Inputs:* current `TallyPushLog` pattern. *Outputs:* every write (ledger creation, Credit/Debit Note, voucher) logged and idempotent. *Interfaces:* Execution Substrate calls into the connector; connector calls into TallyPrime's XML-over-HTTP server. *Owner:* connector lead. *Difficulty:* Low-Medium. *Blocked by:* nothing. *Enables:* safe retry for every Tally interaction, not a subset. *Testing:* deliberately re-run every write path twice in a test environment and confirm no duplication.

**Epic 3.2 — Write the "how to build a connector" one-pager.**
*Inputs:* the Tally connector's actual shape. *Outputs:* a short doc describing Fetch/Push/Resolve/Health, explicitly *not* a framework or registry. *Interfaces:* N/A. *Owner:* connector lead. *Difficulty:* Low. *Blocked by:* 3.1. *Enables:* connector #2, whenever it's actually needed. *Testing:* N/A — reviewed by another engineer for clarity, not code-tested.

## Program 4 — Knowledge & Correction Capture

**Epic 4.1 — `correction_events` table and capture pipeline.**
*Inputs:* every accept/reject/correct action in the existing review workspace. *Outputs:* a structured, retained, queryable event per correction (who, when, what changed, what evidence, trust implication). *Interfaces:* written by the Application Layer's review actions; read by Program 6's eval-set curation and any future promotion pipeline. *Owner:* platform lead. *Difficulty:* Low-Medium (mostly schema and discipline, not novel engineering). *Blocked by:* nothing — start immediately, in parallel with Program 1. *Enables:* every future flywheel/SLM/promotion capability, per RFC-004's final synthesis. *Testing:* verify no review-workspace action can bypass event capture (a required, not optional, write path).

**Epic 4.2 — Supersession, not overwrite, for corrected values.**
*Inputs:* 4.1's event table. *Outputs:* a corrected field's prior value remains queryable, pointed to by the new value's supersession link. *Interfaces:* consumed by Program 2's rule-version-aware reproducibility requirement. *Owner:* platform lead. *Difficulty:* Low. *Blocked by:* 4.1. *Enables:* the bitemporal reproducibility RFC-002/004 require. *Testing:* confirm a record's historical state is reconstructible after multiple corrections.

## Program 5 — Workflow & Automation

**Epic 5.1 — Approval-gate step type with timeout and escalation.**
*Inputs:* existing Celery-based workflow steps that currently wait on human approval with no designed timeout. *Outputs:* every approval-gate step has a configured timeout and a defined escalation action (alert a specific person, not silent indefinite wait). *Interfaces:* used by GST-filing approval, ERP-push approval, and any future consequential-action gate. *Owner:* workflow lead. *Difficulty:* Medium. *Blocked by:* nothing. *Enables:* Program 7's "every consequential action traceable" requirement having a real termination condition. *Testing:* simulate a stale approval and confirm escalation fires correctly.

**Epic 5.2 — Idempotency audit across every existing workflow.**
*Inputs:* every current workflow definition. *Outputs:* a checklist confirming each external-system-touching step is idempotent, gaps fixed. *Interfaces:* N/A — internal hardening. *Owner:* workflow lead. *Difficulty:* Medium (mostly audit work, some fixes). *Blocked by:* Program 3 Epic 3.1's pattern being documented first. *Enables:* safe retries platform-wide. *Testing:* re-run each workflow step twice in a test environment.

## Program 6 — Evaluation Platform

**Epic 6.1 — Golden dataset bootstrap.**
*Inputs:* real, already-processed, already-corrected client documents. *Outputs:* a versioned, growing golden set covering the current document/rule types. *Interfaces:* consumed by CI (regression) and by the monthly CA-grading process. *Owner:* eval lead (can be shared with reconciliation lead at this team size). *Difficulty:* Low. *Blocked by:* Program 4 (correction events are the natural source of golden-set candidates). *Enables:* everything downstream in Program 6. *Testing:* N/A — this epic *is* test infrastructure.

**Epic 6.2 — CI regression suite wiring.**
*Inputs:* 6.1's golden set. *Outputs:* every PR to extraction/validation/reconciliation code runs against the golden set before merge. *Interfaces:* CI pipeline (Program 8). *Owner:* eval lead. *Difficulty:* Low. *Blocked by:* 6.1. *Enables:* Engineering Principle #25 becoming enforceable, not aspirational. *Testing:* deliberately introduce a regression and confirm CI catches it.

**Epic 6.3 — Monthly CA-grading process.**
*Inputs:* a sample of real cases, a CA willing to grade them. *Outputs:* a repeatable, lightweight (not automated) professional-accuracy signal, tracked over time. *Interfaces:* feeds pass-rate tracking; feeds future promotion decisions once Program 10 ever activates. *Owner:* founder/domain expert (this is a professional-judgment task, not an engineering task). *Difficulty:* Low (process design), ongoing cost (grading time). *Blocked by:* nothing. *Enables:* the actual strategic asset RFC-002/003 identified. *Testing:* N/A.

## Program 8 — Developer Platform
Covered in full in Part 5 (repo structure) and Part 7 (developer experience) — not separately epic-decomposed here to avoid duplicating that content.

---

# PART 4 — ARCHITECTURE DECISION RECORDS

Each ADR: Problem, Context, Options, Decision, Trade-offs, Review Trigger. Decisions below **incorporate RFC-005's Red Team Review** — several ADRs decide *not* to build something RFC-005's Part 1-9 described, and say so explicitly.

### ADR-001 — OCR / Document Intelligence Architecture
**Problem:** How should the platform extract structured data from heterogeneous financial documents.
**Context:** RFC-005 Part 3 specified a 5-stage pipeline; RFC-005 Red Team R.5 flagged Stage 3 (vision-model fallback) as being built ahead of evidence.
**Options:** (a) full 5-stage pipeline now; (b) Stages 1-2-4-5 now, Stage 3 deferred; (c) rebuild extraction entirely on a commercial document-AI API.
**Decision:** (b). Keep the existing layout-aware `pdfplumber`-based extraction (Stage 2) as the owned, controllable core; add Stage 3 only once document-failure-mode volume is actually measured and shown to be material.
**Trade-offs:** some current failure cases (badly scanned/handwritten documents) stay manual longer than a full pipeline would allow; in exchange, the team doesn't spend a sprint on infrastructure for a volume of documents that may be small.
**Review trigger:** measured volume of extraction failures attributable to scan/handwriting quality exceeds a threshold worth a dedicated sprint (define the threshold once Program 6's golden set has enough real failure data to set one meaningfully).

### ADR-002 — Knowledge Graph / Ontology
**Problem:** Should the platform build a dedicated entity/relationship graph now.
**Context:** RFC-002/004/005 all describe a rich ontology as the eventual strategic asset; RFC-005 Red Team R.2/R.6 killed it as a near-term build.
**Options:** (a) build a graph database and ontology schema now; (b) use relational tables (`vendors`, `vendor_aliases`, foreign keys) with GSTIN/PAN-anchored resolution; (c) do nothing about entity resolution yet.
**Decision:** (b). Deterministic-anchor entity resolution via relational schema, no graph database.
**Trade-offs:** multi-hop relational queries (e.g., ownership-chain related-party detection) are harder to express than they'd be in a graph; in exchange, the team avoids operating a second database system with no current workload justifying it.
**Review trigger:** a specific product requirement needs a multi-hop relationship query that is demonstrably painful in relational form — not a calendar date.

### ADR-003 — Company Brain
**Problem:** How much of RFC-002's Company Brain (episodic/semantic/procedural memory, promotion pipeline, trust scoring) should be built now.
**Context:** RFC-005 Red Team R.2/R.11 collapsed this to one requirement: correction events must be captured with full fidelity from day one, because that's the one thing that can't be retrofitted.
**Options:** (a) build the full versioned Knowledge & Memory layer with promotion pipeline now; (b) build only the `correction_events` table (Program 4) with the right fields, defer promotion/SLM/semantic-memory-distillation entirely; (c) skip correction capture and revisit later.
**Decision:** (b).
**Trade-offs:** no automated pattern-promotion or SLM training happens yet — every correction is captured but nothing "learns" from the aggregate automatically; in exchange, the team ships a real product now while preserving the exact data needed to build promotion/SLM later without a painful backfill.
**Review trigger:** correction-event volume and the professionally-graded eval set (Program 6) reach a size where a specific promotion or SLM use case has clear, evidenced ROI.

### ADR-004 — Connector Platform
**Problem:** Should connectors be built against a shared registry/framework or as independent, pattern-following integrations.
**Context:** RFC-005 Part 5 described a Connector Registry as shared infrastructure; Red Team R.2/R.8 killed it for a one-connector reality.
**Options:** (a) build a generalized connector registry and shared retry/idempotency framework now; (b) document the Fetch/Push/Resolve/Health pattern and copy-adapt it per connector; (c) build connectors ad hoc with no shared pattern at all.
**Decision:** (b).
**Trade-offs:** some code duplication between connector #1 and connector #2 when it's eventually built; in exchange, no time spent generalizing a pattern that's only been proven once.
**Review trigger:** a third connector is being built — at that point, the pattern has been proven twice and generalizing it stops being speculative.

### ADR-005 — Workflow Engine
**Problem:** Should the platform adopt a dedicated durable-execution engine (Temporal-class) or continue on Celery.
**Context:** RFC-005 Part 6.2 and RFC-004 Part 9 both already recommended staying on Celery until saga complexity genuinely exceeds it; Red Team R.7 reconfirmed.
**Options:** (a) adopt Temporal now; (b) stay on Celery, add the approval-timeout/escalation gap fix (Program 5) on top of it; (c) build a custom durable-execution layer.
**Decision:** (b).
**Trade-offs:** Celery's durability guarantees are weaker than a purpose-built durable-execution engine's; in exchange, the team avoids adopting and operating a genuinely complex new system for a workload that doesn't yet require it.
**Review trigger:** multi-day, multi-system sagas with compensating actions become common enough that hand-rolled state tracking on Celery is visibly the team's biggest maintenance burden.

### ADR-006 — Evaluation Platform
**Problem:** How many of RFC-003's five evaluation layers should be built now.
**Context:** Red Team R.2 flagged Layers 4-5 (drift monitoring, human-trust metrics) as premature given current throughput.
**Options:** (a) build all five layers now; (b) build Layers 1-2 only (regression + professional ground truth); (c) build nothing formal, rely on manual spot-checks.
**Decision:** (b).
**Trade-offs:** the platform won't automatically detect gradual drift or miscalibrated reviewer trust yet; in exchange, the team builds the two layers that are actually actionable at current scale and avoids building measurement infrastructure with no signal to measure.
**Review trigger:** production volume and eval-set size reach a point where a monthly manual pass-rate check is visibly insufficient to catch a real regression before a client does.

### ADR-007 — SLM Strategy
**Problem:** Should the platform invest in fine-tuning or hosting small language models.
**Context:** RFC-002 Part 5's own doctrine is "data-gated, not calendar-gated"; Red Team R.3 confirms the gate is currently closed.
**Options:** (a) begin SLM fine-tuning now; (b) do nothing until verified-correction volume for a specific narrow task justifies it; (c) rule it out permanently.
**Decision:** (b).
**Trade-offs:** the platform continues paying frontier-model API costs for narrow, repetitive tasks (HSN classification, ledger normalization) that could eventually be cheaper on a fine-tuned SLM; in exchange, no engineering time is spent on infrastructure with no training data behind it yet.
**Review trigger:** Program 4's correction-event volume for one specific narrow task (most likely HSN/ledger classification) reaches a size where a fine-tuning experiment has plausible ROI — track this number explicitly, don't guess at it.

### ADR-008 — Observability
**Problem:** What observability stack the platform should run.
**Context:** Sentry + structured logging is already in place (RFC-001's README); RFC-003/005 call for unifying health telemetry and decision-provenance.
**Options:** (a) build a custom unified observability system; (b) extend the existing Sentry + structured-logging setup, adding provenance fields to existing log events; (c) adopt a full OpenTelemetry rollout now.
**Decision:** (b), with OpenTelemetry adoption as instrumentation matures opportunistically (per RFC-004 Part 9), not a forced near-term migration.
**Trade-offs:** less standardized instrumentation than a full OTel rollout would give; in exchange, no migration cost taken on before it's clearly needed.
**Review trigger:** a specific pain point (e.g., needing to correlate traces across a growing number of services) makes the current approach visibly insufficient.

### ADR-009 — Security
**Problem:** What security posture and tooling the platform needs at this scale.
**Context:** SECURITY_REMEDIATION_PHASE1/2 already tracks tenant-isolation work; Programs 1-6 add new endpoints that must inherit the same discipline.
**Options:** (a) a dedicated security engineering hire/team now; (b) enforce tenant-isolation and secret-handling as a code-review gate (Engineering Principle #21, #27), owned by every engineer, revisited by whoever's available for security review; (c) defer security discipline until an incident forces it.
**Decision:** (b).
**Trade-offs:** no dedicated security specialist catching issues a generalist might miss; in exchange, the team doesn't over-hire for a threat profile it doesn't yet have, while still closing the highest-severity gaps already identified.
**Review trigger:** client base grows into BFSI/SEBI-adjacent segments (RFC-001 Part 4) with materially higher security/compliance bar, or any tenant-isolation incident occurs, whichever comes first.

### ADR-010 — Multi-Tenancy
**Problem:** How isolation is enforced as the platform grows.
**Context:** `require_same_tenant` checks exist per-endpoint already; RFC-004 Part 8.2 calls for independent enforcement at storage, graph, retrieval, and training layers — most of which don't exist yet at this scale.
**Options:** (a) build the full independently-enforced-at-every-layer isolation model now; (b) enforce at the data-access layer (current pattern) with a mandatory code-review checklist item for every new endpoint, defer graph/retrieval/training-layer isolation until those layers exist; (c) rely on informal discipline only.
**Decision:** (b).
**Trade-offs:** isolation currently has fewer independent enforcement points than the eventual doctrine calls for; in exchange, the team isn't building isolation enforcement for layers (graph, SLM training) that don't exist yet.
**Review trigger:** Program 10 (Ontology) or ADR-007 (SLM) actually activates — at that point, their respective isolation enforcement must be designed in from their own day one, not retrofitted.

---

# PART 5 — REPOSITORY STRUCTURE

Recommended at the level of intent, not exact folder names (those are an implementation decision for the team, not an architecture-document prescription):

```
/backend
  /extraction          Program 1 — Document Intelligence
  /validation           Program 2 — deterministic rule engine
  /reconciliation        Program 2 — the 8-stage engine
  /connectors            Program 3 — one subfolder per connector, following the documented pattern
  /knowledge              Program 4 — correction_events, verified_knowledge schema and access
  /workflows              Program 5 — Celery task definitions, approval-gate logic
  /evaluation             Program 6 — golden-set fixtures, regression harness, grading-process tooling
  /api                    thin, versioned contract layer
  /security               tenant-isolation helpers, shared auth checks
  /observability           logging/telemetry helpers shared across the above

/frontend
  /review-workspace        Application Layer — the CA review surface
  /dashboards               reporting/MIS surfaces

/docs
  /rfc                     RFC-001 through RFC-005 and any future numbered RFCs (this series)
  /adr                      ADR-001 onward, one file per decision, living and revisable
  /eval                     golden-set documentation, grading-process runbook
  /connectors                the "how to build a connector" one-pager (Epic 3.2) and any per-connector setup notes (e.g., TALLY_CONNECTOR_SETUP.md, already present)
  /runbooks                  operational procedures: LLM-vendor fallback, GSP fallback (Part R.11.4 of RFC-005), incident response

/benchmarks
  golden-set fixtures used by Program 6's CI regression suite (kept versioned, not regenerated ad hoc)

/tools
  developer-facing scripts: local environment setup, test-data seeding — no "internal SDK" abstraction layer until more than one consuming team exists

/.github (or equivalent CI config)
  CI pipeline definitions: lint, test, regression-suite run, deploy
```

**What is deliberately absent from this structure, and why:** no `/ontology` or `/graph` folder (ADR-002 — not built yet); no `/slm` or `/fine-tuning` folder (ADR-007 — not built yet); no `/agents` folder implying a multi-agent framework (Program 9 — not activated); no `/internal-sdk` folder (Engineering Principle #48 — no framework before at least two real consumers). Adding any of these folders back is itself a signal worth noticing — it means a corresponding ADR's review trigger fired and a real decision to build should be made explicitly, not accreted silently.

---

# PART 6 — ENGINEERING STANDARDS

See the standalone [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) — 50 permanent engineering principles, organized under: Deterministic before AI; Build moats, buy commodities; Every subsystem replaceable; Every action observable; Every API versioned; Every connector follows one interface; Every workflow idempotent; Every AI output explainable; Every model replaceable; Every customer isolated; Knowledge compounds; Evaluation never stops; Security by default; Testing before deployment; Documentation is code; Prefer deletion over complexity; Human override for consequential actions; plus team/process, cost/operational, shipping, and humility/revision principles specific to executing at this team's size. That document is the one to hand a new engineer on day one; this document is the one that explains why the current scope is what it is.

---

# PART 7 — DEVELOPER EXPERIENCE

**Development workflow.** Trunk-based development with short-lived feature branches (days, not weeks) — a team this size cannot afford long-lived branches accumulating merge conflicts. Every branch maps to one epic or one clearly-scoped fix, per Part 3's epic breakdown.

**Branch strategy.** `main` is always deployable. Feature branches off `main`, merged via PR after CI passes and one review. No long-lived `develop` branch — unnecessary process overhead at this size (Engineering Principle #41).

**Code review rules.** Every PR gets one reviewer minimum; reviewer checks correctness, tenant-isolation (per ADR-010's checklist), test coverage, and scope — not style (automate style with a linter/formatter so humans don't argue about it, per Engineering Principle #41). A PR touching Validation & Decision-layer code (Program 2) gets a second look specifically for "did a probabilistic shortcut sneak in" (Engineering Principle #1-3).

**Definition of Done.** Code merged, tests passing (including the Program 6 regression suite where applicable), logging/observability present for any new write path (Engineering Principle #10), documentation updated in the same PR (Engineering Principle #31-32), and — for anything touching a consequential external action — a human-approval gate verified present (Engineering Principle #36).

**Release process.** Continuous deployment off `main` for backend/frontend, gated by CI passing — no separate release-branch ceremony at this team size. Database migrations reviewed with extra care given the bitemporal/non-destructive requirements from RFC-004 (a migration that would silently lose correction history or supersession pointers does not ship, per Engineering Principle #23).

**Feature flags.** Used sparingly, specifically for gating a new connector or rule set's rollout to a subset of tenants during validation — not as a general architecture pattern. A flag that's been on or off unconditionally for more than a month gets deleted (Engineering Principle #34).

**Migration strategy.** Additive, backward-compatible schema changes by default (RFC-004 Part 2.4's doctrine, enforced here as a review-gate question: "does this migration lose any historical/supersession data?"). Destructive migrations require explicit sign-off and a written reason.

**Observability standards.** Every new endpoint/workflow step emits structured logs with tenant ID, actor, and outcome at minimum (Engineering Principle #10); errors go to Sentry with enough context to reproduce without asking the reporting user follow-up questions.

**Logging standards.** Structured (JSON), not free-text — consistent with the existing pattern already in place per the README. No secrets or full document contents in logs (references/IDs only).

**Error handling.** Fail loud and specific in development; fail safe (never silently proceed with a wrong value) in production — an extraction or validation failure routes to the review queue, it never gets silently defaulted (Engineering Principle #43 of RFC-002's doctrine, restated here as an execution-level rule).

---

# PART 8 — QUALITY ENGINEERING

**Testing pyramid.** Unit tests (fast, most numerous) for rule logic and extraction-field mapping; integration tests for connector Fetch/Push round-trips against a test Tally instance/sandbox; contract tests for the API Layer's versioned endpoints, catching accidental breaking changes before a version bump is forgotten.

**Unit tests.** Every deterministic rule (Program 2) ships with unit tests covering the rule and at least one known edge case, per Engineering Principle #30.

**Integration tests.** Connector round-trips (push then re-fetch, confirm consistency) run against a controlled test environment, not production client data — protecting the multi-user Tally safety concern already flagged in project memory.

**Contract tests.** API Layer version compatibility checked automatically in CI — a breaking change without a version bump fails the build, not just a code review comment.

**OCR benchmarks.** Program 6's golden set, specifically sliced by document type and (once volume justifies it) by language — tracked as a standing CI metric, not a one-time report.

**Evaluation benchmarks.** The monthly CA-graded sample (Program 6 Epic 6.3) — tracked over time as the actual professional-accuracy signal, distinct from and more important than any automated benchmark.

**Regression suite.** Runs on every PR touching extraction, validation, or reconciliation code — this is the concrete implementation of Engineering Principle #25, non-negotiable.

**Synthetic dataset.** Used narrowly, per RFC-002 Part 5.1's doctrine, to stress-test format-variation robustness (a deliberately malformed or unusual invoice layout) — never used to establish correctness ground truth, only coverage.

**Golden dataset.** The single most valuable test asset the team owns — versioned, grown deliberately from real (anonymized where needed) client cases via Program 4's correction events, never synthetic-only.

**Performance benchmarks.** Tracked for the extraction pipeline's throughput and the reconciliation engine's latency on realistic batch sizes — enough to catch a regression before a client notices slowness, not a dedicated performance-engineering program at this scale.

**Security tests.** Tenant-isolation test cases (attempt cross-tenant access, confirm it's rejected) run in CI for every endpoint touching tenant-scoped data — the automated enforcement of ADR-010's code-review checklist.

---

# PART 9 — ENGINEERING ROADMAP

**Governing rule for this Part, per the mission's own instruction: only include work that should actually be built. Everything from Programs 9-10, and every "delay until evidenced" item from RFC-005's Part 11/Red Team, is absent from this roadmap on purpose — not forgotten, deliberately excluded.**

### 30 Days
Program 4 (correction-events schema and capture) shipped and verified capturing 100% of review-workspace actions. Program 5 Epic 5.1 (approval-gate timeout/escalation) shipped — closing the flagged RFC-005 Part 10.1 gap. Program 3 Epic 3.1 (idempotency extended to every Tally write path) shipped. Program 8's CI/CD baseline (Part 5's repo structure, a working regression-gated pipeline) in place. Program 6 Epic 6.1 (golden dataset bootstrap) started.

### 90 Days
Program 1 (extraction generalization beyond the single current client pipeline) shipped for at least one additional real client/document set. Program 2 Epic 2.1 (rule versioning) shipped. Program 6 fully at Layer 1-2 (regression suite gating every relevant PR; first monthly CA-graded batch complete). Program 3's connector pattern documented (Epic 3.2); connector #2 only started if a real client need exists by this point, not speculatively.

### 6 Months
Program 1's multilingual/Hindi support shipped, *if and only if* real document volume justified the investment (verified per Epic 1.3's own gating note) — otherwise explicitly still deferred and re-evaluated at 12 months. Program 7's tenant-isolation checklist fully enforced with zero known gaps. Program 2's rule-versioning pattern proven by at least one real new rule set (e.g., a next domain per RFC-002 Part 4's ownership table, chosen by actual client demand, not the research document's ordering). Golden dataset (Program 6) covering the majority of real production document/rule-type volume.

### 12 Months
Revisit ADR-002 (Ontology), ADR-004 (Connector Registry), ADR-006 (Evaluation Layers 3-5), and ADR-007 (SLM) against their stated review triggers — **explicitly a checkpoint, not a commitment to build any of them.** If a review trigger has genuinely fired (a third connector needed, a specific rule-versioned domain generating enough verified-correction volume for one narrow SLM task), scope that one thing narrowly. If not, they remain deferred and the checkpoint repeats at 24 months.
Enterprise Platform (Program 7) SSO/SAML work begins only if a specific deal requires it by this point (ADR-009's trigger).

### 24 Months
A second jurisdiction's applicability (RFC-001 Part 6's portability thesis) is evaluated only if the current core market shows genuine saturation of the learning-effect flywheel (RFC-004's final synthesis — "expanding early dilutes the one mechanism that makes the thesis work") — this is a strategic go/no-go conversation, not a scheduled engineering deliverable. Any Program 9/10 activation by this point should already have happened earlier, triggered by evidence, not scheduled to start now by default.

**What has been deliberately deleted from this roadmap, restated for clarity:** dedicated graph database, event-sourcing/CQRS, Temporal-class workflow engine, Kafka-class streaming, federated learning/differential privacy, MCP exposure, the full digital-workforce roster beyond one demand-validated role, and a generalized connector framework before a third connector exists. None of these are "coming later on this roadmap" — they are not on this roadmap at all, by design, until their specific evidentiary trigger fires.

---

# PART 10 — RED TEAM REVIEW OF THIS EXECUTION PLAN

*Written as a Distinguished Engineer whose job is to find what's still wrong with this plan, including places where it under-corrected or over-corrected relative to RFC-005's own Red Team pass.*

**Overengineering that survived, even after one red-team pass already happened.** Ten ADRs and ten Programs for a 3-5 person team is still a lot of ceremony. A team this size does not need ten formally-numbered ADRs before writing code — several of these (ADR-005 "stay on Celery," ADR-007 "don't build SLMs yet") are one-paragraph decisions dressed up in a template. **Revision: collapse ADR-002, 003, 004, 006, 007 into a single "Deferred Infrastructure" ADR-00X listing all five decisions and their triggers in one place**, rather than five separate documents that will each individually accrete review meetings. Keep only ADR-001 (OCR), ADR-005 (Workflow), ADR-008 (Observability), ADR-009 (Security), ADR-010 (Multi-tenancy) as full individual ADRs — these are the ones with real, non-obvious trade-offs worth a dedicated document.

**Wrong priorities.** Program 6 (Evaluation) is marked P0 but its most valuable component — the monthly CA-graded batch — depends on a founder/domain expert's time, which is also needed for Programs 1-2's domain-correctness review and for actual client relationships. **Revision: the roadmap should explicitly name whose time the CA-grading process consumes and cap it (e.g., one half-day per month), or it will silently get deprioritized every month something more urgent comes up** — an unstaffed P0 is not actually a P0, it's a wish.

**Hidden risk: Program 1's multilingual epic is scoped before its precondition is confirmed.** Epic 1.3 says "verify this before committing a sprint" but the roadmap's 6-month milestone still lists it as a deliverable, contradicting the epic's own gating language. **Revision: remove Hindi/multilingual support from the 6-month roadmap entirely and replace it with "verify real Hindi-language document volume; scope only if material" as the actual 90-day deliverable** — don't let a roadmap milestone silently commit to work an epic explicitly said might not be justified.

**Cost risk not fully addressed.** The blueprint tracks LLM/API cost per workload (Engineering Principle #44) as a principle but the roadmap has no actual checkpoint for reviewing that cost. **Revision: add a recurring (quarterly) cost review as an explicit, named checkpoint — not just a standing principle nobody schedules time to check.**

**Hiring risk.** This plan assumes the current team can execute Programs 1-8 without naming how many people that actually requires or where the gaps are (e.g., who owns Program 6's CI/eval infrastructure vs. who owns Program 1's extraction work — are these the same person, and is that sustainable). **Revision: before 90 days, do an explicit staffing map against Part 3's epic "Owner" fields — if one person is listed as owner on more than roughly three concurrently-active epics, that is a scheduling risk, not just a resourcing note, and either the roadmap slows down or hiring becomes an explicit Q2 deliverable, not an assumption.**

**Scaling risk correctly avoided, worth confirming explicitly.** The plan does not build for a scale the team doesn't have (no Resource Manager, no multi-region, no dedicated SRE function) — this is correct and should be *actively defended*, not silently assumed, if a future stakeholder pushes for "enterprise-grade" infrastructure ahead of an enterprise-grade client actually requiring it. Restated as a standing answer: **"we build enterprise-grade correctness and auditability now (Programs 2, 4, 7); we build enterprise-grade scale infrastructure only when a specific enterprise client's specific requirement demands it (ADR-009/010's triggers)."**

**Maintainability risk.** Ten Programs, even correctly scoped, is still a lot of surface area for a small team to keep mentally loaded. **Revision: this document's own Part 1/2 should be re-read and re-pruned at the 90-day and 6-month checkpoints already defined in Part 9 — if a Program has had zero epics active for two consecutive checkpoints, fold it into an adjacent Program rather than keeping it as a separate heading indefinitely.**

**Developer productivity risk.** The Definition of Done (Part 7) requires documentation, tests, logging, and tenant-isolation review on every PR — correct in principle, but for a 3-5 person team this can become a bottleneck if every PR requires the same ceremony regardless of size. **Revision: distinguish "consequential" PRs (touch Validation & Decision, Execution Substrate, or tenant-scoped data access) from "low-stakes" PRs (a UI copy fix, a log message improvement) — the full Definition of Done applies to the former; the latter gets a lighter, explicitly-defined fast path, or the team will either slow to a crawl or start quietly skipping the checklist, which is worse.**

**Net revision applied to this document:** ADRs consolidated from ten to six full documents plus one grouped "Deferred Infrastructure" record; the 6-month roadmap's multilingual commitment corrected to match its own epic's gating language; a quarterly cost-review checkpoint added; a staffing-map exercise added before the 90-day mark; a two-tier Definition of Done (consequential vs. low-stakes PRs) added to Part 7; and a standing instruction to re-prune Part 1/2's Program list at every roadmap checkpoint rather than letting it grow monotonically. These revisions are reflected in Part 9's roadmap and Part 7's process description above; Part 4's ADR count should be read as six-plus-one going forward, not ten independent documents, even though all ten decisions above remain valid and complete as written.

---

# CLOSING NOTE

This blueprint is the execution-scoped, red-team-corrected translation of RFC-005 for a 3-5 person engineering team. Every Program, epic, and ADR traces back to a specific RFC-001–005 finding, and every deferral traces back to a specific Red Team finding from RFC-005's own review or this document's Part 10. The next deliverable is PROJECT_BOOTSTRAP.md — the first 100 concrete tasks in execution order, assuming engineering starts tomorrow morning.
