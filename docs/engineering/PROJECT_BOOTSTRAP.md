# PROJECT BOOTSTRAP
## The First 100 Engineering Tasks, In Order

**Assumes engineering starts tomorrow morning. Derived directly from ENGINEERING_EXECUTION_BLUEPRINT.md's 30-day priorities (Programs 4, 5, 3, 8, 6, in that dependency order) plus the foundational setup those programs need to land on. No code. No placeholders. Execution only.**

Ordering logic: foundation and repo hygiene first (so everything after has somewhere correct to live), then Program 4 (correction capture — the one thing that can't be retrofitted, per RFC-004's final synthesis), then Program 3 (connector idempotency — small, contained, unblocks Program 5), then Program 5 (workflow approval gates — the flagged RFC-005 gap), then Program 8 (CI/CD made real, not aspirational), then Program 6 (golden dataset and regression gating, which depends on CI existing), then Program 2 (rule versioning), then Program 1 (extraction generalization — largest, so scheduled once everything it depends on for safe iteration is in place), then Program 7 (tenant-isolation checklist enforcement, threaded through everything above), then the four required checkpoint tasks from the Red Team review that must not be forgotten.

---

### Foundation & Repo Hygiene (1–12)

1. Create `/docs/rfc` and move RFC-001 through RFC-005 into it.
2. Create `/docs/adr` and write ADR-001 (OCR), ADR-005 (Workflow), ADR-008 (Observability), ADR-009 (Security), and ADR-010 (Multi-tenancy) as five individual files, using the decisions already recorded in ENGINEERING_EXECUTION_BLUEPRINT.md Part 4.
3. Write one consolidated `ADR-00X-deferred-infrastructure.md` covering the Ontology, Connector Registry, Evaluation Layers 3–5, and SLM decisions and their review triggers, per the Red Team's ADR-consolidation revision.
4. Create `/docs/eval`, `/docs/connectors`, and `/docs/runbooks` folders, each with a one-line README stating its purpose.
5. Confirm `/benchmarks` exists as a top-level folder for golden-set fixtures, separate from application code.
6. Audit the current CI configuration and write down, in one page, exactly what it runs today and what it does not.
7. Confirm `main` is the only long-lived branch; delete or archive any stale long-lived branches found.
8. Set up branch-protection so `main` cannot be merged into without a passing CI run and at least one review.
9. Add or confirm an automated linter/formatter runs in CI, so code review time isn't spent on style.
10. Write the two-tier Definition of Done into `/docs` — "consequential PR" checklist (touches validation, execution, or tenant-scoped data) vs. "low-stakes PR" fast path — per the Red Team's productivity-risk revision.
11. Write the runbook stub for LLM-vendor fallback (manual procedure, not automated) under `/docs/runbooks`.
12. Write the runbook stub for GSP-provider fallback under `/docs/runbooks`.

### Program 4 — Correction & Knowledge Capture (13–30)

13. Inventory every accept/reject/correct action currently possible in the review workspace UI.
14. Design the `correction_events` schema: record ID, tenant ID, actor, timestamp, field changed, prior value, new value, evidence pointer, effective-from date.
15. Add a `trust_score` and `supersession_pointer` field to the schema design, per RFC-002's versioning doctrine.
16. Review the schema design against ADR-003 to confirm it captures exactly what's needed and nothing more (no premature promotion/SLM fields).
17. Write the migration adding the `correction_events` table, additive only, no destructive changes to existing tables.
18. Wire the review workspace's "accept" action to write a correction event.
19. Wire the review workspace's "reject" action to write a correction event.
20. Wire the review workspace's "manual correct" action to write a correction event, including the prior and new value.
21. Confirm no code path in the review workspace can modify a reviewed field without going through the correction-event write path.
22. Add a test that attempts to bypass correction-event capture and confirms it's structurally impossible, not just discouraged.
23. Add supersession-pointer logic so a corrected value's prior state remains queryable, never overwritten.
24. Write a test that makes multiple corrections to the same record and confirms full history is reconstructible.
25. Add a simple internal query/report showing correction-event volume per day, per tenant.
26. Confirm tenant isolation on the `correction_events` table specifically (a cross-tenant query must be structurally impossible, not just unlikely).
27. Deploy the correction-capture change to production.
28. Verify, on real production traffic, that 100% of review-workspace corrections are being captured as events.
29. Document the `correction_events` schema and its fields in `/docs/eval`.
30. Mark Program 4's 30-day deliverable complete and note the verified capture rate.

### Program 3 — Connector Idempotency Hardening (31–42)

31. List every distinct write path the Tally connector currently performs (voucher push, ledger auto-creation, Credit Note, Debit Note).
32. Confirm which of these write paths are currently covered by the existing `TallyPushLog` idempotency pattern.
33. Identify the write paths not yet covered.
34. Extend the idempotency log to cover ledger auto-creation.
35. Extend the idempotency log to cover Credit Note pushes, if not already covered.
36. Extend the idempotency log to cover Debit Note pushes, if not already covered.
37. Write a test that deliberately re-runs each write path twice in a test environment and confirms no duplication for any of them.
38. Fix any write path that fails the duplication test.
39. Deploy the hardened idempotency coverage to production.
40. Write the "how to build a connector" one-pager describing Fetch/Push/Resolve/Health, explicitly noting no registry/framework exists yet and none should be built until a second connector is real.
41. Place the one-pager in `/docs/connectors`.
42. Mark Program 3's 30-day deliverable complete.

### Program 5 — Workflow Approval Gates (43–58)

43. List every current workflow step that waits on a human approval.
44. For each one, confirm whether a timeout currently exists — expect the answer to be no, per the flagged RFC-005 gap.
45. Design the approval-gate step type: configurable timeout duration, configurable escalation target, per workflow type.
46. Decide the default timeout and escalation target for the GST-filing approval step specifically, since it's the highest-stakes case.
47. Decide the default timeout and escalation target for the ERP-push approval step.
48. Implement the timeout mechanism on top of the existing Celery-based workflow steps — no new workflow engine.
49. Implement the escalation action (alert the configured target) when a timeout fires.
50. Write a test that simulates a stale, unactioned approval and confirms escalation fires correctly.
51. Apply the approval-gate step type to the GST-filing workflow.
52. Apply the approval-gate step type to the ERP-push workflow.
53. Apply the approval-gate step type to any other existing consequential-action workflow identified in task 43.
54. Confirm every workflow's state survives a mid-flight restart (verify existing Celery + DB-backed state actually holds, don't assume).
55. Create the shared exception-queue table (or confirm one exists) that a stalled/failed workflow step routes into.
56. Wire a review surface (even a minimal one) for a human to see and act on the exception queue.
57. Deploy the approval-gate timeout/escalation change to production.
58. Mark Program 5's 30-day deliverable complete.

### Program 8 — CI/CD Made Real (59–68)

59. Confirm the CI pipeline actually blocks merge on failure — test this deliberately with a known-failing PR.
60. Add a required check that Program 4's correction-event capture test (task 22) runs on every relevant PR.
61. Add a required check that Program 3's idempotency tests (task 37) run on every relevant PR.
62. Add a required check that Program 5's approval-timeout test (task 50) runs on every relevant PR.
63. Add tenant-isolation test cases (attempt cross-tenant access, confirm rejection) for every existing tenant-scoped endpoint.
64. Wire the tenant-isolation tests into CI as a required check.
65. Confirm CI runtime is fast enough not to become a team bottleneck; if not, parallelize or trim before proceeding.
66. Set up a basic PR template referencing the two-tier Definition of Done from task 10.
67. Confirm deploy-off-`main` works end to end for both backend and frontend.
68. Mark the CI/CD baseline complete.

### Program 6 — Golden Dataset & Regression Suite (69–80)

69. Identify a representative set of already-processed, already-corrected real client documents to seed the golden set.
70. Anonymize/handle any sensitive fields in the seed set appropriately before it's used as a shared test fixture.
71. Store the seed set in `/benchmarks`, versioned.
72. Write the regression harness that runs extraction against the golden set and compares output to expected values.
73. Write the regression harness that runs validation/reconciliation against the golden set.
74. Wire both harnesses into CI as a required check for PRs touching extraction, validation, or reconciliation code.
75. Deliberately introduce a known regression in a test branch and confirm CI catches it.
76. Set up a simple, versioned pass-rate tracking mechanism (a dashboard or even a tracked log) for the golden set.
77. Design the monthly CA-grading process: how a sample is selected, how grading is recorded, who is responsible.
78. Cap the CA-grading time commitment explicitly (per the Red Team's staffing revision) and get sign-off from whoever's time it consumes.
79. Run the first monthly CA-graded batch and record the result.
80. Mark Program 6's 30-day deliverable (golden set bootstrapped, regression suite live, first graded batch complete) done.

### Program 2 — Rule Versioning (81–88)

81. List every rule currently in the 8-stage reconciliation engine.
82. Design the effective-from/effective-to schema addition for rule definitions.
83. Write the migration adding versioning fields to rule definitions, additive only.
84. Backfill existing rules with a sensible effective-from date (their known or assumed introduction date).
85. Write a test that replays a past reconciliation and confirms it reproduces the original result under the rule version active at that time.
86. Write and merge the "how to add a new rule" pattern document.
87. Apply the pattern to one real new or upcoming rule change, proving it end to end.
88. Mark Program 2's versioning deliverable complete.

### Program 1 — Extraction Generalization (89–96)

89. Identify a second real client or document set to generalize the extraction pipeline against, beyond the current single-client shape.
90. Parameterize the extraction pipeline by document-type/template family rather than hardcoding the current client's shape.
91. Run the golden-set regression suite (task 74) against both the original and the new generalization target before merging any change.
92. Implement the single blended confidence score for review routing, replacing any ad hoc per-field signal handling.
93. Compare routing decisions under the new confidence score against actual reviewer override rates; adjust the threshold if overrides cluster unexpectedly.
94. Confirm whether real Hindi or mixed-language document volume actually exists in current or near-term client data before committing further work.
95. If task 94 confirms material volume, scope the multilingual field-mapping work as its own follow-on task set; if not, explicitly log it as deferred and revisit at the 6-month checkpoint, not silently dropped.
96. Deploy the generalized extraction pipeline to production for the second client/document set.

### Program 7 — Tenant Isolation Checklist Enforcement (97–98)

97. Add the tenant-isolation review question ("does this PR correctly scope every new query/write to the acting tenant?") to the PR template from task 66, required for every consequential PR.
98. Do a one-time audit pass of every endpoint touched by tasks 13–96 above specifically for tenant-isolation correctness, closing any gap found immediately rather than filing it for later.

### Closing Checkpoints (99–100)

99. Schedule the 90-day roadmap checkpoint (per ENGINEERING_EXECUTION_BLUEPRINT.md Part 9) and the staffing-map exercise (per the Red Team's hiring-risk revision) — confirm no single engineer is listed as owner on more than roughly three concurrently-active epics.
100. Schedule the first quarterly cost-review checkpoint (LLM/API spend per workload, per Engineering Principle #44) and the first roadmap re-prune review (fold any Program with zero active epics into an adjacent one, per the Red Team's maintainability revision).

---

**What is not on this list, deliberately:** anything from Program 9 (Digital Workforce) or Program 10 (Ontology/Company Brain graph), any connector-registry/framework work, any SLM/fine-tuning work, any dedicated durable-execution engine adoption, any Evaluation Layer 3–5 build-out. These remain valid future destinations per RFC-005 and the Blueprint's ADRs, gated by their stated review triggers — not by task 101.
