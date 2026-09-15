# Definition of Done

Two tiers, per `ENGINEERING_EXECUTION_BLUEPRINT.md`'s Red Team Review (Part 10, developer-productivity finding): the full checklist applies to consequential changes; low-stakes changes get a fast path. Applying the full checklist uniformly to every PR either slows the team to a crawl or trains people to skip it — neither is acceptable, so the distinction is deliberate, not a shortcut.

## Is this PR "consequential"?

Yes, if it touches **any** of:
- `backend/core/reconciliation/`, `backend/core/validation/`, or any other deterministic rule-execution code
- `backend/services/tally_connector.py` or any other Execution-Substrate-style write path to an external system
- Tenant-scoped data access (a new or changed query/endpoint touching tenant-owned rows)
- Authentication, authorization, or `require_same_tenant`-style isolation checks
- Correction/audit-trail tables (`UserAnnotation`, `ObservabilityLog`) or anything writing to them
- Database schema (new/changed columns or tables)

If none of the above apply (UI copy, log message wording, a comment, a doc fix, a test-only change with no production code touched) — use the **low-stakes fast path**.

## Full checklist (consequential PRs)

- [ ] Reviewed existing implementation before adding new code — reused/extended rather than duplicated where something already existed
- [ ] Deterministic logic stays deterministic — no LLM/probabilistic shortcut introduced into rule-execution code
- [ ] Tenant isolation checked for every new or changed query/write ("does this correctly scope to the acting tenant?")
- [ ] Tests added or updated, and they actually fail without the fix (not just pass alongside it)
- [ ] Full regression suite run locally and green (`python backend/tests/regression/run_regression.py`)
- [ ] Any new external-system write path is idempotent
- [ ] Any new consequential/irreversible action has a human-approval gate — not automated end-to-end
- [ ] No secrets, credentials, or real client/PII data committed
- [ ] Additive schema changes only (or a clearly justified, called-out exception)

## Low-stakes fast path

- [ ] CI passes (regression + lint)
- [ ] Change does what the PR description says

That's it — no further ceremony required.
