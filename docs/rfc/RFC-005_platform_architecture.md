# RFC-005 — AUDITOS PLATFORM ARCHITECTURE
## Designing the Financial Intelligence Platform

**Prepared by: Principal Architect perspective**
**Status: Architecture. No code. No technology-stack prescriptions except where they materially constrain design.**
**Doctrine (accepted, not repeated, not re-litigated except where noted): RFC-001 World Intelligence, RFC-002 Company Brain, RFC-003 Financial Intelligence Operating System, RFC-004 Data Intelligence Platform.**

> The four prior RFCs answered *why* and *what*. This RFC answers *how the system is organized* — the layers, their boundaries, their interfaces, their failure modes, and how the platform evolves from a two-person team's working product to a decade-durable financial intelligence platform without a rewrite. Every layer below is a direct, traceable implementation of specific doctrine from RFC-001–004; where a layer's shape doesn't map cleanly to one of those RFCs, that mapping is called out explicitly.

---

# PART 0 — ONE CONTRADICTION FLAGGED BEFORE PROCEEDING

Per this RFC's mandate to challenge prior doctrine only where a critical contradiction exists: RFC-003 Part 1 defines Knowledge and Memory as separate OS components; RFC-002 defines Memory as encompassing episodic/semantic/procedural layers, one of which (semantic memory, once verified) is functionally indistinguishable in storage/versioning behavior from RFC-003's "Knowledge." This is not a contradiction in substance — both RFCs agree on the underlying doctrine (versioned, trust-scored, human-verified-before-shared) — but it is an unresolved naming and layering ambiguity that this architecture must resolve once, structurally, so implementation teams don't inherit the ambiguity. **Resolution adopted for this architecture:** "Knowledge" and "Memory" are unified into one platform layer — the **Knowledge & Memory Layer** — internally partitioned by RFC-002's three memory types (episodic, semantic, procedural) plus RFC-002/003's authority-sourced Knowledge, all sharing one versioning/trust/provenance substrate (Part 2.7 below), because they share every governance property that matters architecturally (versioning, supersession, trust scoring, tenant isolation) and splitting them into two platform layers would only duplicate that substrate. This is a naming/layering simplification, not a doctrinal reversal — every rule RFC-002 and RFC-003 established about each memory/knowledge type individually still applies unchanged within its partition.

---

# PART 1 — THE COMPLETE PLATFORM, TOP TO BOTTOM

## 1.1 Why layers at all, and the ordering principle
The layer ordering below is not arbitrary — it follows a single rule, derived directly from RFC-003 Part 1.3's finding that **Execution is the only layer permitted to cause real-world side effects**: every layer above Execution in the data-flow sense (closer to raw input) is progressively more replaceable and more probabilistic; every layer at or below Execution is progressively more durable and more deterministic. This gives the platform a structural property worth stating up front: **you can tell how replaceable a layer is by how close it sits to raw external input, and how durable/deterministic it must be by how close it sits to a real-world consequence.** This single rule is what should guide every future "which layer does this new capability belong in" decision, more than any specific layer's name.

## 1.2 The layer stack

```
User
  │
Identity & Access Layer          (who is asking, on whose behalf, with what authority)
  │
Application Layer                (the surfaces humans and external systems touch)
  │
API Layer                        (the platform's own stable contract)
  │
Automation & Workflow Layer      (durable multi-step orchestration, human gates)
  │
Reasoning Layer                  (agents, planning, model-based judgment — stateless)
  │
Knowledge & Memory Layer         (Company Brain: episodic/semantic/procedural/knowledge)
  │
Ontology Layer                   (entities, relationships, events — the financial graph)
  │
Validation & Decision Layer      (deterministic rules, veto power, always)
  │
Document Intelligence Layer      (OCR, extraction, canonical mapping)
  │
Connector Layer                  (every external system: ERP, government, comms, storage)
  │
Evaluation Layer                 (cross-cutting: measures every layer above, continuously)
  │
Observability & Security Layer   (cross-cutting: every layer, always)
  │
Execution Substrate              (the only layer permitted a real-world side effect)
```

Two layers are drawn as **cross-cutting** rather than positioned in the vertical flow (Evaluation, Observability & Security) because, per RFC-003 Part 1's OS-component doctrine, they attach to every other layer rather than sitting between two of them in the data-flow sense — placing them at a single point in the stack would misrepresent their actual reach.

## 1.3 What responsibility belongs where, and what must never leak across a boundary

**Identity & Access Layer.** *Belongs:* authentication, tenant resolution, session management, the mapping from "this human/API caller" to "this tenant, this role, this authority scope." *Never belongs here:* any business logic about what a role is *permitted to decide* — that's Policy, which lives inside the Automation & Workflow layer's governance surface (RFC-003 Part 1.2 distinguishes identity from policy explicitly; this architecture preserves that split as two layers' worth of responsibility, not one).

**Application Layer.** *Belongs:* the CA review workspace, dashboards, the digital-workforce chat/briefing surfaces (RFC-003 Part 8), any UI. *Never belongs here:* extraction logic, reconciliation logic, or any deterministic rule — the Application Layer renders and collects, it does not decide. A common architectural failure this boundary specifically prevents: business logic creeping into frontend code because it's convenient for a specific screen, which makes that logic invisible to Evaluation and Observability and untestable independent of the UI.

**API Layer.** *Belongs:* the platform's own stable, versioned external contract — what a client's own systems, or a future partner integration, or an MCP-exposed surface (RFC-001 Part 2) actually calls. *Never belongs here:* orchestration or state — the API layer is a thin, versioned facade over the Automation & Workflow and Reasoning layers, never a place where multi-step logic accumulates (that accumulation, if allowed, silently recreates an unaudited workflow engine outside the one the platform already has).

**Automation & Workflow Layer.** *Belongs:* durable state machines (RFC-003 Part 3), the Scheduler, Planner, Policy Engine, Governance Layer, human-approval gates, exception queues, approval chains — everything RFC-003 Part 1 and Part 6 specified. *Never belongs here:* the actual judgment about whether a specific invoice's classification is correct (that's Reasoning/Validation) — this layer sequences and gates, it does not reason about content.

**Reasoning Layer.** *Belongs:* the Planner's task decomposition, the specialized agents (RFC-003 Part 2, Part 8), frontier-model and SLM inference, the Context Manager. Stateless by RFC-003 Part 1's doctrine — every agent invocation reads from Knowledge & Memory and writes proposals back to it, holding nothing durable itself. *Never belongs here:* direct writes to any external system (that crosses into Execution Substrate, always through a gate) and never belongs here: storage of "what this agent has learned" outside the shared Knowledge & Memory layer (RFC-003 Part 2.3's "no agent owns memory privately" doctrine, enforced structurally by this layer having no private persistent store of its own).

**Knowledge & Memory Layer.** *Belongs:* everything RFC-002 specified — episodic, semantic, procedural memory; authority-sourced global/domain knowledge; all versioned, trust-scored, provenance-carrying. *Never belongs here:* unverified proposals presented as fact (RFC-002 Part 1's doctrine — proposals live in a structurally distinct, clearly-tagged staging partition within this layer, never comingled with verified content in a way a query could accidentally retrieve as trusted).

**Ontology Layer.** *Belongs:* resolved entities (golden records), typed relationships, the event graph (RFC-002 Part 2, RFC-004 Part 3-4). *Never belongs here:* the raw evidentiary documents themselves (those live in Document Intelligence's output store, referenced by pointer from ontology events, never duplicated into the graph) and never belongs here: business-metric definitions (those are the semantic layer, positioned inside Knowledge & Memory's derived/semantic partition per RFC-004 Part 6.2, not the ontology's structural graph).

**Validation & Decision Layer.** *Belongs:* every deterministic rule with veto power — tax math, debit/credit balancing, statutory apportionment (RFC-002/003's permanent doctrine). *Never belongs here:* anything requiring judgment or interpretation — the instant a "rule" needs an LLM to evaluate it, it has left this layer and become a Reasoning-layer task, and this layer's implementers must resist the temptation to let probabilistic shortcuts creep into what must remain provably deterministic code.

**Document Intelligence Layer.** *Belongs:* OCR, layout analysis, table extraction, semantic parsing, canonical mapping (Part 3 below covers this in full). *Never belongs here:* reconciliation logic (that requires cross-referencing the ontology and other documents, which is Validation & Decision / Ontology territory) — Document Intelligence's job ends at "this document, correctly structured, with confidence scores," never "this document, cross-checked against everything else we know."

**Connector Layer.** *Belongs:* every integration to an external system, behind one standard interface (Part 5 below). *Never belongs here:* any interpretation of the data it moves — a connector transports and maps to the canonical schema (RFC-004 Part 2); it never decides whether a value is correct, which is downstream Validation's job. A connector that starts embedding correctness logic has silently become an undocumented second Validation layer, which is a specific, real anti-pattern to guard against.

**Evaluation Layer (cross-cutting).** *Belongs:* the five-layer continuous evaluation from RFC-003 Part 4, attached to every layer above. *Never belongs here:* the promotion decision itself (measuring is not deciding — Evaluation reports, the Knowledge & Memory Layer's promotion-verification checkpoint decides, per RFC-002/RFC-003's explicit separation of measurement from action).

**Observability & Security Layer (cross-cutting).** *Belongs:* telemetry, provenance logging, tenant isolation enforcement, encryption, the Safety Layer's anomaly backstop (RFC-003 Part 1.2). *Never belongs here:* business-rule enforcement (that's Validation & Decision) — Security enforces *who can touch what*, Validation enforces *whether what they're touching is correct*, and conflating the two recreates RFC-003 Part 1.2's identity-vs-policy conflation risk at a different layer boundary.

**Execution Substrate.** *Belongs:* the narrow, heavily-logged surface that actually performs an ERP write, a filing submission, a message send — nothing else. *Never belongs here:* any decision-making of any kind — by the time something reaches Execution, every decision (should this happen, is it correct, is it approved) has already been made upstream; Execution's only job is to perform the action idempotently and log the outcome (RFC-003 Part 3.2).

---

# PART 2 — EVERY PLATFORM LAYER, IN DETAIL

For each layer: purpose, inputs, outputs, dependencies, failure modes, replacement strategy, future scalability. Layers are grouped where their operational profile is genuinely shared; each retains a distinct responsibility per Part 1.

## 2.1 Identity & Access Layer
**Purpose:** establish who is acting, on whose behalf, within which tenant boundary, at every request.
**Inputs:** credentials/session tokens, API keys, connector-originated service identities.
**Outputs:** a verified `(actor, tenant, role, authority-scope)` tuple attached to every downstream request.
**Dependencies:** none upstream (this is the platform's entry point); every other layer depends on it.
**Failure modes:** identity spoofing (mitigated by standard auth hardening, not a novel concern here); tenant-scope leakage at this layer is catastrophic because every downstream layer trusts what this layer asserts — this is why isolation is enforced independently at every layer (RFC-004 Part 8.2) rather than trusting this layer alone, defense in depth against exactly this single-point-of-failure risk.
**Replacement strategy:** standard, swappable auth infrastructure (Part 9's build/buy table) — this layer should be the *easiest* to replace in the entire stack, precisely because it holds no domain-specific logic.
**Future scalability:** SSO/SAML for enterprise clients, delegated authority for agent-acting-on-behalf-of-human flows (RFC-003 Part 2's bounded-authority doctrine requires this layer to express "agent X acting under human Y's delegated authority," not just human identity alone) — this requirement should be designed in now even though enterprise SSO demand may be a Phase 3 concern (Part 10).

## 2.2 Application Layer
**Purpose:** every human- and external-system-facing surface.
**Inputs:** rendered data from the API Layer; user actions (corrections, approvals, queries).
**Outputs:** requests to the API Layer; captured human corrections/approvals routed to the correction-event stream (RFC-004 Part 5.2).
**Dependencies:** API Layer exclusively — the Application Layer should never call any layer beneath the API Layer directly, which is the architectural guarantee that a new application surface (a mobile app, a Slack-native review flow) can be added without touching anything below the API.
**Failure modes:** business logic leaking into presentation code (Part 1.3's named risk); UI treating a low-confidence proposal as if it were verified fact, undermining RFC-002's structural distinction between proposal and knowledge.
**Replacement strategy:** individual application surfaces are the *most* replaceable thing in the platform by design — a surface can be rebuilt entirely without touching any layer beneath the API.
**Future scalability:** every named RFC-003 Part 8 digital-workforce role gets its own application surface eventually (a CFO-advisor briefing view, a compliance-officer dashboard) — all built as independent Application-Layer surfaces against the same API, never as one growing monolith UI.

## 2.3 API Layer
**Purpose:** the platform's one stable, versioned contract to everything above it, and eventually to external parties.
**Inputs:** calls from Application Layer surfaces, external integrations, and (future) MCP-exposed tool calls.
**Outputs:** routed requests into Automation & Workflow or, for read-only queries, directly into Knowledge & Memory / Ontology via the Reasoning layer's Context Manager pattern.
**Dependencies:** Automation & Workflow Layer for anything consequential; Knowledge & Memory / Ontology for read paths.
**Failure modes:** version sprawl without a deprecation discipline (mitigated by RFC-004 Part 2.3's data-contract versioning principle applied here to API contracts specifically); orchestration logic accumulating in this layer (Part 1.3's named risk).
**Replacement strategy:** the contract (not the implementation) is the durable asset — implementation can be rewritten freely as long as the versioned contract is honored or formally deprecated.
**Future scalability:** this is the layer that eventually exposes an MCP-compatible surface (RFC-001 Part 2's prediction) once that protocol's security model matures for consequential financial actions (RFC-003 Part 10's 2026 outlook) — designing the API layer with clean, tool-call-shaped semantics now (rather than ad hoc REST endpoints that don't map cleanly to a tool-call model) is a low-cost hedge for that future without committing to MCP today.

## 2.4 Automation & Workflow Layer
**Purpose:** sequence multi-step processes durably, gate consequential actions by reversibility (RFC-003 Part 6.1), hold the Policy Engine, Scheduler, Governance Layer, exception queues, and approval chains.
**Inputs:** a Planner-produced plan (from Reasoning), or a scheduled/triggered workflow definition.
**Outputs:** ordered, gated calls into Reasoning (for judgment steps), Validation & Decision (for deterministic steps), and ultimately Execution Substrate (for consequential steps) — with every transition durably logged.
**Dependencies:** Identity & Access (who is approving), Policy (what's allowed), Knowledge & Memory (workflow state, per RFC-003 Part 1's State Manager concept, which lives inside this layer).
**Failure modes:** the saga/compensating-action failure to properly unwind a partially-completed multi-system workflow (RFC-003 Part 3.1 finding #2) — this is the layer's single most consequential failure mode and must be tested explicitly, not assumed correct by construction; indefinite unmonitored waits on a human approval (RFC-003 Part 3.1 finding #5).
**Replacement strategy:** the underlying durable-execution mechanism (Part 9's build/buy table) is replaceable; the workflow *definitions* (which steps, which gates, per process) are the platform-specific asset that must survive any underlying engine swap — this argues for defining workflows in a representation independent of whichever engine currently executes them.
**Future scalability:** new automated processes (ROC filing, a future jurisdiction's equivalent of GST filing) are added as new workflow definitions on existing shared infrastructure (RFC-003 Part 6.4's shared-infrastructure principle), never as bespoke per-process orchestration code.

## 2.5 Reasoning Layer
**Purpose:** stateless judgment — planning, specialized-agent execution, model inference (frontier and SLM), context assembly.
**Inputs:** a task from the Planner, grounded context from Knowledge & Memory / Ontology via the Context Manager.
**Outputs:** proposals (extraction results, classifications, recommendations, plans) — never a direct external-system write.
**Dependencies:** Knowledge & Memory (for grounding), Ontology (for relational context), a model-serving substrate (frontier API + SLM hosting, per RFC-002 Part 5).
**Failure modes:** hallucination when grounding is incomplete or stale (mitigated structurally by the Context Manager's mandatory-citation discipline, RFC-002 Part 3.4); an agent silently exceeding its bounded authority (mitigated by Policy Engine enforcement at the Automation & Workflow boundary, never trusted to self-limit); model/vendor outage (mitigated by the Reasoning layer's designed interchangeability — RFC-003 Part 9 principle 15 — requiring at minimum a documented fallback routing path, not necessarily live multi-vendor redundancy from day one).
**Replacement strategy:** this is the layer explicitly designed to be swapped constantly (new model generations, new agent implementations) — the architectural test of success here is whether a model-generation upgrade requires zero changes to any other layer, which it should if the Context Manager and Tool Router interfaces (Part 1.3) are honored strictly.
**Future scalability:** new specialized agents (RFC-003 Part 2, Part 8's growing digital workforce) are added by registering a new bounded-authority agent definition against existing Planner/Supervisor infrastructure — never by building a parallel agent stack.

## 2.6 Ontology Layer
**Purpose:** the resolved-entity, typed-relationship, event graph (RFC-002 Part 2, RFC-004 Parts 3-4) — the platform's stable semantic backbone.
**Inputs:** validated financial events from Validation & Decision, entity-resolution proposals from Reasoning (confirmed by human checkpoint per RFC-004 Part 3.1).
**Outputs:** queryable entity/relationship/event data to Reasoning (context), to the semantic layer (metric computation), to the Application Layer (360-views, per RFC-004 Part 3.1, as live projections never separately stored copies).
**Dependencies:** Knowledge & Memory (for the rules governing what relationship types are valid, sourced from RFC-002 Part 2's typed-relationship doctrine), Validation & Decision (events only enter the graph once validated).
**Failure modes:** schema rigidity preventing addition of new entity/relationship types as domains expand (mitigated by RFC-002 Part 2.2's versioned, backward-compatible schema-evolution requirement, enforced as an architectural constraint on this layer specifically, not left to implementation discretion); indirect cross-tenant leakage through multi-hop graph traversal (RFC-004 Part 8.2's named, easy-to-miss risk — this layer's query interface must enforce tenant-scoping at every traversal hop, not just at the entry point).
**Replacement strategy:** the underlying graph storage technology (Part 9's build/buy table) is replaceable; the ontology schema itself (entity types, relationship types, event types) is the durable, owned asset and should be defined independent of storage technology, so a future storage-engine migration (relational-with-graph-query-layer today, dedicated graph database later, per RFC-004 Part 9's threshold-based adoption) does not require redefining the schema.
**Future scalability:** new domains (RFC-002 Part 4's Payroll, MCA/ROC, FEMA) each introduce new entity/relationship types as additive schema extensions — this is the layer most directly stress-tested by domain expansion, and its versioned-evolution discipline is what makes that expansion survivable without a rewrite.

## 2.7 Knowledge & Memory Layer (the Company Brain, unified per Part 0's resolution)
**Purpose:** the single versioned, trust-scored, provenance-carrying substrate for episodic memory, semantic memory, procedural memory (as executable rules, held jointly with Validation & Decision — see note below), and authority-sourced global/domain knowledge.
**Inputs:** raw episodic capture from Document Intelligence and Connector layers; distilled patterns from Evaluation/Learning; ingested statutory knowledge (RFC-002 Part 3) after human verification.
**Outputs:** grounded context to Reasoning; rule definitions to Validation & Decision; trust/freshness metadata to every consumer.
**Dependencies:** none structurally above it other than the raw capture sources — this is intentionally one of the most depended-upon, least dependent layers in the stack, consistent with RFC-002's "knowledge outlives every model" doctrine.
**Failure modes:** the four "never store" categories from RFC-002 Part 1 (raw tenant content leaking into shared partitions, unverified proposals presented as fact, credentials, unsupersede-pointed deletions) — each is a distinct, specifically-guarded failure mode, not a generic "data quality" risk; conflict left unresolved and silently defaulted (RFC-002 Part 1's conflict-resolution doctrine, enforced here as a required escalation path, never a silent pick).
**Replacement strategy:** the storage substrate (Part 9) is replaceable; the versioning/trust/provenance schema is the owned, durable asset (RFC-004 Part 10 principle 46: models are replaceable, data and its schema are not).
**Future scalability:** this layer scales primarily by partition (per-tenant episodic partitions, per-domain knowledge partitions) rather than by redesign — new domains and new tenants both fit the existing partition model without requiring a new kind of layer.

*Note on procedural memory's split location:* RFC-002 Part 1 defines procedural memory as, wherever a procedure has one provably correct form, expressed as executable rules rather than soft patterns. Architecturally, this means procedural-memory *content* (the rule definitions, versioned and governed exactly like other Knowledge) lives in this layer, while procedural-memory *execution* (actually running the rule against a specific record) happens in the Validation & Decision Layer. This is the same "definition vs. execution" split already applied to workflow definitions vs. the workflow engine (2.4) and is a consistent architectural pattern worth naming explicitly: **definitions are Knowledge-layer content; execution is a dedicated, purpose-built engine layer**, applied identically to rules, workflows, and (Part 2.4) automation processes.

## 2.8 Validation & Decision Layer
**Purpose:** deterministic rule execution with veto power over any probabilistic output — tax math, debit/credit balancing, statutory apportionment, and any procedure with exactly one correct answer.
**Inputs:** proposals from Reasoning/Document Intelligence, rule definitions from Knowledge & Memory.
**Outputs:** validated/rejected/auto-corrected records, each with a precise, explainable failure reason when rejected (RFC-003 Part 6.3's finding that deterministic failures are the best available recovery signal).
**Dependencies:** Knowledge & Memory (rule definitions, versioned by effective date), Ontology (for cross-record validation like reconciliation-adjacent checks).
**Failure modes:** a probabilistic shortcut creeping into what should be a deterministic rule (the single most important failure mode to guard against in this entire layer, per RFC-002/003's permanent doctrine — this should be enforced by a hard engineering discipline: this layer's code is ordinary, testable, non-AI software, full stop, with no exceptions negotiated under deadline pressure); stale rule application (mitigated by the effective-date versioning already required of every rule in Knowledge & Memory).
**Replacement strategy:** individual rules are added/versioned independently; the rule-execution engine itself is conventional software and among the most stable, rarely-replaced layers in the stack — appropriately, since it is also the layer bearing the most direct liability weight.
**Future scalability:** new domains bring new rule sets (RFC-002 Part 4's table), each added as new, independently-versioned rule definitions against the same execution engine — this layer's scalability is almost entirely about rule-set growth, not engine redesign.

## 2.9 Document Intelligence Layer
Covered in full in Part 3.

## 2.10 Connector Layer
Covered in full in Part 5.

## 2.11 Evaluation Layer
**Purpose:** continuous, five-layer measurement (RFC-003 Part 4.1) of every other layer's output quality, drift, cost, and calibration.
**Inputs:** outputs and outcomes from every layer, human corrections/approvals (RFC-004 Part 5.2's correction-as-event), the professionally-graded eval set.
**Outputs:** trust-score adjustments (fed back to Knowledge & Memory and to per-agent authority in Automation & Workflow's Policy Engine, per RFC-003 Part 7.4), drift alerts (to Observability), promotion candidates (to Knowledge & Memory's promotion-verification checkpoint — proposed, never auto-applied).
**Dependencies:** every layer above it, structurally, since it measures all of them; the owned eval set specifically, held in Knowledge & Memory as a distinguished, especially-protected partition given its strategic-asset status (RFC-002/RFC-003 Part 9).
**Failure modes:** measuring without acting (a well-known MLOps anti-pattern — dashboards nobody uses to change anything) mitigated by this layer's outputs being wired directly into the promotion and trust-adjustment mechanisms rather than existing only as a reporting surface; eval-set staleness or contamination (the eval set itself needs the same freshness/versioning discipline as any other knowledge asset, a subtlety easy to overlook when the eval set is treated as "just test data").
**Replacement strategy:** the measurement infrastructure (Part 9's build/buy table) is replaceable; the eval set and the professional-grading process are the owned, durable, strategic asset.
**Future scalability:** new agents, workflows, and domains each register their own eval criteria against shared measurement infrastructure — this layer's scalability, like Knowledge & Memory's, is by partition/registration, not by redesign.

## 2.12 Observability & Security Layer
**Purpose:** system-health telemetry unified with decision-provenance logging (RFC-003 Part 1.2), tenant isolation enforcement at every layer independently (RFC-004 Part 8.2), encryption, and the Safety Layer's runtime anomaly backstop.
**Inputs:** telemetry and provenance events from every layer.
**Outputs:** dashboards and alerts for operations; a queryable, reconstructible provenance chain for any output, on demand, for audit purposes (RFC-002/003's explainability doctrine, operationalized here as the actual serving mechanism for "explain this number" requests).
**Dependencies:** every layer, structurally.
**Failure modes:** provenance and health telemetry drifting into two inconsistent systems (RFC-003 Part 1.2's explicit warning against this); a Safety Layer with no properly maintained "normal" baseline, rendering its anomaly detection decorative (RFC-003 Part 9 principle 12).
**Replacement strategy:** standard observability tooling (Part 9) for the telemetry side; the provenance schema and its linkage to every other layer's data model is the owned, durable design.
**Future scalability:** this layer's reach grows automatically as new layers/agents/workflows are added, provided every new component is built to emit into the shared observability substrate from day one — a discipline enforced by making observability emission part of the platform's shared component contract (Part 1.3), not an opt-in feature teams remember to add later.

## 2.13 Execution Substrate
**Purpose:** the sole, narrow surface permitted to cause a real-world, hard-to-reverse effect.
**Inputs:** a fully-approved, fully-validated, policy-cleared action from Automation & Workflow.
**Outputs:** the actual external effect (ERP write, filing submission, message send) plus an idempotency-logged record of having done so.
**Dependencies:** Connector Layer (to actually reach the external system), Automation & Workflow (for the approval it never second-guesses — by the time an action reaches here, the decision has already been made).
**Failure modes:** non-idempotent retry causing duplicate effects (RFC-003 Part 6.4's central, named risk — mitigated by the idempotency-log requirement being a hard, non-negotiable property of every Execution Substrate action, no exceptions); an action reaching this layer without having actually passed every required gate upstream (mitigated by this layer independently re-verifying the presence of a valid approval/policy-clearance token rather than trusting that an upstream caller "must have" checked — defense in depth, consistent with RFC-004 Part 8.2's isolation-enforced-independently-at-every-layer principle applied to authorization rather than tenancy).
**Replacement strategy:** deliberately the most conservative, least frequently changed layer in the entire stack — its narrowness is a feature, and expanding its responsibility beyond "perform one already-approved action idempotently" should be resisted as a standing architectural discipline.
**Future scalability:** new external-effect types (a new filing type, a new payment-adjacent action once/if that's ever in scope) are added as new, narrow, individually-idempotent action handlers — this layer never grows in *responsibility*, only in the *count* of narrowly-scoped actions it can perform.

---

# PART 3 — DOCUMENT INTELLIGENCE ARCHITECTURE

## 3.1 The layered-OCR design, and why layering (not a single model) is correct
Per RFC-002 Part 5's SLM economics and RFC-004 Part 5.1's confidence-vs-trust distinction, a single-pass "throw it at the best available model" design is architecturally wrong for this domain, for a specific reason: **different document types, languages, and quality levels have wildly different accuracy/cost profiles for different extraction techniques, and a document platform that doesn't route accordingly either overpays for easy documents or underperforms on hard ones.** The correct architecture is a **routing-first pipeline**, not a single-model pipeline:

**Stage 1 — Document classification and routing.** Every incoming document is first classified (document type, language, quality tier, layout family) by a cheap, fast pass — this classification result determines which downstream extraction path the document takes. This stage itself should be an SLM-appropriate task per RFC-002 Part 5.3 (a narrow, well-specified classification task) once sufficient labeled data exists, and a lightweight heuristic/small-model combination before that.

**Stage 2 — Layout-aware structural extraction.** For born-digital or high-quality-scan PDFs (the majority of the current invoice/GST workload, per the existing `pdfplumber` coordinate-aware approach), spatial/layout-aware extraction runs directly — this path should remain the thin, owned, controllable layer RFC-001 Part 5 and RFC-002 Part 8 already established as correct, not replaced wholesale by a commercial API, because it's tightly coupled to downstream reconciliation logic.

**Stage 3 — Vision-model fallback for degraded input.** For scanned/photographed/thermal-receipt/handwritten documents where layout-aware text extraction fails or scores low-confidence, the document routes to a vision-capable model pass (either a commercial document-AI API per RFC-001 Part 5's buy verdict, or a vision-capable LLM) — this is explicitly a **fallback path, entered by confidence-based routing, not the default path**, because it is more expensive and, for born-digital documents, offers no accuracy advantage over Stage 2's structural extraction.

**Stage 4 — Semantic parsing and canonical mapping.** Whichever stage produced the raw structured output, the result is mapped into the canonical event schema (RFC-004 Part 2) — this stage is where document-type-specific and language-specific field semantics are resolved (which field is the GSTIN, which is the taxable value, correctly identified regardless of whether the source language was English, Hindi, or mixed).

**Stage 5 — Confidence-based review routing.** The combined confidence signal from Stages 1-4 (never a single opaque score — per RFC-004 Part 5.1's trust-vs-confidence distinction, this platform must expose *which* stage was uncertain and why, not just a final blended number) determines whether the document proceeds directly to Validation & Decision (high confidence, full-population deterministic checking still applies regardless) or is queued for human review at the appropriate confidence-proportional priority (RFC-003 Part 4.1 Layer 2's discipline: concentrate human review where uncertainty and impact are highest, not uniformly).

## 3.2 Multilingual and mixed-language design
English, Hindi, and mixed-language documents are not a separate pipeline — they are a dimension of Stage 1's classification and a requirement threaded through every stage: Stage 1's classification includes language/script detection; Stage 2/3's extraction models must be selected or configured for the detected language (a layout-aware extractor tuned for Latin-script text will underperform on Devanagari without explicit multilingual support, and mixed-language documents — an English invoice template with a Hindi-language item description, common in SME trade documents — require field-level, not document-level, language handling); Stage 4's semantic mapping must resolve field labels correctly regardless of the label's language (a "मात्रा" column must map to the canonical `quantity` field exactly as a "Qty" column would). **The architectural principle: language is a routing and configuration parameter threaded through the existing five-stage pipeline, never a reason to build a separate parallel pipeline** — a separate Hindi-document pipeline would fragment the confidence-routing, review-queue, and learning-loop infrastructure that must stay unified for the correction loop (Part 4) to work correctly across all documents regardless of language.

## 3.3 The learning loop, specific to Document Intelligence
Every human correction made during Stage 5's review is captured as a first-class event (RFC-004 Part 5.2) and feeds two distinct downstream uses: (1) immediate session-level application (RFC-003 Part 7.2's fast loop — the same vendor's remaining documents in this batch benefit immediately), and (2) accumulation toward Stage 1/2/3's own SLM training data (RFC-002 Part 5.4's data-gated SLM ownership threshold) — meaning Document Intelligence is architecturally the layer most directly responsible for generating the raw material the platform's eventual SLM strategy depends on, and its correction-capture discipline should be held to the highest rigor in the entire platform for that reason.

## 3.4 Build vs. buy for Document Intelligence specifically
Consistent with and extending WORLD_INTELLIGENCE_REPORT.md Part 5 and PHASE_1_5 Part 8: **Stage 1 (classification/routing)** — build, it's the thin orchestration logic that is the actual architectural value of this layer. **Stage 2 (layout-aware structural extraction for born-digital documents)** — build/maintain the thin, controllable layer already in place; this is a deliberate, justified exception to "never build commodity infrastructure" because it's tightly coupled to downstream domain logic, not a general-purpose capability. **Stage 3 (vision fallback for degraded/handwritten/photographed input)** — buy, via commercial document-AI or vision-model APIs; building general-purpose vision-based OCR to compete with well-funded commercial offerings is exactly the capital-destructive move RFC-001 Part 5 already ruled out. **Stage 4 (semantic/canonical mapping)** — build, this is where domain-specific correctness (GST field semantics, multilingual label resolution) lives and is the layer's actual differentiation. **Stage 5 (confidence-routing and review-queue infrastructure)** — build, this is core product experience and tightly coupled to the Company Brain's correction loop, not a generic capability available to buy.

---

# PART 4 — COMPANY BRAIN INTEGRATION

## 4.1 The runtime loop, mapped onto the layer stack precisely
RFC-003 Part 7 specified the loop conceptually (Knowledge → Planner → Reasoner → Agents → Verification → Execution → Evaluation → Learning → Knowledge Update). This section maps that loop onto Part 1's concrete layer stack, closing the gap between the two documents:

**Knowledge & Memory Layer** supplies grounded context, through the **Reasoning Layer's** Context Manager, to the **Reasoning Layer's** Planner, which decomposes the goal and delegates to specialized agents (also Reasoning Layer, per Part 1.3's stateless-agent doctrine) within bounded authority enforced by the **Automation & Workflow Layer's** Policy Engine. Agent proposals pass to the **Validation & Decision Layer** (deterministic verification) and/or a human reviewer (via the **Application Layer**, routed by the **Automation & Workflow Layer's** approval-gate logic). Verified outputs proceed to the **Execution Substrate**. Outcomes and captured corrections flow to the **Evaluation Layer**, whose findings feed the **Knowledge & Memory Layer's** promotion-verification checkpoint, closing the loop.

## 4.2 Why this mapping matters architecturally, beyond restating RFC-003
The value of making this mapping explicit is that it exposes exactly **which layer boundary each part of the loop must cross**, which is where integration bugs and governance gaps actually occur in practice. Three boundary-crossings deserve specific architectural attention beyond what RFC-002/003 already established:

**The Reasoning-to-Validation boundary** must be a hard, structural handoff — an agent's proposal is a distinct object type from a validated record (never the same object with a "validated" flag flipped in place, which would make it too easy for a bug to skip the flip and treat an unvalidated proposal as validated). This is the concrete implementation of RFC-002 Part 1's "structurally distinct" staging doctrine.

**The Evaluation-to-Knowledge&Memory promotion boundary** must never be a direct write path — Evaluation's findings are themselves proposals (of a different kind: "this pattern appears to hold") that pass through the same differentiated verification checkpoints (RFC-002 Part 3.3) as any other knowledge candidate, enforced by the Knowledge & Memory Layer's own write interface refusing direct writes from Evaluation and requiring the verification-checkpoint path instead — an architectural guarantee, not a process convention that could be skipped under pressure.

**The Automation & Workflow-to-Execution boundary** is where RFC-003's reversibility-based gating actually becomes enforceable code rather than a design intention — this boundary is the single most safety-critical interface in the entire platform, and should be implemented as the narrowest, most heavily tested interface in the system, consistent with Execution Substrate's designed narrowness (Part 2.13).

## 4.3 The Company Brain as the platform's actual center of gravity
Restating this once, architecturally rather than strategically (RFC-001 already made the strategic case): **every layer in Part 1's stack except Identity/Access, Application, API, and Execution Substrate either reads from or writes to the Knowledge & Memory and Ontology layers.** This is not incidental — it is the direct architectural consequence of RFC-001's moat thesis. A useful architectural test for any future platform change: *if a proposed new capability doesn't touch Knowledge & Memory or Ontology at all, it is very likely either a thin Application-layer feature (fine, low strategic weight) or a sign that the capability has been designed outside the compounding-asset loop and should be reconsidered before being built* (a direct, practical instantiation of RFC-004's final-synthesis warning against building things that don't compound).

---

# PART 5 — UNIVERSAL CONNECTOR ARCHITECTURE

## 5.1 One standard interface, precisely specified (in responsibility terms, not code)
Every connector, regardless of what it connects to, must expose the same four responsibilities to the rest of the platform, and nothing more:

1. **Fetch** — retrieve data from the external system, in whatever native pattern that system requires (polling, webhook receipt, streaming subscription, offline-sync relay — RFC-003 Part 5.1's pattern-matched-to-system-capability doctrine), and hand it to Document Intelligence / canonical mapping (RFC-004 Part 2.3) in the connector's declared, versioned data contract.
2. **Push** — accept an already-approved, canonically-shaped action from the Execution Substrate and translate it into the external system's native write operation, idempotently (RFC-003 Part 6.4).
3. **Resolve** — answer identity/reference-lookup questions against the external system when needed (does this vendor already exist in the client's Tally, what's the current chart-of-accounts) — read-only, used by entity resolution (RFC-004 Part 3) and by pre-push validation.
4. **Health** — report connectivity/credential/rate-limit status to Observability, so a connector outage is visible at the platform level rather than only discoverable as a downstream mystery (Part 2.13's stated failure mode).

Every connector implements exactly these four responsibilities and nothing else — a connector that starts implementing reconciliation logic, interpretation, or business rules has violated its boundary (Part 1.3's explicit warning) and that logic must be pulled back into Validation & Decision or Reasoning where it belongs.

## 5.2 Why one interface can span such different external systems
The interface works uniformly across ERPs (Tally, Busy, Marg, Zoho, QuickBooks, SAP, Oracle), spreadsheets (Excel, Google Sheets, Airtable), government systems (GSTN via GSP, MCA, ROC, bank APIs), communication (Slack, Teams, WhatsApp, Email), storage (Drive, OneDrive, Dropbox), and analytics (Power BI, Snowflake) because **Fetch/Push/Resolve/Health are defined at the responsibility level, not the protocol level** — a given connector's *implementation* of Fetch might be XML-over-HTTP polling (Tally today), a REST API webhook receiver (a modern SaaS ERP), or a GSP-mediated government API call, but the Tool Router (Part 2.5, RFC-003 Part 1.2) and every upstream consumer only ever sees the same four-responsibility contract, never the protocol details underneath. This is the direct architectural payoff of RFC-004 Part 2.3's data-contract discipline, applied specifically to the connector boundary.

## 5.3 Differentiating connector categories architecturally, per RFC-001/RFC-004's build/buy doctrine
**ERP connectors (Tally today, SAP/Zoho/QuickBooks as demand justifies)** — implement all four responsibilities fully, including Push, because these are the ontology's primary inlet/outlet (RFC-001 Part 5, RFC-004 Part 9) and must be owned and hardened. **Spreadsheet connectors (Excel, Google Sheets)** — implement Fetch and Push fully (import/export), never attempt to become a spreadsheet engine (RFC-001 Part 5's explicit boundary) — Push here specifically means "render the canonical output as a spreadsheet a human opens," not "operate a live spreadsheet application." **Government connectors (GSTN via GSP, MCA, ROC, bank APIs)** — implement Fetch and Push through the sanctioned GSP/API layer only (RFC-001/RFC-004's partner-not-build verdict), with Push here always terminating in a human-approval gate upstream at the Automation & Workflow layer (Part 6.3's permanent doctrine) regardless of how the connector itself is implemented. **Communication connectors (Slack, Teams, WhatsApp, Email)** — implement Fetch (inbound triggers/replies) and Push (outbound notifications) only; Resolve and Health are typically trivial/not applicable — these remain intentionally the thinnest connector category, consistent with their pure-transport role (RFC-001 Part 5). **Storage connectors (Drive, OneDrive, Dropbox)** — Fetch-dominant (document ingestion), with Push limited to archival (Part 1's lifecycle Archival stage). **Analytics connectors (Power BI, Snowflake)** — Fetch-only in the outbound direction (the platform pushes its own semantic-layer outputs *to* these systems on request) — never a two-way sync, consistent with RFC-001 Part 5's "never build a competing BI tool" doctrine; these connectors expose read access to the semantic layer (RFC-004 Part 6.2), not a general data-export free-for-all.

## 5.4 Versioning, retry, and conflict resolution, architecturally positioned
Per RFC-003 Part 5.2, every connector's adapter is versioned per external-system-version, with a declared compatibility matrix living in the connector registry (a component of the Connector Layer, queried by the Tool Router). Retry/backoff and idempotency are **shared platform infrastructure** (Part 2.4's "shared infrastructure for shared concerns" principle, RFC-003 Part 5.3) that every connector inherits rather than reimplements — architecturally, this means the connector registry and the idempotency/retry framework are themselves platform components a new connector plugs into, not something each new connector author builds from scratch. Conflict resolution follows RFC-003 Part 5.2's doctrine positioned precisely: the connector layer detects a discrepancy between AuditOS's cached state and the external system's live state and **surfaces it upward to Validation & Decision / human review**, never resolving it silently within the connector itself — the connector's Resolve responsibility is for lookups, not for adjudicating conflicts, which is out of scope for this layer by design.

---

# PART 6 — WORKFLOW PLATFORM

## 6.1 What the named example chain actually requires, layer by layer
Invoice → Extraction → Validation → Reconciliation → Approval → ERP Push → GST Filing → Notification → Archive, mapped onto Part 1's stack: Extraction is Document Intelligence; Validation and Reconciliation are Validation & Decision (Reconciliation additionally consults Ontology for cross-referencing); Approval is an Automation & Workflow human-gate step; ERP Push and GST Filing are Execution Substrate actions (each behind its own Connector, each individually idempotent, GST Filing specifically always human-gated per Part 5.3/RFC-003 Part 6.3's permanent doctrine); Notification is a Connector Push (communication category); Archive is the Part 1 lifecycle's Archival stage, a Knowledge & Memory retention-tier transition, not a new action type.

## 6.2 Which durable-execution principles the architecture adopts, and at what maturity
Per this RFC's instruction to recommend only what fits AuditOS's current scale and maturity, not the full weight of every durable-execution research finding at once: **adopt now** — durable state persistence across restarts (the workflow's position must survive a deploy or crash, non-negotiable even at current scale, because a lost mid-flight GST-filing-approval workflow is unacceptable regardless of company size); idempotency at every external-system-touching step (already partially proven in production via the Tally-push-log pattern, RFC-001 — this architecture's requirement is to generalize that exact pattern to every connector, not invent a new mechanism); designed timeout-and-escalation on every human-approval wait (currently likely underspecified — a concrete near-term architecture gap worth flagging for RFC-005A-level follow-up, not deferred to a future phase, because an approval silently going stale is a real, current-scale risk, not a hypothetical future-scale one). **Adopt when evidenced (Phase 2-3, Part 10)** — a dedicated durable-execution engine (Temporal-class) replacing the current Celery-based approach, once the number and complexity of multi-day, multi-system sagas genuinely exceeds what hand-rolled idempotency/state-tracking on top of Celery can maintain correctly (RFC-004 Part 9's Temporal verdict, reconfirmed) — this is explicitly *not* a Phase 1 recommendation, consistent with the "do not overengineer Phase 1" instruction.

## 6.3 Recovery, rollback, and exception handling, positioned architecturally
Recovery and rollback are saga/compensating-action concerns (RFC-003 Part 3.1) that belong entirely inside the Automation & Workflow Layer's workflow-definition logic — never inside Execution Substrate (which only performs one idempotent action and has no visibility into the broader saga) and never inside Connectors (which have no visibility into cross-system consistency, only their own single external system). Exception queues are shared Automation & Workflow infrastructure (Part 2.4, RFC-003 Part 6.4), fed by any workflow step that fails validation, times out, or is flagged by the Safety Layer — routed to the Application Layer's review surfaces by priority derived from Part 5.1 (RFC-003)'s materiality/confidence weighting, never a flat FIFO queue.

---

# PART 7 — KNOWLEDGE PLATFORM

## 7.1 The mechanics, mapped onto Part 1's stack
**Ingestion** (RFC-002 Part 3) enters the Knowledge & Memory Layer through source-class-specific paths: statutory-source ingestion (human-verified, low-frequency, high-stakes) enters through a distinct, more heavily gated write path than tenant-episodic ingestion (high-volume, sampled-review, per RFC-002 Part 3.3's differentiated-checkpoint doctrine) — architecturally, these should be genuinely separate ingestion pipelines feeding the same underlying versioned store, not one generic ingestion path with a flag, because their throughput, review requirements, and failure consequences are different enough to warrant separate operational tooling and separate on-call/alerting posture.

**Refresh** (freshness windows, RFC-002 Part 1/3) is implemented as a scheduled re-verification job (Automation & Workflow Layer's Scheduler) per knowledge domain, at the domain-specific cadence RFC-002 Part 4's table established — architecturally, this means the Scheduler needs a per-domain freshness-window configuration, not a single global refresh interval.

**Versioning** is a structural property of every record in the Knowledge & Memory store (effective-from/to, supersession pointer, per RFC-002 Part 1) — not a feature bolted onto specific record types, but a schema-level guarantee every write path must satisfy, enforced at the store's write interface.

**Promotion** and **Retirement** flow through the verification-checkpoint mechanism (Part 4.2 above) — architecturally the critical point is that the *only* path from "proposal" to "trusted knowledge" is through this checkpoint; there must be no secondary write path (a debug tool, an admin override) that bypasses it, because such a bypass would be exactly the kind of gap that erodes RFC-002's ground-truth doctrine in practice, quietly, long before anyone notices.

**Verification** is the human-checkpoint mechanism itself (Part 2.2's Application-layer surfaces feeding into it), differentiated by type per RFC-002 Part 3.3 — architecturally this means at least four distinct verification UI/workflow patterns (interpretation, extraction, promotion, conflict-adjudication), not one generic "review this" screen, because the reviewer's task and required expertise genuinely differs across the four.

## 7.2 How the Company Brain stays current without hallucinating — the architectural mechanism, precisely
This is the direct architectural answer to this Part's explicit question, synthesizing RFC-002 Part 3.4 and RFC-003 Part 1.2's Context Manager into one concrete mechanism: **the Reasoning Layer's Context Manager is architecturally forbidden from assembling context that lacks a trust score and a citation pointer back to Knowledge & Memory**, and any model output that makes a factual claim not traceable to assembled context is treated by the Evaluation Layer as a defect (an ungrounded claim), not merely a stylistic issue. This is enforceable architecturally, not merely as a prompting guideline, because the Context Manager is a distinct, testable component (Part 1.3) whose output can be validated independently of whatever the Reasoning Layer's model does with it — **grounding is verified at the interface between Context Manager and Reasoning, not hoped for from the model's behavior.**

---

# PART 8 — EVALUATION PLATFORM

## 8.1 Architecture for continuous, layered evaluation, mapped onto components
RFC-003 Part 4.1's five layers, positioned: Layer 1 (component regression) runs against Document Intelligence, Validation & Decision, and Connector Layer outputs on every change — standard CI-adjacent infrastructure, cheap, automated, no architectural novelty required. Layer 2 (professional ground truth) runs against Reasoning Layer and Document Intelligence outputs, drawing from the owned eval set held in a specially-protected Knowledge & Memory partition (Part 2.11). Layer 3 (agent/workflow chain-level) runs against the full Reasoning-to-Execution path, requiring the Evaluation Layer to have read access to the full provenance chain (Observability & Security Layer) for any given case, not just its final output. Layer 4 (drift monitoring) runs as a continuous statistical-process-control job over Layers 1-3's pass rates, feeding alerts to Observability. Layer 5 (human trust metrics) draws from Application Layer interaction telemetry (review time, override rate) — architecturally, this requires the Application Layer to emit these specific interaction signals as first-class telemetry, not just functional UI events, which is a concrete, non-obvious requirement worth stating explicitly so it isn't missed when application surfaces are built.

## 8.2 Business metrics and customer success as an evaluation-layer concern
Extending RFC-003 Part 4 with what this Part's prompt adds explicitly (Customer Success, Business Metrics) that RFC-003 didn't fully specify: these are architecturally a **sixth practical measurement stream, distinct from but feeding the same Evaluation Layer** — adoption depth per client, time-to-value, correction-rate trend per client over time (a leading indicator of whether the flywheel, RFC-004 Part 7, is actually turning for that specific relationship). This stream should be architected to draw from the same Application-layer and Observability telemetry as Layer 5's human-trust metrics, rather than a separately bolted-on business-intelligence system, because the underlying data source is the same and a second, disconnected reporting pipeline would risk exactly the metric-definition-drift problem RFC-004 Part 6.2 warned against.

## 8.3 How we know the platform gets smarter every month — the specific, checkable architecture
Not an aspiration — a specific, monitorable dashboard architecture: Layer 2's professional-eval pass rate over time, Layer 4's drift-adjusted trend line, and the correction-rate-per-document-volume trend (Part 8.2) together, plotted against the SLM-promotion and rule-promotion event log (Part 7.1) — if pass rates are flat or declining while promotion events continue, that is itself a Layer-4-detectable signal that the flywheel (RFC-004 Part 7.1's "where it stalls" finding) has stalled despite still *looking* active, and this is precisely the kind of failure this evaluation architecture is built to catch that a simpler "we have an eval suite" design would miss.

---

# PART 9 — AUTOMATION PLATFORM, BUILT ON SHARED PLATFORM COMPONENTS

## 9.1 Human-in-the-loop, risk gates, approval chains, recovery — as shared Automation & Workflow Layer components
Per RFC-003 Part 6.4's shared-infrastructure principle and Part 2.4 above: Human-in-the-loop gating is implemented once, as a configurable step type in the workflow-definition language (Part 6.2), parameterized by reversibility/blast-radius classification (RFC-003 Part 6.1's matrix) — every automated process (GST filing, vendor creation, MIS report distribution) declares its gate type by referencing this shared step type with process-specific parameters, never by implementing its own bespoke approval logic. Risk gates (the Safety Layer's anomaly-triggered escalation, RFC-003 Part 6.2's example of bank-reconciliation gating becoming conditional) are implemented as a shared Safety Layer capability that any workflow step can subscribe to, not a per-workflow anomaly check reimplemented each time. Approval chains (multi-step, multi-approver sequences) are a shared Automation & Workflow primitive, configurable per process (a single-approver gate for routine reconciliation vs. a multi-approver chain for a large filing) without requiring new orchestration code per chain shape. Recovery/rollback are the saga-pattern mechanisms from Part 6.3, shared across every workflow definition.

## 9.2 Compliance logging and audit trails, architecturally unified
Per Part 2.12's unification of provenance and telemetry: compliance logging is not a separate system from Observability — every workflow-state transition (Part 2.4), every knowledge promotion (Part 7.1), every Execution Substrate action (Part 2.13) already emits into the same Observability & Security provenance store, and "the audit trail" for compliance purposes is a queryable *view* over that unified store, filtered to the relevant case/period/entity, never a separately maintained log a compliance officer must reconcile against the system's actual behavior.

## 9.3 The digital-workforce roles (Virtual CFO, Virtual Auditor, Virtual Tax Manager, Virtual Compliance Officer), architecturally
Each role from RFC-003 Part 8 is implemented as: (a) a bounded-authority agent definition registered with the Reasoning Layer's Planner/Supervisor, specifying its knowledge scope, tool access (via the Connector Layer's registry), and decision limits (enforced by the Automation & Workflow Layer's Policy Engine, per RFC-003 Part 2.2's escalation doctrine); (b) an Application-layer surface specific to that role's human-collaboration model (a Virtual CFO's briefing view is architecturally distinct from a Virtual Tax Manager's filing-preparation workspace, even though both sit on identical underlying Reasoning/Knowledge/Execution infrastructure); (c) role-specific evaluation criteria registered with the Evaluation Layer (RFC-003 Part 8's per-role KPI table, now given its concrete architectural home). **The architectural point worth making explicit: no digital-workforce role requires any new platform layer** — every role in RFC-003 Part 8's roster is a configuration of existing Reasoning, Automation & Workflow, Application, and Evaluation layer components, which is the direct test of whether Part 1's layer design actually achieves its stated goal ("every future capability should naturally fit into this architecture without redesign") — if a new virtual role ever required a genuinely new platform layer rather than a new configuration of existing ones, that would be a signal the layer design itself needs revisiting.

---

# PART 10 — PLATFORM EVOLUTION

## 10.1 Phase 1 — the smallest architecture that delivers immediate value
**What exists:** Identity/Access (basic tenant+auth, already largely in place), Application (the existing review workspace), API (thin, current), Document Intelligence (Stages 1-2-4-5 as already built; Stage 3 vision-fallback added only where genuinely needed for current document quality, not preemptively), Validation & Decision (the existing 8-stage reconciliation engine, generalized per Part 2.8's discipline), Connector Layer (Tally connector, Drive sync — implementing the four-responsibility interface, Part 5.1, even at small scale, because retrofitting that discipline later is expensive per RFC-004 Part 3.1's entity-resolution lesson applied here by analogy), a minimal Automation & Workflow layer (Celery-based, per RFC-004 Part 9's reconfirmed verdict — not a dedicated durable-execution engine yet), Knowledge & Memory (episodic capture and the current correction-capture UI, with the versioning/provenance schema in place from day one even though the promotion/SLM pipeline is not yet built), Observability (Sentry + structured logging, already in place, extended with the provenance-unification discipline from Part 2.12).
**What deliberately does NOT exist yet:** a dedicated Ontology/graph layer beyond what current relational schema already expresses (introduced when multi-hop relational queries genuinely become a workload, per RFC-004 Part 9); a formal multi-agent Planner/Supervisor (the current pipeline's implicit sequencing is Phase 1-adequate; formalize only once more than one or two genuinely independent specialized agents exist); a dedicated Evaluation Layer beyond ad hoc regression tests (Layer 1 only; Layers 2-5 are designed-for but built incrementally starting Phase 2); SLM ownership (data-gated, per RFC-002 Part 5.4 — Phase 1's job is disciplined correction capture that makes this possible later, not building it now).
**What must not be skipped even at this minimal scope, because retrofitting is expensive:** the versioned, provenance-carrying schema for Knowledge & Memory and for the canonical event model (RFC-004 Part 1.3, Part 2.4) — this is the one piece of "Phase 1 infrastructure" that genuinely justifies being built correctly from day one rather than deferred, because every later phase's value depends on Phase 1's correction and event data having been captured with full fidelity from the start.

## 10.2 Phase 2 — expand capabilities
Formalize the Reasoning Layer's Planner/Supervisor as more specialized agents come online (per RFC-002 Part 4's next-ring domains: Income Tax, Payroll, MCA/ROC). Introduce the dedicated Ontology layer once entity-resolution and cross-document relational queries (Part 2.6) exceed what the existing relational schema comfortably serves. Build out Evaluation Layers 2-3 (the owned professional eval set becomes an active, continuously-graded asset, not just a design intention). Begin the promotion pipeline (Part 7.1) from correction events to distilled semantic-memory patterns, still human-checkpoint-gated at every promotion. Expand the Connector Layer to additional ERPs only as actual client demand justifies (RFC-004 Part 9's threshold discipline), never speculatively.

## 10.3 Phase 3 — scale to enterprise
Introduce a dedicated durable-execution engine if and only if saga complexity has genuinely outgrown Celery (Part 6.2). Build Evaluation Layers 4-5 (drift monitoring, human-trust metrics) as standing, always-on infrastructure rather than periodic manual review. Data-gate the first domain SLM (RFC-002 Part 5.4) once a specific narrow task's verified-correction volume justifies it — likely HSN/ledger-classification-class tasks first, per RFC-002 Part 5.3's task-placement guidance. Introduce enterprise-grade Identity/Access (SSO/SAML, per Part 2.1's flagged future requirement) as upmarket ERP connectors (SAP, larger QuickBooks/Xero deployments) bring larger, more IT-governed clients. Formalize the differentiated cross-tenant aggregate-learning mechanism (RFC-004 Part 8.1) with its provability requirement, once cross-tenant benchmarking (RFC-002 Part 4's Advisory cluster) becomes a real product surface rather than a future direction.

## 10.4 Phase 4 — scale globally
Extend the canonical event model (RFC-004 Part 2.2) and the rule-execution engine (Part 2.8) to a second jurisdiction's invoice-matched VAT/GST regime (RFC-001 Part 6's portability thesis), explicitly building the new jurisdiction's rule set and connector layer as additive extensions of existing infrastructure, never a parallel platform. Introduce federated-learning or differential-privacy infrastructure (RFC-004 Part 8.4) only once cross-jurisdiction, cross-tenant benchmarking claims at that scale genuinely require their specific guarantees. Evaluate genuine streaming/real-time infrastructure (RFC-004 Part 9's Kafka-class verdict) only if a real-time risk/fraud-monitoring workload (RFC-002 Part 4's Risk/Fraud derived domain) has matured into an active product at a scale that justifies it. **Explicitly, per RFC-004's final synthesis, Phase 4 does not begin until Phase 1-3's learning-effect depth in the current core market is genuinely saturating** — premature Phase 4 expansion dilutes the concentrated learning-effect advantage that makes the whole platform's moat real, and this phasing discipline is as architecturally important as any layer boundary defined in this document.

## 10.5 The evolution test every phase must pass
Consistent with this RFC's opening mandate ("every future capability should naturally fit into this architecture without redesign"): at the end of every phase, the test is not "did we ship more features" but **"did any new capability require a new platform layer, or only a new configuration/extension of an existing one."** Part 9.3 already demonstrated this test passing for the entire digital-workforce roster using only Phase 1-3's layers. Any future capability that fails this test — that seems to require inventing a genuinely new layer rather than extending Part 1's stack — should trigger a specific, deliberate architecture review before being built, rather than being absorbed as an ad hoc exception, because that is exactly the moment architectural erosion begins.

---

# PART 11 — BUILD / BUY / PARTNER / OPEN SOURCE / MANAGED SERVICE / DELAY / IGNORE, PER SUBSYSTEM

Consolidating and finalizing (not re-deriving) the verdicts scattered through RFC-001, RFC-002, and RFC-004, now positioned against this architecture's specific layers, with any new subsystems this RFC introduced given their own verdict.

| Subsystem | Verdict | Layer | Justification (brief; full justification in cited RFC) |
|---|---|---|---|
| OCR / vision fallback | Buy (API) | Document Intelligence, Stage 3 | RFC-001 Part 5 |
| Layout-aware structural extraction | Build | Document Intelligence, Stage 2 | RFC-001 Part 5 — thin, controllable, domain-coupled |
| Document classification/routing | Build | Document Intelligence, Stage 1 | Core orchestration value of the layer |
| Semantic/canonical mapping | Build | Document Intelligence, Stage 4 | Domain-specific correctness is the differentiation |
| ERP connectors (Tally, future SAP/Zoho) | Build | Connector Layer | RFC-001 Part 5, RFC-004 Part 9 — ontology inlet |
| Spreadsheet connectors (Excel/Sheets) | Build (compatibility layer only) | Connector Layer | RFC-001 Part 5 — never build the spreadsheet engine |
| Government/GST connectors | Partner (GSP) | Connector Layer | RFC-001 Part 5 — regulatory gating |
| MCA/ROC connectors | Partner/API, delay until demand | Connector Layer | RFC-001 Part 4/5 — next-ring, not core wedge |
| Communication connectors (Slack/Teams/WhatsApp/Email) | API integration | Connector Layer | RFC-001 Part 5 — pure transport |
| Storage connectors (Drive/OneDrive/Dropbox) | API integration | Connector Layer | RFC-001 Part 5 |
| Analytics connectors (Power BI/Snowflake) | API integration, outbound-only | Connector Layer | RFC-001 Part 5 — never a competing BI tool |
| Identity & Access infrastructure | Buy/Open standard | Identity & Access | RFC-001 Part 5 — never build custom crypto |
| Workflow/orchestration engine (current scale) | Open Source (Celery) | Automation & Workflow | RFC-004 Part 9 — reconfirmed, Phase 1-2 adequate |
| Durable-execution engine (Temporal-class) | Delay until evidenced | Automation & Workflow | RFC-004 Part 9, Part 6.2 above — Phase 3 candidate |
| Data-pipeline orchestration (Dagster/Prefect-class) | Delay until evidenced, distinct from above | Knowledge Platform / Ontology ingestion | RFC-004 Part 9 — a different problem than workflow orchestration; don't conflate |
| Table formats (Iceberg/Delta) | Ignore for now | Knowledge & Memory / Ontology storage | RFC-004 Part 9 |
| OLAP store (ClickHouse) / Arrow / DuckDB | Open Source, adopt opportunistically | Semantic layer / Evaluation reporting | RFC-004 Part 9 |
| Event streaming (Kafka/Redpanda) | Delay until evidenced | Ontology event log | RFC-004 Part 9 — Phase 4 candidate at earliest |
| Graph database (Neo4j-class) | Delay until evidenced | Ontology Layer | RFC-004 Part 9, Part 2.6 above |
| Relational store (PostgreSQL) | Buy/Open Source, foundational | Ontology, Knowledge & Memory, Validation & Decision, workflow state | RFC-004 Part 9 — correct default throughout Phase 1-2 |
| Vector search (pgvector → dedicated) | Open Source, threshold-gated upgrade | Knowledge & Memory retrieval | RFC-004 Part 9 |
| Observability/APM (Sentry + OpenTelemetry) | Buy/Open Source | Observability & Security | RFC-001 Part 5, RFC-004 Part 9 |
| ELT/connector plumbing (Airbyte/Meltano-class) | Use for peripheral sources only, never core ERP connectors | Connector Layer (peripheral) | RFC-004 Part 9 |
| CDC (Debezium) | Open Source, per-connector evaluation | Connector Layer | RFC-004 Part 9 |
| Metric/semantic-layer versioning (dbt-class) | Open Source, adopt once semantic layer is non-trivial | Knowledge & Memory (semantic partition) | RFC-004 Part 9, Part 2.7 above |
| Agent orchestration framework (LangChain-class) | Avoid for core loop; thin owned primitives instead | Reasoning Layer | RFC-002 Part 8, RFC-003 Part 9 — indirection fights auditability |
| Foundation model training | Never | Reasoning Layer | RFC-001 Part 5 — permanent, absolute |
| Fine-tuning infrastructure (LoRA/QLoRA tooling) | Buy/API, data-gated timing | Reasoning Layer (SLM) | RFC-002 Part 5 |
| Eval-set and professional-grading process | Build, permanently owned | Evaluation Layer | RFC-002/003/004 — the strategic asset itself |
| Eval-harness plumbing | Open Source | Evaluation Layer | RFC-002 Part 8 |
| MCP-compatible API exposure | Delay until protocol/security model matures | API Layer | RFC-001 Part 2, RFC-003 Part 10 — 2026-2028 candidate |
| Federated learning / differential privacy | Delay, scale-and-claim-gated | Knowledge & Memory (cross-tenant aggregate) | RFC-004 Part 8.4 |
| Enterprise SSO/SAML | Buy, demand-gated (Phase 3) | Identity & Access | Part 2.1, Part 10.3 above |

---

# ARCHITECTURE RISKS & RED TEAM REVIEW

*Written as a Principal Engineer who has to actually ship this with a small team, and who is skeptical of the document above. Nothing in this section gets softened because a prior RFC said it first — prior doctrine explains why a capability might eventually matter, not that it should be built now, by this team, at this size.*

## R.1 The core objection
This document names roughly **21 platform components across 13 layers** (Scheduler, Planner, Context Manager, Tool Router, Policy Engine, Governance Layer, Safety Layer, State Manager, Decision Engine, Resource Manager, plus the 13 named layers themselves) before a single new domain (Payroll, Income Tax, ROC) has been added to a product that today has **one working ERP connector, one reconciliation engine, and a review workspace.** That is not a Phase 1 architecture. That is a Series-C platform-engineering org chart wearing a Phase 1 costume. If a two-to-four-person team tries to stand up even a defensible skeleton of all 13 layers before shipping the next real client-facing capability, the most likely outcome is not "a decade-durable platform" — it is eighteen months of scaffolding, zero new revenue-relevant features, and a team that burns out maintaining abstractions nothing yet uses. **The single biggest risk in this document is not any one layer being wrong — it's the document implying all of it should exist before the next feature ships.**

## R.2 Overengineering, named specifically

- **Ontology Layer as a distinct platform layer, day one.** A dedicated entity/relationship/event graph, with its own storage strategy, its own schema-evolution discipline, its own query interface — for a product that currently has maybe a few thousand resolved vendor entities across all clients combined. This is solving a scale problem AuditOS does not have. A `vendors` table with a `resolved_entity_id` foreign key and a `vendor_aliases` table for the fuzzy-name variants gets 90% of the practical benefit (RFC-004 Part 3's GSTIN/PAN-anchored merging) with a fraction of the conceptual and operational overhead of a "Layer."
- **Event sourcing / CQRS for the ledger, framed as required architecture.** RFC-004 Part 4 makes a genuinely elegant argument that double-entry accounting *is* event-sourced by nature — that's true as a conceptual observation, and it is a trap as an implementation mandate. Full event-sourcing (append-only log as sole source of truth, materialized views rebuilt from replay) is one of the most operationally expensive patterns in distributed systems: replay performance, snapshotting, eventual-consistency debugging, and a steep learning curve for anyone who hasn't run it in production before. A conventional table with a proper immutable `correction_events` / `journal_entries` audit table (append rows, never update the semantically-final ones, exactly matching the "reverse, don't edit" doctrine) delivers the actual requirement — immutability, auditability, bitemporal history — without the CQRS machinery. **This is premature optimization dressed up as domain-fidelity.**
- **A formal multi-agent Planner/Supervisor, before more than one or two agents exist.** RFC-003's whole multi-agent chapter (military command, air traffic control, delegation hierarchies) is answering a coordination problem that doesn't exist yet when there is effectively one extraction pipeline and one reconciliation engine. Building a generic delegation/supervisor framework for agents that don't yet exist is speculative infrastructure — the actual near-term need is "call the LLM, validate the output, let a human review it," which does not require a Planner/Supervisor abstraction to implement correctly.
- **A generic Connector Registry and shared retry/idempotency "framework," for one real connector.** Part 5.4's registry and shared-infrastructure framing is right in spirit for connector #5 through #20. For connector #2 (a second ERP), it is over-abstraction — the idempotency discipline already proven in the Tally push-log pattern should simply be copied and adapted for the next connector, not generalized into a registry-and-framework nobody has stress-tested against a second real integration yet.
- **A dedicated Evaluation Layer with five continuously-running measurement layers.** Layers 4 (drift monitoring via statistical process control) and 5 (human trust metrics with calibrated instrumentation) are genuinely good ideas for a mature platform with meaningful traffic. Building them now, before Layer 2's actual professionally-graded eval set has more than a handful of cases, is measuring a system that doesn't have enough throughput yet to produce a meaningful drift signal.
- **Federated learning, differential privacy, MCP exposure, enterprise SSO/SAML.** All correctly marked "delay" in Part 10/11 already — flagged here only to confirm the red-team review agrees these should stay out of scope, and to add: they should not even appear as named architectural placeholders that consume review-meeting time repeatedly. Cut them from active planning entirely until a specific deal or requirement forces the conversation.
- **The full digital-workforce roster (12 named virtual roles) as an architectural concern in RFC-005.** Virtual CEO Advisor and Virtual Treasury Analyst, specifically, are aspirational product concepts with no validated demand signal yet. Designing their "decision limits" and "KPIs" in an architecture document before a single client has asked for either is effort spent on a persona, not a system.

## R.3 Premature optimization

- **SLM strategy anywhere near this phase.** RFC-002's SLM chapter is intellectually correct and organizationally premature — "data-gated, not calendar-gated" is the right test, and the honest answer to whether the gate is currently open is *no*. Nobody should be evaluating LoRA/QLoRA tooling or model-hosting infrastructure until there's a specific task with thousands of verified corrections. This should not consume architecture bandwidth now.
- **Multi-database sprawl implied by Part 11's table** (relational + vector + eventual graph + eventual OLAP + eventual streaming). Even with every individual "delay until evidenced" caveat correctly attached, listing five storage systems in one table normalizes the idea that this is where the platform is headed soon. It isn't. PostgreSQL (plus pgvector when actually needed) should be treated as capable of carrying the *entire* platform for a multi-year stretch, not as "Phase 1's stopgap."
- **Confidence-vs-trust as two separately engineered, separately stored score fields (RFC-004 Part 5.1) at current volume.** Correct as an eventual data-quality discipline; premature as a "must be architected now" requirement when the review workspace already has a working accept/reject/correct flow. A single `status` + `reviewer_note` field captures what's actually needed today; splitting confidence and trust into independently-modeled, independently-consumed scores is optimization for a scale of automated-trust-based-routing decision-making the product doesn't make yet.

## R.4 Single points of failure — some real, some manufactured by the architecture itself

- **Real and worth fixing:** a single LLM vendor dependency for the entire Reasoning Layer, with no documented fallback path (flagged in Part 2.5 but not actually resolved — "at minimum a documented fallback routing path" is a sentence, not a mitigation). For a small team this doesn't need multi-vendor redundancy, but it does need a tested manual fallback runbook.
- **Real and worth fixing:** the single GSP partner for GST filing (Part 5.3) — an outage or contract issue there stops the highest-stakes workflow in the product. Worth knowing the GSP's own SLA and having a documented (not necessarily automated) secondary-GSP path before this becomes a live incident.
- **Manufactured by this architecture, not by the product's actual needs:** treating the Knowledge & Memory Layer as the mandatory dependency of nearly every other layer (Part 4.3's own "everything reads from or writes to it" observation) is true by construction *because this document designed it that way*, not because the current product requires that much central coupling. A simpler design where Document Intelligence, Validation, and the review workspace talk mostly to a normal database, with a much smaller "verified facts" table growing incrementally, would have fewer things depending on one conceptual mega-layer, and would be easier for a small team to reason about when something breaks at 11pm.

## R.5 AI hype without measurable value

- **Virtual CFO / Virtual CEO Advisor as "briefing functions."** RFC-003 Part 8's own honest admission — no clean ground truth, evaluation dominated by human-trust metrics that don't exist yet — is itself the tell that this is speculative. Nothing about this should be architected now; it should be a Phase 3+ idea revisited only if clients are explicitly asking for it.
- **The five-stage "layered OCR" pipeline's Stage 3 vision-model fallback**, built ahead of evidence that current document quality actually needs it. If the existing `pdfplumber`-based extraction already handles the large majority of real client documents (which the README suggests is true for the core GST/invoice workload), building a vision-model fallback path is solving a problem largely for a document class (handwritten notes, badly-photographed thermal receipts) that may be a small fraction of actual volume. Verify the failure-mode volume before building the fallback stage, not before.
- **"Confidence-based review routing" described as multi-signal, non-opaque, stage-attributed scoring (Part 3.1 Stage 5).** Elegant, and probably more machinery than is needed when the honest current requirement is "did the deterministic reconciliation pass or fail, and does the extraction confidence (one number) fall below a threshold." Multi-stage confidence attribution is a genuine improvement — later, once there's evidence a single blended score is causing misrouted reviews.

## R.6 Components that should be deleted from the near-term architecture entirely

- **Resource Manager** (Part 1.2/2 of the OS component list) — multi-tenant fair-scheduling infrastructure for a client base almost certainly small enough that a shared task queue with sane rate limits solves this without a dedicated component.
- **State Manager as a distinct component from the workflow engine.** RFC-003's own distinction (business-object state vs. workflow-step state) is real in theory; in practice, for the current scale, a `status` column on the relevant tables (invoice, filing, reconciliation) is the State Manager. It does not need a name, a diagram box, or a separate implementation effort.
- **Governance Layer as distinct from Policy Engine.** For a small team, "policy" is a config file or a small admin screen a human edits directly. Splitting "the rules" from "the UI to change the rules" into two named architectural layers is premature separation of concerns for an org this size.
- **A generic Tool Router abstraction**, for a system with one real tool-consuming surface (the extraction pipeline) and one real connector (Tally). Direct calls, with a thin adapter interface per connector, achieve the same replaceability RFC-003 wants without the indirection of a routing layer nobody yet needs to route between more than two things.

## R.7 Components that can genuinely wait 3–5 years

Dedicated graph database; full event-sourcing/CQRS; a durable-execution engine (Temporal-class); Kafka-class streaming; federated learning / differential privacy; SLM training and hosting infrastructure; formal multi-agent Planner/Supervisor; MCP-compatible API surface; enterprise SSO/SAML; cross-jurisdiction canonical-model extension; the full digital-workforce roster beyond whichever one or two roles a real client has actually asked for. This list is longer than RFC-005's own Part 10 phase-gating already implied, and that gap between "technically phase-gated to later" and "not even worth naming as a near-term architectural concept" is exactly what a red-team pass is for.

## R.8 Build vs. Buy mistakes in the original document

- **Building the connector-registry/shared-idempotency "framework" (Part 5.4)** ahead of a second connector, as already flagged in R.2 — this isn't really a build-vs-buy mistake so much as a build-too-early mistake; the "buy/open-source" alternative doesn't even apply, the correct answer is *don't build the generalized version yet, copy-paste-and-adapt instead.*
- **The instinct to avoid agent-orchestration frameworks entirely (RFC-002 Part 8, RFC-003 Part 9), reconfirmed uncritically in Part 11.** The reasoning (auditability, indirection) is sound for the core deterministic-guardrail loop. But for the genuinely exploratory, lower-stakes uses (an internal tool, a first draft of a Virtual-Advisor-style feature before it's trusted enough to touch real client data), a lightweight existing framework may be faster to prototype with than hand-rolled orchestration — RFC-005 should not have implied a blanket avoidance without that carve-out, which PHASE_1_5 itself actually included and this document dropped.
- **No real mistake found in the "never build OCR/foundation-models/spreadsheet-engine/BI-tool" verdicts** — those hold up under red-team scrutiny and should not be revised.

## R.9 Cost risks
Running a professionally-graded eval set means paying qualified CAs to grade cases on an ongoing basis — a real, recurring cash cost this document treats as an unquestioned strategic investment (RFC-002/003) without ever sizing it. At small scale, this cost is disproportionate to the number of production decisions it's currently protecting. Frontier-model inference cost for anything resembling continuous "digital workforce" reasoning (R.5) is a second, avoidable near-term cost if those roles aren't built yet. Running five-plus storage/infra systems "eventually" (R.3) is a cost risk mainly in the form of *premature commitment* — provisioning and operating infrastructure ahead of the load that justifies it is pure burn with no offsetting product value.

## R.10 Team capability risk — the one that matters most
Nearly everything in R.2–R.4 requires senior distributed-systems and data-platform experience to build *correctly* (event sourcing, sagas, entity resolution, knowledge graphs, differential privacy, multi-agent coordination). This document was written channeling Palantir/Stripe/Snowflake-caliber platform engineering organizations. If the actual AuditOS engineering capacity is a small team (plausibly one-to-a-few engineers, AI-assisted), the realistic outcome of pursuing this document literally is **half-built infrastructure that nobody on the team has the bandwidth to operate correctly, while the actual client-facing product — extraction accuracy, reconciliation correctness, connector coverage — stalls.** A wrong, over-ambitious architecture doesn't fail loudly; it fails by quietly consuming all available engineering time on plumbing while competitors who shipped a simpler system pull ahead on the thing that actually matters (RFC-001's own thesis): trust earned through correct, shipped, working product.

---

## R.11 Revised recommendations

The criticism above is valid, and it changes the recommendation, not just the tone. **Long-term doctrine from RFC-001–004 is not wrong and is not being reversed** — the moat is still the ontology, the correction loop, the deterministic-guardrail discipline, the compounding data asset. What was wrong was **presenting a decade's worth of eventual layers as if a small team should scaffold all of them now.** Revised guidance:

1. **Collapse Phase 1 to four things, not thirteen layers:** (a) the existing extraction + deterministic-validation pipeline, hardened and generalized, not re-platformed; (b) one `verified_knowledge` table with the versioning/provenance *fields* RFC-002 requires (effective-from/to, source, trust score, supersession pointer) — as columns on ordinary tables, not a distinct "Layer" with its own service boundary; (c) the Tally connector's idempotency pattern, copy-pasted (not generalized) for the next one or two connectors as they're actually built; (d) the correction-capture discipline (every human correction retained as an event, per RFC-004 Part 5.2) — this is the one piece of "architecture-sounding" infrastructure that genuinely must be right from day one, because it's the only thing this whole research program agrees cannot be retrofitted later without losing years of flywheel data.
2. **Delete from active planning, not just "phase-gate": Resource Manager, State Manager, Governance Layer, Tool Router, formal Planner/Supervisor, Connector Registry-as-framework, event sourcing/CQRS, dedicated graph database, Evaluation Layers 4–5, the full digital-workforce roster beyond one validated role.** These remain valid *long-term destinations*, described accurately in Parts 1–9 for when the team and the traffic justify them — but they should not appear on any near-term roadmap, sprint plan, or architecture-review agenda until a specific, evidenced trigger (not a calendar date) is hit. The trigger, restated concretely: a second real connector before generalizing the connector pattern; measurable drift or trust-metric noise before building Evaluation Layers 4–5; an actual client request before building any second digital-workforce role; genuine multi-hop relational query pain before a graph database.
3. **Reframe RFC-005's 13-layer stack as a *map of eventual destinations*, not a *build list*.** Its real value is Part 10.5's evolution test (does a new capability fit by extension, not redesign) — that test is worth keeping precisely *because* it lets the team build the collapsed four-thing Phase 1 above without accidentally painting themselves into a corner, while still not building the other nine layers speculatively. The architecture's job at this team size is to **not block the simple version**, not to **mandate the complex one**.
4. **On multi-vendor/GSP redundancy (R.4):** upgrade from "documented fallback" to an actual tested runbook (a real, once-verified manual procedure) for both the LLM-vendor and GSP single points of failure — this is cheap to do now and expensive to improvise during an actual outage, unlike everything else on this list.
5. **On agent frameworks (R.8):** narrow the "avoid frameworks" doctrine correctly — avoid them for the deterministic-guardrail core loop touching real client data; allow a lightweight existing framework for low-stakes prototyping of anything not yet trusted with production financial actions.

**The net effect of this red-team pass: RFC-005's long-run architecture is retained as written, but reclassified — almost everything in Parts 2 and 9 beyond the four items in R.11.1 is downgraded from "architecture to build" to "vocabulary to recognize the destination by, when the evidence arrives."** That distinction, not any single layer's correctness, was the actual gap in the original document.

---

# CLOSING NOTE

This architecture is the direct, traceable implementation of RFC-001 through RFC-004's doctrine — every layer boundary, every build/buy verdict, and every phasing decision above cites the specific prior finding it implements, and Part 0's single flagged ambiguity was resolved without reversing any doctrine. The Architecture Risks & Red Team Review above is now part of this RFC's accepted content, not a separate document: **Part 10 (Platform Evolution) and Part 11 (Build/Buy table) should be read through R.11's revised recommendations, not independently of them** — where the two disagree on near-term scope, R.11 governs. The evolution test in Part 10.5 is the standing check against which every future capability, agent, connector, or domain expansion should be measured before implementation begins: it should fit this architecture by configuration and extension, not by redesign — and per R.11, "fit by extension" for the next 12–18 months means extending the four-item collapsed Phase 1, not the full 13-layer stack. RFC-005 marks the beginning of the Architecture Program; the next appropriate deliverable is a concrete, small-team-sized implementation plan for the collapsed Phase 1 (R.11.1), starting with the human-approval timeout/escalation gap flagged in Part 10.1, not a further research document and not a build-out of the layers this review just deprioritized.
