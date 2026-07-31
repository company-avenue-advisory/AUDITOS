<!--
See docs/engineering/DEFINITION_OF_DONE.md for the full checklist and what
makes a PR "consequential" vs. low-stakes. Delete whichever section below
doesn't apply.
-->

## Summary

<!-- What changed, and why. -->

## Test plan

<!-- How you verified this. Paste regression suite output if relevant. -->

---

### If this PR is consequential (touches reconciliation/validation, tenant-scoped data, an external write path, auth/isolation, correction/audit tables, or schema):

- [ ] Reviewed existing implementation before adding new code
- [ ] No probabilistic/LLM shortcut introduced into deterministic rule-execution code
- [ ] Tenant isolation checked for every new/changed query or write
- [ ] Tests added/updated and confirmed to fail without the fix
- [ ] Full regression suite run locally and green
- [ ] Any new external-system write path is idempotent
- [ ] Any new consequential/irreversible action has a human-approval gate
- [ ] No secrets, credentials, or real client/PII data committed
- [ ] Schema changes are additive (or the exception is explicitly justified below)

### If this PR is low-stakes (copy, comments, docs, test-only):

- [ ] CI passes
- [ ] Change does what this description says
