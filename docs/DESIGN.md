# Research Synthesis: AuditOS Brand & UX Direction

**Method:** Codebase audit + persistent project-history review + competitive research
**Participants:** N/A — no live user interviews conducted this pass
**Date:** 2026-08-01
**Researcher:** Aeronive Labs Brand Studio (Claude)

> **Read this caveat before acting on anything below.** This synthesis is grounded in
> (a) direct review of the running frontend/backend, (b) this project's persistent memory
> spanning several past sessions (Tally connector build, GSTR-2B workflow spec, Purchase-side
> extraction research, expense-report mapping), and (c) competitive research on aiAccountant.com,
> Sarvam AI, and YC-funded bookkeeping startups. **It is not live customer research.** Treat the
> segment split, the WhatsApp/payroll bet, and the priority order as informed hypotheses to
> validate with real firm and business users before committing engineering time — especially
> anything in the "later phase" bucket.

Full visual presentations live at:
- **Concept 01 — Brand Revamp Proposal** (positioning, palette, logo, type, applied example)
- **UX Audit & Expansion Roadmap** (font system, audit findings, staged features, proposed IA, platform bet)

This document is the text-only synthesis of both, structured for reference and sign-off.

---

## Executive Summary

AuditOS's current identity (blue shield mark, Inter-on-white, flat 9-item sidebar) reads as generic
SaaS and gives no visual signal of what the product actually does. A ledger-and-tick visual system —
grounded in the auditor's own tick-mark gesture rather than a decorative shield — gives the brand
something ownable. Separately, the navigation has not kept pace with what's already built: a
fully-tested Tally integration has no first-class nav entry, three pages maintain three disconnected
period pickers, and two structurally identical review flows sit as unrelated sidebar items. Both
problems compound with the stated future direction — onboarding businesses directly over WhatsApp,
with Purchase Orders and Payroll as new compliance domains — which is a second product surface
layered on the same backend, not a bigger version of today's firm-facing dashboard.

---

## Key Themes

### Theme 1: The visual identity undercuts a differentiated product
**Prevalence:** Every screen in the app (9 pages audited)
**Summary:** The current shield-icon + `#2563eb` blue + Inter combination is visually indistinguishable
from most SaaS dashboards built in the last decade, and carries no reference to accounting, GST, or
the CA profession.
**Supporting Evidence:**
- `frontend/src/components/Sidebar.tsx` — shield icon in a rounded blue square, identical grammar to
  generic "security/compliance" marks industry-wide
- `frontend/src/app/globals.css` (pre-revamp) — `--accent: #2563eb`, the same blue used across
  countless YC fintechs and Stripe's own documentation
- Competitive check (aiAccountant.com, Puzzle, Digits, Campfire) confirmed no competitor is using a
  ledger/tick-mark visual language — the territory is open
**Implication:** A mark built from the auditor's actual tick-and-tie gesture, in a palette drawn from
ruled ledger paper and stamp ink, is both more distinctive and more honest about what the product does.

### Theme 2: Navigation hasn't kept pace with what's already built
**Prevalence:** 6 concrete findings across the current 9-page IA
**Summary:** Features shipped in separate sessions were each given their own flat sidebar slot or, in
one major case, no slot at all — the structure was never revisited as a whole.
**Supporting Evidence:**
- `services/tally_connector.py` + `invoice-extractor/page.tsx` — a live-tested, idempotent Tally
  read/write integration exists only as a modal one click inside the Extractor's export step
- `google-drive-sync`, `sales-period-review`, `purchase-gstr2b-review` — three independent period
  pickers, no shared "current period" state
- `sales-period-review/page.tsx` and `purchase-gstr2b-review/page.tsx` — structurally identical
  generate → review → approve workflow, filed as two unrelated sidebar items
- `document-utilities/page.tsx` — 5 unrelated PDF tools sharing one page purely because they're all
  "PDF-adjacent"
- No pending-work surface anywhere outside `AuthGuard.tsx`'s single "resume last session" toast
- `models.py` — `tenant_id` on every table (genuinely multi-tenant), yet no client/company switcher
  exists in the UI
**Implication:** A grouped IA (Import / Review & File / Reconcile / Tools / Firm) with a top-bar
period and client switcher resolves all six without touching page-level functionality.

### Theme 3: The near-term roadmap already assumes structure the IA doesn't have yet
**Prevalence:** 6 features pulled from confirmed project history
**Summary:** Purchase-side extraction, the Tally local bridge agent, GSTR-2B auto-nudges, expense-report
ingestion, the correction-feedback loop, and role management are all either backend-complete or
explicitly next-phase — none have a planned home in the current sidebar.
**Supporting Evidence:**
- `project_nanonets_purchase_side.md` — Purchase-side IDP evaluation deferred to Phase 0b, confidence
  scores flagged as "a natural fit for a human-review gate"
- `project_tally_connector.md` — local bridge agent explicitly deferred "until cloud deployment is
  real"; the DigitalOcean migration this session made that condition true
- `project_gstr2b_client_trigger.md` — confirmed auto-email rules for at-risk ITC, monthly re-trigger
  cycle, no audit-trail surface built yet
- `project_er_category_ledger_mapping.md` — expense-report-to-ledger mapping currently done by hand
  every month, same shape as an ingestion pipeline
- `project_active_work.md` — "Remaining across all phases" list includes role management, explicitly
  unscheduled
**Implication:** The near-term IA regroup should reserve slots for these now (a placeholder "Expense
Reports" row, "Tally Sync" promoted out of its modal) rather than being re-architected when each ships.

### Theme 4: The stated future is a second product surface, not a bigger dashboard
**Prevalence:** New input this session — WhatsApp onboarding, local OCR, Purchase Orders, Payroll
**Summary:** Self-serve business onboarding inverts the volume assumption the current extraction
pipeline is built on (a firm processes hundreds of documents; self-serve implies thousands of
businesses sending a handful each), and introduces an entirely new compliance domain (payroll) no
competitor researched touches.
**Supporting Evidence:**
- Current extraction pipeline (`core/extraction/pipeline.py`) runs a full cloud LLM pass per document —
  affordable at firm scale, not at WhatsApp-onboarding scale
- Competitive research: none of Puzzle, Digits, Campfire, Last Accounting Company, Rational, or
  ProcIndex (all YC-funded bookkeeping/accounting agents) address Indian statutory payroll (TDS 192,
  PF/ESI/PT, Form 16/24Q)
- `models.py` tenant model is already structurally capable of supporting a business-operated workspace
  alongside a firm-operated one — the fork is a front-door/onboarding-flow difference, not a schema change
**Implication:** Treat this as a sequenced Phase 2/3 bet — a local-OCR-first WhatsApp intake flow, then
Purchase Orders (which gives Purchase-side extraction something to reconcile against beyond GSTR-2B),
then Payroll last, given its scope is comparable to the entire existing GST/audit product.

---

## Insights → Opportunities

| Insight | Opportunity | Impact | Effort |
|---|---|---|---|
| Shield + generic blue signals nothing product-specific | Ledger-and-tick mark + ink/paper/tick/agent/seal palette | High | Medium |
| Tally push is fully built but undiscoverable | Promote to a first-class "Tally Sync" nav item under Reconcile | High | Low |
| Three period pickers don't share state | Single top-bar period switcher, all pages read from it | High | Medium |
| Sales Review / GSTR-2B Review are one workflow filed twice | Merge into one Review Queue with a type filter | Medium | Medium |
| No pending-work surface outside one resume toast | Badge counts on grouped nav items (Import, Review & File) | Medium | Low |
| Multi-tenant schema, no client switcher in UI | Top-bar client/company switcher | High | Medium |
| Doc Utilities is an unrelated 5-tool grab-bag | Leave grouped under "Tools" — lowest-priority fix, not urgent | Low | Low |
| WhatsApp-scale onboarding breaks the per-document cloud-LLM cost model | Local OCR first pass, cloud escalation only on low confidence | High | High |
| No competitor covers Indian statutory payroll | Payroll module — the actual basis for a "one-stop compliance" claim | High | High |
| Purchase-side extraction has nothing to reconcile against but GSTR-2B | Purchase Orders module — enables real 3-way match | Medium | High |

---

## User Segments Identified

| Segment | Characteristics | Needs | Notes |
|---|---|---|---|
| **Firm-operated** (today's whole product) | CA firm staff, log in via web, manage multiple client workspaces | Fast period close, review/approve gates, Tally push, audit trail | Existing IA regroup (Section 04 of the roadmap doc) serves this segment directly |
| **Business-operated** (stated future) | Business owner, likely no accounting background, primarily on WhatsApp | Zero-friction capture (photo in, confirmation back), minimal web dashboard use, trust that data isn't blindly sent to the cloud | Requires the WhatsApp + local-OCR intake flow (Section 05); web dashboard becomes an exception-handling surface, not the primary interface |
| **Hybrid** (a firm overseeing business-operated clients) | Same tenant, two front doors | Firm needs visibility into what a business's WhatsApp channel captured, without operating it directly | Not yet designed — flagged as an open question below |

**Refinement from the mockup pass:** "Business-operated" is not one shape. A solo owner (WhatsApp-first,
near-zero web usage) and a company with a 30-40 person internal finance department are both single-entity
(no client switcher needed) but need almost opposite dashboards — the large team needs the same
workload/approval infrastructure Firm mode needs, just scoped to one company instead of many clients. The
real architecture is two independent axes, not three fixed products:

- **Entity scope** — one company vs. many → determines whether the top bar shows a client switcher
- **Operator scope** — solo vs. large internal team → determines whether the workload/role-distribution
  view and a Department switcher turn on

Firm mode = many entities. Large-team mode = one entity + many operators. Solo mode = one entity + one
operator. Confirmed working in an interactive mockup (persona toggle on the Dashboard, top bar chrome
swaps with it, not just page-body copy).

---

## Confirmed Decision: Role Ladder (2026-08-01)

Existing role strings scattered across the codebase before this pass: `owner`, `auditor`, `developer`,
`accountant`, `hr`, `ca`, `client`, `other` — eight inconsistent strings, `auditor`/`ca` overlapping,
`other` a catch-all, `accountant` carrying no seniority distinction. Collapsed to seven, confirmed:

| Role | Scope |
|---|---|
| **Owner** | Firm/business owner — full access, billing, firm settings |
| **Dedicated CA** | Sign-off authority — final approval gate (collapses old `auditor`/`ca`) |
| **Senior Accountant** | Reviews junior work, escalates to CA |
| **Accountant** | First-pass processing — ingestion, data entry, initial review |
| **HR** | **Payroll and statutory compliance only** — not a general people-ops role. Confirmed scope: PF/ESI/PT filings, salary-run compliance. Does not extend to hiring, leave management, or other HR functions outside the compliance surface AuditOS covers. |
| **Client** | Read-only/limited view — a business owner when a firm manages them (Hybrid segment) |
| **Developer** | Internal/admin, full technical access |

`Owner`, `Client`, and `Developer` don't carry day-to-day casework and are excluded from workload/role-
distribution counts (e.g. "38 active" on the Large-Team dashboard covers only Dedicated CA / Senior
Accountant / Accountant / HR). Department (Accounts Payable / Payroll / Compliance-Sign-off) is a
separate, orthogonal axis — a filter on *what work*, not *who's doing it* — confirmed by wiring a working
Department filter against the role table in the mockup rather than leaving it decorative.

---

## Recommendations

1. **High priority — approve or revise the brand direction (Concept 01) before any mockup work.**
   Every later recommendation inherits the palette, type, and logo decided here; revising it after
   mockups exist costs more than revising it now.
2. **High priority — ship the near-term IA regroup (Import / Review & File / Reconcile / Tools / Firm)
   independent of the platform bet.** It resolves six real findings today and doesn't require WhatsApp,
   Payroll, or Purchase Orders to exist first.
3. **High priority — promote Tally Sync out of its modal.** Lowest effort, highest-impact single fix on
   the list — a fully-built feature currently has zero discoverability.
4. **Medium priority — build the top-bar period and client switchers before the next new page ships.**
   Every additional page built against today's per-page period picker pattern is more work to unwind later.
5. **Medium priority — validate the WhatsApp/local-OCR/Payroll bet with 3-5 target business owners
   before deep investment.** This synthesis has zero direct input from that segment; the whole Section 05
   thesis is inference from competitive gaps and architecture reasoning, not confirmed demand.
6. **Lower priority — merge Sales Review and GSTR-2B Review into one Review Queue.** Real duplication,
   but lower urgency than the Tally/period-switcher fixes since both flows work correctly today.

---

## Questions for Further Research

- **Local OCR model choice** — which on-device/edge OCR engine actually hits acceptable accuracy on
  phone-camera photos of Indian invoices (lighting, skew, handwriting) at a cost that clears the
  WhatsApp-scale economics this bet depends on? Not yet evaluated.
- **WhatsApp Business API vendor** — official Meta Cloud API vs. a BSP (Gupshup, Interakt, etc.)? Cost,
  approval time, and template-message rules differ meaningfully; not yet scoped.
- **Payroll compliance depth** — is the intent full payroll processing (bank file generation, Form 16
  issuance) or compliance-only (TDS/PF/ESI calculation and filing, no disbursement)? Very different
  build sizes.
- **Hybrid segment UX** — when a firm oversees a business-operated client, what does the firm actually
  see? Full WhatsApp transcript access, or just the same Review Queue with a different intake source?
  Not designed yet.
- **Pricing/packaging implication** — does self-serve business onboarding compete with or route through
  existing CA firm customers? Affects whether WhatsApp intake should default to "notify the firm" or
  "handle independently."

---

## Methodology Notes

This synthesis draws on three sources, each with different reliability:

1. **Direct codebase inspection** (high confidence) — read every page under `frontend/src/app/`, the
   relevant backend models and routes, and ran the actual build (`npm run build`) to confirm the current
   state described above is real, not assumed.
2. **Persistent project memory** (medium-high confidence, time-decayed) — memory files dated 9-32 days
   old at time of writing describe past build sessions (Tally connector, GSTR-2B workflow, Nanonets
   research, expense-report mapping). Each carries its own "point-in-time, verify before asserting"
   caveat; treated here as directional evidence of what's staged, not as current live state.
3. **Competitive research** (medium confidence) — web search + limited fetch access (Sarvam.ai blocked
   direct fetch; findings on aiAccountant.com and Sarvam are from search-result summaries, not full
   site audits). YC bookkeeping-startup positioning (Puzzle, Digits, Campfire, LAC, Rational, ProcIndex)
   is from search summaries as of August 2026, not hands-on product trials.

**No live interviews, surveys, or usability tests were conducted for this pass.** The segment split and
the entire Theme 4 / Section 05 platform bet are architecture-and-market inference, explicitly flagged
in Recommendation 5 as needing direct validation before committing build time.
