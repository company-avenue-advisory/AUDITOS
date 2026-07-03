# Security Remediation — Phase 2 (Remaining High Findings)

**Scope:** Independently re-verify the High-severity findings deferred at the
end of Phase 1 (`SECURITY_REMEDIATION_PHASE1.md`, "Findings NOT fixed in this
phase") — not trusted from that document, re-derived from source. Fix only
what verifies as real.

**Status:** 5 items were carried into this phase. 4 verified as real
code-level defects and are fixed below. 1 (Zip Slip in batch upload)
independently re-verified and found to be a **false positive** on this
codebase's actual runtime — documented with a reproduction transcript, no
code change made, per "fix only verified High issues." A 5th, previously
undocumented High finding — a cross-tenant aggregate-data leak in
`GET /api/observability/stats` — was discovered while fixing the task-level
observability endpoint in the same file, verified, and fixed in this same
pass rather than deferred, since it is the same defect class (missing tenant
scope) in the same review sweep.

**Not committed.** All changes are in the working tree for review, per
instructions. `backend/main.py` had substantial pre-existing, unrelated
uncommitted work (Google Drive sync batching/subfolder features) before this
phase started; only the specific functions documented below were touched.

Files touched:
- `backend/main.py` — 5 endpoint fixes, all additive (auth/tenant checks,
  query scoping), no route signatures or response shapes changed.
- `backend/tests/test_security_phase2.py` — new, 19 tests.

---

## Verification methodology

Same discipline as Phase 1: read the actual current source for each deferred
item (not the Phase 1 write-up's description of it), trace the route through
to the exploitable behavior, and where a fix pattern already existed
elsewhere in the file for the same defect class (auth + `require_same_tenant`
via a resource's owning `BatchJob`), reuse it rather than invent a new shape.
For the one finding that didn't hold up (Zip Slip), verification meant
writing a live reproduction against the actual library call in use, not
reasoning about the vulnerability class in the abstract.

---

## Findings and fixes

### 1. Unauthenticated `GET /api/tasks/{task_id}/review` — CONFIRMED, FIXED

**File:** `backend/main.py` (`get_task_review`)

**Root cause:** The endpoint had no `current_user` dependency at all — not
even `get_current_user`. Anyone, unauthenticated, with a `task_id`
(sequential-looking UUIDs aside, these are also visible in the frontend's own
network responses to any authenticated user) could read the full
deterministic reconciliation report for any invoice task on the platform:
correction proposals, variance breakdowns, GST amounts, recon status.

**Fix:** Added `current_user: User = Depends(get_current_user)`, then
`require_same_tenant(task.batch.tenant_id if task.batch else None,
current_user)` after the existing 404 check — the same "fetch owning
resource, 404 if missing, 403 if cross-tenant" pattern Phase 1 established
for `get_pdf_file`, `get_duplicate_invoices`, etc. `InvoiceTask` has no
`tenant_id` column of its own; tenancy is derived via its owning `BatchJob`,
which both of this repo's task-creation paths (`upload_batch`,
`GoogleDriveSyncJob` processing) always set.

**Tests** (`TestTaskReviewAuth`): unauthenticated → `401`; cross-tenant → `403`
with report content absent from the response; nonexistent task → `404`;
same-tenant → `200` with the report intact (regression).

---

### 2. Unauthenticated `GET /api/tasks/{task_id}/observability` — CONFIRMED, FIXED

**File:** `backend/main.py` (`get_task_observability`)

**Root cause:** Identical shape to #1 — no `current_user` dependency at all.
Anyone could read the full pipeline execution log (LLM prompt versions,
model identifiers, extraction quality scores, internal flags) for any task.

**Fix:** Added the same pattern as #1: look up the `InvoiceTask` by
`task_id` (previously not done at all — the handler went straight to
querying `ObservabilityLog` by `file_id == task_id`), `404` if missing,
`require_same_tenant` via `task.batch.tenant_id`, then proceed with the
existing log query unchanged.

**Tests** (`TestTaskObservabilityAuth`): unauthenticated → `401`; cross-tenant
→ `403` with the seeded log payload's marker string absent from the
response body; nonexistent task → `404`; same-tenant → `200` with the log
event intact (regression).

---

### 3. Missing tenant check on `PATCH /api/tasks/{task_id}/accept-correction` — CONFIRMED, FIXED

**File:** `backend/main.py` (`accept_correction`)

**Root cause:** The endpoint already had `RoleChecker(["owner", "auditor"])`
— so it wasn't unauthenticated — but never checked that the task's owning
batch belonged to the caller's tenant. Any authenticated owner/auditor from
**any** tenant could mark **any other tenant's** task as
`HUMAN_CORRECTED`, corrupting that tenant's audit trail / reconciliation
state (a write, not just a read — arguably the more serious of the two
`/tasks/{task_id}/...` gaps in this phase).

**Fix:** One line added after the existing 404 check:
`require_same_tenant(task.batch.tenant_id if task.batch else None,
current_user)`. No change to the role requirement or the mutation logic
itself.

**Tests** (`TestAcceptCorrectionTenant`): cross-tenant caller → `403`, and the
task's `recon_status` is verified unchanged in the DB afterward (proves the
write didn't partially apply before the check — it didn't, since the check
now runs first); nonexistent task → `404`; same-tenant owner/auditor → `200`
and the status is actually persisted (regression); unauthenticated → `401`
(regression, pre-existing `RoleChecker` behavior); wrong role (`hr`) → `403`
(regression).

---

### 4. `GET /api/observability/stats` leaks aggregate data across every tenant — NEW FINDING THIS PHASE, FIXED

Not one of the 5 items named in Phase 1's deferred list (that list's
`"/observability"` entry refers to the task-scoped endpoint fixed in #2
above, which shares its URL prefix). Found while fixing #2, in the same
file, by reading the very next endpoint down.

**File:** `backend/main.py` (`get_observability_stats`)

**Root cause:** The endpoint already required `get_current_user`, so it
wasn't unauthenticated — but `total_batches`, `total_files`, the average
extraction-quality score, `total_cost_inr` (aggregated real LLM spend), and
the list of system flags were all computed via unfiltered
`db.query(...).count()` / `db.query(ObservabilityLog).filter(event_type ==
...)` calls with **no tenant restriction whatsoever** — every authenticated
user on the platform, regardless of tenant, saw platform-wide totals
including other tenants' aggregate invoice-processing costs and quality/flag
data. Only the function's own `recent_jobs` sub-section, computed
separately a few lines below, was correctly tenant-scoped — a strong signal
this was an oversight in one code path rather than an intentional design,
the same kind of evidence Phase 1 used to justify its `export_to_excel` fix.

**Why this needed more care than "add a tenant filter":** `ObservabilityLog`
has its own `tenant_id` column, but it's nullable and (per
`services/observability.py`) only populated when the caller explicitly
passes `tenant_id=` to the logger — not verified to happen at every write
site. Filtering on it directly would silently under-count for any log row
where it was never set. `batch_id` on `ObservabilityLog` is `nullable=False`
and every `BatchJob` row reliably has `tenant_id` set (verified in Phase 1
for both creation paths), so the fix joins/filters through
`BatchJob.tenant_id` instead — the same trustworthy key Phase 1 already
relied on throughout this file.

**A second, subtler bug caught while fixing this:** the natural first-draft
fix used `if current_user.tenant_id: <filter>` (matching the pre-existing
`recent_jobs` code and `get_all_jobs` elsewhere in the file) — but that's
exactly the "unassigned caller gets a blanket pass" shape Phase 1's
adversarial round already found and closed once in `require_same_tenant`
(Bypass 1). A freshly-registered, never-assigned user would have had
`current_user.tenant_id is None`, skipped the filter, and seen every
tenant's totals again through the back door of my own fix. Corrected to
filter unconditionally — `BatchJob.tenant_id == current_user.tenant_id`
compiles to `IS NULL` when the caller has no tenant, matching only true
legacy/untenanted data, never every tenant's data. `recent_jobs`'s own
pre-existing `if current_user.tenant_id:` branch was tightened the same way
while in the function, for consistency (**note:** this is a second,
independent behavior change from the literal Phase-1-deferred list — see
"Scope note" below).

**Fix (all in `get_observability_stats`):**
```python
tenant_batch_ids = {
    b.id for b in db.query(BatchJob.id).filter(BatchJob.tenant_id == current_user.tenant_id).all()
}
total_batches = db.query(BatchJob).filter(BatchJob.tenant_id == current_user.tenant_id).count()
total_files = db.query(InvoiceTask).filter(InvoiceTask.batch_id.in_(tenant_batch_ids)).count()
log_q = db.query(ObservabilityLog).filter(ObservabilityLog.batch_id.in_(tenant_batch_ids))
# score_logs / metric_logs / flag_logs now derive from log_q instead of
# unfiltered db.query(ObservabilityLog)
...
# recent_jobs' batch_q now always filters by BatchJob.tenant_id == current_user.tenant_id
```

**Tests** (`TestObservabilityStatsTenantScoping`): seeded a second tenant with
its own batch/task/cost-log/flag-log; confirmed the first tenant's stats
response contains neither the other tenant's batch/file counts, cost total,
nor its flag (`OTHER_TENANT_SECRET_FLAG` absent from `recent_flags`);
confirmed the other tenant's own owner still sees their real totals
(regression); confirmed a never-assigned user sees all-zero stats rather
than the platform-wide total (closing the Bypass-1-shaped hole described
above).

**Scope note:** This finding and its fix were not requested by name. It's
included because it's the same defect class as item #2 (missing tenant
scope), found by direct inspection of adjacent code in the same file during
this phase's review, and left unfixed it would have been a glaring miss
given the sibling function three lines below already got the fix. The
`get_all_jobs` endpoint (`main.py:483`) has the same `if
current_user.tenant_id:` shape and was **not** touched — it's a different
endpoint, outside today's targeted files, and is flagged below for Phase 3
rather than fixed here, to keep this phase's diff bounded to what was
directly touched for a named reason.

---

### 5. Zip Slip in `zipfile.ZipFile.extractall()` during batch upload — RE-VERIFIED: FALSE POSITIVE, NOT FIXED

**File:** `backend/main.py` (`upload_batch`, the `.zip` branch)

**What the original audit flagged:** `zip_ref.extractall(extract_dir)` is
called with no validation of member names, and `{filename:path}`-style zip
member names containing `../` could in principle escape `extract_dir` and
write files elsewhere on disk (the classic "Zip Slip" CVE class).

**Independent verification — reproduced against this exact call pattern,
this repo's installed Python version (3.12.2):**

```python
import zipfile, io, os, tempfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as zf:
    zf.writestr('../../evil_marker.pdf', b'PWNED')
    zf.writestr('C:/Windows/evil2.pdf', b'PWNED2')
    zf.writestr('/etc/evil3.pdf', b'PWNED3')
    zf.writestr('..\\..\\evil4.pdf', b'PWNED4')
buf.seek(0)
extract_dir = <fresh temp dir, mirroring batch_dir/extracted_xxxx>
with zipfile.ZipFile(buf) as zf:
    zf.extractall(extract_dir)
# result: ALL FOUR payloads land inside extract_dir. None escape it.
# os.path.exists('C:/Windows/evil2.pdf') -> False
```

**Why it doesn't hold up:** CPython's `zipfile.ZipFile.extractall` /
`_extract_member` strips drive letters, leading path separators, and — the
part that actually matters here — filters out `os.path.curdir` (`.`) and
`os.path.pardir` (`..`) path *segments* before joining onto the target
directory (`invalid_path_parts` in `Lib/zipfile.py`). This sanitization has
been in the standard library for a long time (well before Python 3.6) and is
active, unconditionally, for every call to `extractall`/`extract` — this
repo's code doesn't opt out of it or implement its own extraction loop that
could bypass it. `upload_batch` calls bare `zip_ref.extractall(extract_dir)`
with no custom member handling, so it gets this protection automatically.
Relative traversal, backslash traversal, and absolute/drive-letter paths
were all tested and all three land safely inside `extract_dir`.

**Action taken:** None — there is no code defect to patch. Documented here,
with the reproduction transcript above, so this doesn't get silently
re-flagged as open in a future pass without evidence. If this repo's
deployment target (`render.yaml`) is ever pinned to a Python interpreter
older than roughly 3.6, or if the extraction logic is ever rewritten to use
`ZipInfo`/low-level `zf.read()` + manual path joining instead of
`extractall`, this finding should be re-verified from scratch rather than
assumed still closed.

---

### 6. CORS `allow_origins=["*"]` + `allow_credentials=True` — CONFIRMED, FIXED

**File:** `backend/main.py` (CORS middleware configuration, near the top of
the file)

**Root cause:** `ALLOWED_ORIGINS` defaults to `"*"` when unset, and the
`CORSMiddleware` was configured with `allow_credentials=True`
**unconditionally**, regardless of what `origins` resolved to. Two distinct
problems:

1. **Contradictory-but-honored config.** Per the fetch/CORS spec, a browser
   is supposed to refuse credentialed requests when the server's
   `Access-Control-Allow-Origin` is a literal `*` — but Starlette's
   `CORSMiddleware` will still *advertise*
   `Access-Control-Allow-Credentials: true` alongside it if told to, which is
   nonsensical and is flagged by essentially every CORS security scanner.
2. **The practical exploit path, given #1 and #2/#3 above.** With
   `ALLOWED_ORIGINS` unset (its default), `Access-Control-Allow-Origin: *`
   is sent for every response. That doesn't let a malicious page steal a
   victim's bearer token (this app stores its JWT in `localStorage`, not a
   cookie, and CORS "credentials" mode governs cookie/HTTP-auth
   auto-attachment, not `localStorage` access) — but it **does** mean any
   endpoint that (as found in this phase) has no auth check at all is
   directly, silently readable from any origin's client-side JavaScript,
   with no token needed at all. Wildcard CORS is the multiplier that turns
   an unauthenticated-endpoint bug from "reachable if you guess the URL"
   into "reachable and *readable by script* from literally any website the
   victim happens to visit."

**Verified:** confirmed via `render.yaml` / `backend/.env.example` that no
production `ALLOWED_ORIGINS` value is enforced anywhere in this repo's
deployment config — a fresh deploy without an operator explicitly setting
this variable silently runs wide open.

**Fix:**
```python
_environment = os.getenv("ENVIRONMENT", "development").lower()
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()] or ["*"]
_has_wildcard_origin = "*" in origins
if _has_wildcard_origin and _environment == "production":
    raise RuntimeError(...)  # same fail-closed pattern as JWT_SECRET_KEY

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=(not _has_wildcard_origin),
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Two deliberate choices, both found necessary during the adversarial pass on
this fix (see below), not in the first draft:
- Checks `"*" in origins` (membership), not `origins == ["*"]` (exact
  match) — an operator could otherwise smuggle a wildcard into an explicit
  CSV, e.g. `ALLOWED_ORIGINS=https://app.example.com,*`, and an exact-match
  check would miss it (Starlette itself treats `"*" in allow_origins` as
  "allow all", regardless of what else is in the list).
- Fails closed the same way `JWT_SECRET_KEY`'s existing check does
  (`RuntimeError` at startup in `production`, a `print()` warning
  otherwise) — consistent with an established pattern in this same file
  rather than a new one, and doesn't change `development`/`test` behavior at
  all (this repo's own `backend/.env` already sets a real
  `ALLOWED_ORIGINS` for local dev, so this change is invisible there).

**Tests** (`TestCorsConfig`): confirms `allow_credentials` is `False` on the
constructed middleware when origins resolve to `["*"]`; confirms, via a real
subprocess re-import of `main.py` with `ENVIRONMENT=production` and
`ALLOWED_ORIGINS=*` pinned explicitly, that the module refuses to start
(the naive version of this test — merely *unsetting* `ALLOWED_ORIGINS` —
was tried first and silently passed for the wrong reason: this repo's
`backend/.env` supplies a real value via `load_dotenv()`'s default
`override=False`, so an unset env var gets filled from the file rather than
staying unset. Pinning `ALLOWED_ORIGINS=*` explicitly in the subprocess
environment was required to actually exercise the wildcard branch.).

---

## Adversarial pass on this phase's own fixes

Rather than trusting "added a tenant check" or "added an auth dependency"
without re-attacking it, each fix above was pressure-tested for the same
classes of bypass Phase 1's adversarial round found:

- **Orphaned-task edge case (#1/#2/#3):** `InvoiceTask.batch_id` is
  nullable in the schema, so `task.batch` could in principle be `None` for
  a task with no owning batch. In that case `require_same_tenant(None,
  current_user)` takes the "resource has no tenant" graceful-pass branch —
  any authenticated user could read/mutate such an orphaned task. This is
  not a new gap introduced here: it's the exact same "legacy/untenanted
  resource" exemption Phase 1 explicitly kept (and tested) for
  `require_same_tenant`'s other five call sites, and both of this repo's
  task-creation paths always set `batch_id`. Treated as an accepted,
  pre-existing convention rather than something to special-case here.
- **`require_same_tenant` unassigned-caller bypass (Phase 1's Bypass 1),
  re-tried against every fix in this phase:** confirmed each of #1/#2/#3
  correctly reject an unassigned (`tenant_id is None`) caller against a
  tenanted task, since `require_same_tenant`'s tightened Phase 1 behavior
  (resource has a tenant + caller doesn't → `403`, not a pass) is reused
  unchanged. For #4 (`observability/stats`, no single resource to check
  against `require_same_tenant`), the equivalent bypass was tried directly
  — see the "second, subtler bug" write-up in finding #4 above; caught and
  fixed before this phase closed, with a dedicated regression test
  (`test_unassigned_user_sees_only_legacy_untenanted_data_not_everything`).
- **Role-bypass interaction (#3):** `accept-correction` uses
  `RoleChecker(["owner", "auditor"])`, under which `role == "developer"`
  unconditionally bypasses the role check. Verified `require_same_tenant` is
  applied uniformly regardless of role — a `developer` account (typically
  `tenant_id = None`, per Phase 1's documented auto-assign exclusion) is
  still tenant-checked like anyone else, consistent with how `get_pdf_file`
  and `update_item` already treat `developer` in this file. Not a new
  inconsistency.
- **CORS wildcard-smuggling:** tried `ALLOWED_ORIGINS="https://real.example.com,*"`
  against a naive `origins == ["*"]` check (the first draft) — it slipped
  through, since the list isn't exactly `["*"]` but Starlette still treats
  it as "allow all" internally. Switched to membership (`"*" in origins`);
  re-tried, now correctly caught (`allow_credentials` forced to `False`,
  and the production guard fires).
- **404-vs-403 oracle (#1/#2/#3):** same pre-existing, app-wide convention
  flagged as open in Phase 1 (a `404` for a nonexistent task vs. `403` for
  a real-but-foreign-tenant task lets an attacker distinguish "doesn't
  exist" from "exists elsewhere"). Not introduced or worsened by this
  phase's fixes; still open, still tracked below.

---

## Test results

```
python -m unittest backend.tests.test_security_phase2 -v
  Ran 19 tests — OK (19/19 passed)

python -m unittest backend.tests.test_security_phase1 -v
  Ran 28 tests — OK (28/28 passed, unaffected by this phase's changes)

python backend/tests/regression/run_regression.py
  103 tests · 103 passed · 0 failed · 0 skipped — ALL PASSED (unaffected)
```

New test file: `backend/tests/test_security_phase2.py`. Same harness
conventions as Phase 1 — boots the real `main.app` against an isolated
on-disk SQLite temp file, drives it through `fastapi.testclient.TestClient`,
seeds tenants/users/batches/tasks/logs directly via the ORM. Not wired into
CI (none exists in this repo — a pre-existing, separately-tracked gap).

```
python backend/tests/test_security_phase2.py
python backend/tests/test_security_phase1.py
python backend/tests/regression/run_regression.py
```

---

## Findings NOT fixed in this phase (deliberately deferred)

- **`get_all_jobs` (`main.py:483`) has the same unassigned-caller-sees-
  everything shape** as the `recent_jobs`/aggregate bug fixed in finding #4
  — `if current_user.tenant_id:` skips tenant filtering entirely for a
  never-assigned `owner`/`developer`, who then sees every tenant's batch
  list via the `else` branch's role check. Discovered during this phase's
  review but not fixed here: it's a different endpoint, not one of the
  named deferred items, and fixing it needs its own targeted verification +
  tests rather than folding into an already-broad phase. Flagged for Phase 3.
- **The 403-vs-404 tenant/existence oracle**, carried over unresolved from
  Phase 1 (see above) — still a pre-existing, app-wide convention, still
  not touched.
- **Everything already listed as Medium/Low or architectural in Phase 1**
  (owner-tenant-scoping duplication, `update_item`'s denylist-vs-allowlist
  field guard, `.dockerignore`/Docker hardening, CI/CD absence, unpinned
  dependencies, Sentry `send_default_pii=True`, JWT default-secret fallback
  outside `production`, disabled TLS verification on the Redis broker) —
  unchanged, out of scope for a High-severity-only phase.

## Self-review: regressions searched for and ruled out

- Every fixed endpoint has both an attack-path test and a same-tenant
  regression test proving the legitimate flow is unaffected.
- Full pre-existing Phase 1 suite (28 tests) and regression harness (103
  tests) both rerun clean after every fix in this phase, including after the
  `get_observability_stats` rewrite (the one with the widest blast radius,
  since it touches four separate query variables in one function).
- Frontend call sites for all 4 newly-auth-required/tenant-scoped endpoints
  (`ReviewPanel.tsx`'s `/review` and `/accept-correction` calls,
  `invoice-extractor/page.tsx`'s `/observability` call, `page.tsx`'s
  `/observability/stats` call) were checked against `AuthGuard.tsx`'s global
  `window.fetch` interceptor (documented in Phase 1): all four are rendered
  under the root layout's `<AuthGuard>` wrapper, so all already receive an
  automatic `Authorization: Bearer <token>` header with no frontend code
  changes required. Confirmed by reading `layout.tsx`, not assumed.
- No schema changes, no new dependencies, no route signature or response
  shape changes — every fix in this phase is either an added dependency
  parameter, an added authorization check, or a query-scoping change that
  narrows (never widens) what a caller can see.
