# ENGINEERING PRINCIPLES
## AuditOS Engineering Doctrine

**Status: Living document. Governs day-to-day engineering decisions. Subordinate to RFC-001–005 on strategy; authoritative on execution.**

These are not research findings — they are working rules for a small team shipping a regulated financial product. Each one exists to prevent a specific, real failure mode, not to sound complete.

## Deterministic before AI
1. Anything with exactly one correct answer (tax math, debit/credit balance, statutory apportionment) is plain, tested code — never a model call, never negotiable under deadline pressure.
2. An LLM call proposes; a deterministic check disposes. If a PR lets an LLM output reach a client-facing number without a deterministic check in between, it does not merge.
3. If you catch yourself writing a prompt to do arithmetic or compare two ledger values, stop — that's a bug, not a feature.

## Build moats, buy commodities
4. Before writing a new component, ask: does this make our data/ontology/eval-set more valuable, or is it infrastructure a funded competitor could stand up in a weekend? If the latter, buy or use open source.
5. Never build: OCR from scratch, a spreadsheet engine, a BI tool, a foundation model, a workflow engine before Celery is actually insufficient, a graph database before relational joins actually hurt.
6. Always build and own: the canonical schema, the connector to each ERP we actually support, the correction-capture pipeline, the eval set.

## Every subsystem replaceable
7. No component assumes a specific LLM vendor will exist next quarter. If swapping models requires touching more than one file, that's a defect.
8. Connectors talk to the rest of the system through the same four operations (fetch, push, resolve, health) — copy the pattern, don't build a framework until there's a third connector proving the pattern needs one.
9. Prefer a boring, swappable dependency over a clever, sticky one, even if the clever one saves a week now.

## Every action observable
10. If an action changes client data or triggers an external write, it logs who, what, when, on what evidence, before it ships — not "we'll add logging later."
11. A bug that can't be explained from logs alone is treated as a logging bug first, a code bug second.

## Every API versioned
12. Breaking an existing API contract without a version bump and a deprecation window is a blocking review comment, not a style nitpick.
13. Internal APIs between our own layers get the same discipline as external ones — "it's just us calling it" is not an exemption.

## Every connector follows one interface
14. Fetch, Push, Resolve, Health — nothing else lives in a connector. Reconciliation logic, interpretation, or business rules found inside a connector get moved out in the same PR that's touching that code, not filed as a follow-up ticket.

## Every workflow idempotent
15. Any step that touches an external system (ERP, GSTN, email, Slack) must be safely retryable. If you can't answer "what happens if this runs twice," it isn't done.
16. Idempotency keys are added when the step is written, never bolted on after the first duplicate-voucher incident.

## Every AI output explainable
17. A model's output that a CA reviews must show its source: which document region, which field, which rule. "The AI said so" is never an acceptable answer to "why."
18. Confidence and correctness are different things — never present a model's self-reported confidence as if it were a correctness guarantee.

## Every model replaceable
19. Prompts, model choice, and routing logic live in one place, not scattered across the codebase — swapping a model or a prompt should touch one module.
20. New frontier-model releases are evaluated against our own eval set before being adopted, never adopted because a benchmark leaderboard changed.

## Every customer isolated
21. Tenant scoping is checked at the data-access layer for every new endpoint, every time, even when "obviously" the caller is already scoped correctly upstream.
22. A cross-tenant data leak is a Sev-1 regardless of size, blast radius, or whether a client noticed.

## Knowledge compounds
23. Every human correction is captured as a retained, timestamped event — never a silent overwrite. If a migration or refactor would lose correction history, it doesn't ship as written.
24. Nothing is promoted from "the AI proposed this" to "the system trusts this" without a human verification step logged against it.

## Evaluation never stops
25. A change to extraction, validation, or reconciliation logic runs against the regression suite before merge — no exceptions for "small" changes, which are exactly the ones that quietly break an edge case.
26. If we can't currently measure whether a change made the system more accurate, that's a gap to close before shipping more features that depend on accuracy, not after.

## Security by default
27. Secrets never live in code, config committed to the repo, or the knowledge store — full stop.
28. New dependencies are checked for known vulnerabilities before being added, not after a security review flags them months later.

## Testing before deployment
29. Nothing reaches production without passing CI. CI is red means nothing merges, no matter who's waiting on it.
30. A bug fix ships with a regression test that would have caught it, in the same PR.

## Documentation is code
31. A connector, a rule set, or an API without a short README explaining what it does and why is not done, even if it works.
32. Documentation that contradicts the code is worse than no documentation — fix or delete it in the same PR that changes the behavior it describes.

## Prefer deletion over complexity
33. Before adding an abstraction, try solving the problem without it. If the direct solution is only slightly more repetitive, ship the direct solution.
34. Dead code, unused feature flags, and speculative "might need this later" scaffolding get deleted on sight, not preserved "just in case."
35. If a proposed component only serves a hypothetical future need with no current evidence, the default answer is no.

## Human override for consequential actions
36. Anything irreversible or externally visible (a filing, an ERP write, a message sent to a client) requires an explicit human approval step, permanently — this is not a maturity stage we graduate out of as models improve.
37. Every automated action has a "who approved this and when" answer, retrievable without archaeology.

## Team and process
38. A three-to-five-person team does not run five databases, three orchestration frameworks, and a microservices mesh. One well-understood system beats three partially-understood ones.
39. Estimate in terms of "can this be built and maintained by the people we actually have," not "what would a well-funded platform team build."
40. A design that can't be explained in a five-minute conversation to the rest of the team is too complicated for this team's current size.
41. Code review exists to catch correctness and scope creep, not to bikeshed style — automate style enforcement so humans don't have to argue about it.
42. If two engineers disagree on an architectural call for more than one meeting, write it down as an ADR and move on — indecision is more expensive than a wrong-but-documented decision.

## Cost and operational discipline
43. Every new piece of infrastructure has an named owner and a documented reason it's running, reviewed quarterly — infrastructure with no owner gets shut down.
44. LLM/API cost per workload is tracked, not assumed — if a cheaper model or a deterministic rule can do the job, use it.
45. Provisioning ahead of evidenced load is treated as a cost risk, not a readiness win.

## Shipping discipline
46. A feature isn't done when the code works — it's done when it's tested, logged, documented, and a real client's data has been run through it without a reviewer finding a surprise.
47. Ship the narrow, correct version before the broad, ambitious one — one ERP done right beats five ERPs done approximately.
48. If a sprint's plan includes building a "platform" or a "framework" for a capability with fewer than two real, current consumers, cut it and build the concrete version instead.

## Humility and revision
49. Every principle in this document is subject to revision when it's shown to be wrong for our actual scale — but revision requires a specific incident or piece of evidence, not just a preference.
50. When in doubt, re-read RFC-005's Red Team Review before adding complexity — if a proposal wouldn't have survived that review, it doesn't survive this one either.
