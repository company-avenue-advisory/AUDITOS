# Security Remediation — Phase 1 (Critical Findings)

**Scope:** Independently verify and remediate the 5 Critical findings from the
DevOps/Security audit. High-severity and lower findings are explicitly out of
scope for this phase (see "Deferred" below).

**Status:** All 5 Critical findings independently verified as real. 4 were
code-level defects and have been fixed with minimal, behavior-preserving
patches plus regression/authorization tests. 1 (live secrets in `.env`) is an
operational finding with no code fix available in-repo — it requires manual
credential rotation, documented below.

A follow-up adversarial review of those 4 fixes (see "Adversarial review"
below) found and closed 3 further bypasses — 2 in the shared tenant-isolation
helper/admin endpoints, 1 a mass-assignment gap in the item-update endpoint —
that would otherwise have left Critical #4/#5 practically unprotected against
the most likely attacker shapes.

A subsequent Principal Engineer review pass (see "Phase 1 Review" below) found
one more gap: `GET /api/jobs/{batch_id}/files/{filename:path}` — the same
endpoint hardened against path traversal — had no tenant-isolation check at
all. Initially documented as a Phase 2 item since that review was read-only;
reclassified as a Phase 1 blocker and fixed in a dedicated follow-up pass
(see "3a." below), since it's a direct tenant-confidentiality gap on data
already in this phase's scope. **Phase 1 now closes with all 5 Critical
findings fixed and verified, plus 4 additional bypasses/gaps found through
adversarial and principal-engineer review, also fixed and verified — 8
code-level defects total.** Files touched in total:
`backend/main.py`, `backend/services/auth.py`,
`frontend/src/app/invoice-extractor/page.tsx`,
`frontend/src/app/google-drive-sync/page.tsx`,
`backend/tests/test_security_phase1.py` (new).

**Committed:** `aebbf4f` — "security: Phase 1 critical fixes + adversarial/review
hardening". The commit contains only the 6 files listed above; the repository
had substantial unrelated, pre-existing uncommitted work (Google Drive sync
batching/subfolder features) at the time, which was carefully separated out
hunk-by-hunk and left untouched in the working tree rather than folded into
this commit.

---

## Verification methodology

Each finding was independently re-derived by reading the actual source (not
trusted from the audit report):
- Confirmed the vulnerable code path by line number.
- Traced the request from route decorator through to the exploitable behavior.
- Checked whether existing, similar endpoints in the same file already solved
  the same problem correctly (several do — `/api/jobs/{batch_id}` and
  `/api/export/{batch_id}/gstr1` already use `get_current_user` +
  `require_same_tenant`), so fixes could reuse the codebase's own established
  pattern rather than invent a new one.

---

## Findings and fixes

### 1. Live secrets in `backend/.env` — CONFIRMED, operational (no code fix)

**Root cause:** Production credentials (DB password, JWT signing secret, GCP
service-account private key, LLM API keys, Redis token) are stored in a
plaintext `.env` file on the local filesystem.

**Verification:** Confirmed `backend/.env` exists, contains live-looking
credentials, is listed in `.gitignore` (`.env`, `.env.*`), and is **not**
tracked by git (`git ls-files` returns nothing for it). So the immediate
"committed to git" risk is not present — but the file still exists in
plaintext on disk, which is what the finding is actually about.

**Why no code fix:** There is no code defect to patch — `.env`-based config
loading via `python-dotenv` is a standard, appropriate pattern. The fix here
is operational, not architectural, and requires access to external systems
(Supabase, GCP IAM, LLM provider consoles, Upstash) that I cannot act on from
this repository.

**Action required (manual, outside this PR):**
1. Rotate every credential currently in `backend/.env`: Supabase DB password,
   JWT_SECRET_KEY, the GCP service-account key, all LLM provider API keys, and
   the Upstash Redis token.
2. Store secrets in Render's environment variable manager (already the
   deployment target per `render.yaml`) rather than a local `.env` file for
   any shared/staging/prod environment.
3. Confirm `.dockerignore` excludes `.env` before any Docker build (currently
   no `.dockerignore` exists at all — flagged as a Medium finding in the
   original audit, Phase 2 scope).

---

### 2. Role self-escalation via `/api/auth/register` — CONFIRMED, FIXED

**File:** `backend/main.py:150-155`, `backend/services/auth.py:117-133`

**Root cause:** `POST /api/auth/register` accepted any client-supplied
`role`, and its `allowed_roles` list included `"developer"`. Separately,
`RoleChecker.__call__` (`services/auth.py:126`) treats `role == "developer"`
as an unconditional bypass of every `allowed_roles` check in the app — it's a
platform-wide superadmin role, not a normal RBAC tier. Combining the two: any
anonymous caller could `POST /api/auth/register` with `role=developer` and
immediately hold admin-equivalent access to every tenant.

Notably, the `User` model's own docstring
(`backend/models.py:157-158`) already states *"Supported roles: owner, hr,
auditor, other"* — `developer` was never intended to be part of the
self-service set. The vulnerable code had drifted from the model's own
documented design.

**Fix:** Removed `"developer"` from the self-registration `allowed_roles`
list in `backend/main.py`. All other roles (`owner`, `hr`, `auditor`,
`other`) are unaffected — registration for those roles behaves identically to
before.

```python
# before
allowed_roles = ["owner", "hr", "auditor", "developer", "other"]
# after
allowed_roles = ["owner", "hr", "auditor", "other"]
```

`developer` accounts can now only be provisioned by direct database access
(consistent with it being an ops/superadmin role, not a signup-time choice).

**Tests added** (`backend/tests/test_security_phase1.py::TestRegisterRoleEscalation`):
- Registering with `role=developer` → `400`, user not created.
- Case-insensitivity (`DEVELOPER`) also rejected.
- Regression: `owner`, `hr`, `auditor`, `other` still register successfully.
- Regression: omitting `role` still defaults to `auditor`.

---

### 3. Path traversal in file download endpoint — CONFIRMED, FIXED

**File:** `backend/main.py:480-517` (`GET /api/jobs/{batch_id}/files/{filename:path}`)

**Root cause:** `filename` is a `{filename:path}` route parameter (accepts
slashes) and was joined directly into the batch's temp directory
(`os.path.join(batch_dir, filename)`) with no check that the resulting path
stays inside `batch_dir`. A caller with any valid JWT (itself trivially
obtainable pre-fix via finding #2) could request a `../`-style payload to read
arbitrary files readable by the server process — including `backend/.env`.

**Fix:** After computing the candidate path, resolve both the batch directory
and the candidate file to their real (symlink-resolved, normalized) paths and
reject the request with `400` unless the candidate resolves to somewhere
inside the batch directory:

```python
batch_dir_real = os.path.realpath(batch_dir)
file_path_real = os.path.realpath(file_path)
if file_path_real != batch_dir_real and not file_path_real.startswith(batch_dir_real + os.sep):
    raise HTTPException(status_code=400, detail="Invalid filename")
```

This is applied once, before any of the three lookup strategies the endpoint
tries (local disk, GCS pull-through, subdirectory walk), so all three are
covered. The `os.walk` fallback was already safe on its own (it matches
against real on-disk basenames, so a traversal string can never equal a bare
filename in that list) but is now additionally covered by the upfront check.

**Tests added** (`backend/tests/test_security_phase1.py::TestFileDownloadPathTraversal`):
- Regression: a legitimate filename inside the batch dir still downloads
  (`200`).
- A `../`-style traversal payload targeting a file outside the batch dir is
  rejected (`400`) and its content is never returned. (Payloads are
  percent-encoded in the test — `httpx`, like browsers, normalizes literal
  `../` client-side before the request is even sent, which would have made
  the test pass for the wrong reason. Percent-encoding lets the payload reach
  the server's route handler, where the actual fix is exercised.)
- A deep traversal payload targeting `backend/.env` is rejected.
- Regression: the pre-existing authentication requirement on this endpoint
  (any valid JWT) is unchanged — unauthenticated requests still get `401`.

---

### 3a. Missing tenant isolation on the same file-download endpoint — CONFIRMED, FIXED

Found during the Phase 1 principal-engineer review (see "Phase 1 Review"
below), reclassified by the reviewer as a Phase 1 blocker rather than
Phase 2 follow-up, and fixed in this pass. This is a distinct defect from
the path traversal fixed above — it's about *whose* batch you're allowed to
read, not about escaping the batch directory.

**File:** `backend/main.py:500-518` (`GET /api/jobs/{batch_id}/files/{filename:path}`)

**Root cause:** The endpoint checked that the caller had *a* valid JWT
(`get_current_user`) but never checked that the caller belonged to the same
tenant as the batch being read — the only one of the six `require_same_tenant`-
eligible resource-by-ID endpoints in the file missing that check, despite
being the endpoint most recently touched (for the traversal fix). Reproduced
live before fixing: a Tenant B user, given or guessing Tenant A's `batch_id`,
could download Tenant A's uploaded PDF (`200`, file bytes returned).

**Fix:** Added the exact same pattern already used by `get_job_status` (its
nearest sibling — same `{batch_id}` shape, same file): fetch the owning
`BatchJob`, `404` if it doesn't exist, `require_same_tenant(batch.tenant_id,
current_user)` before touching the filesystem at all. The traversal
containment check added earlier in this phase is untouched — it now runs
*after* the tenant check, so a cross-tenant request is rejected with `403`
before any path-resolution logic executes.

```python
batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
if not batch:
    raise HTTPException(status_code=404, detail="Job not found")
require_same_tenant(batch.tenant_id, current_user)
```

Verified both of this repo's `BatchJob`-creating code paths
(`upload_batch` in `main.py` and the Google Drive sync job in
`services/google_drive_sync.py`) always set `tenant_id` on the row they
create, so no legitimate batch can hit the new `404` — the only case that 404s
is a `batch_id` with no corresponding row at all (never-existed or already
deleted), which is the same behavior `get_job_status` already has.

**Tests added/updated** (`backend/tests/test_security_phase1.py::TestFileDownloadPathTraversal`):
- `test_legit_filename_still_downloads` — regression: same-tenant access to
  a real file still succeeds (`200`). (Existing test; its fixture now also
  creates the `BatchJob` row the new check requires — see note below.)
- `test_cross_tenant_file_access_rejected` — **new.** A second tenant/user
  requesting the exact same, correctly-spelled filename (no traversal
  payload involved) is rejected with `403` and the file content is never
  returned.
- `test_unauthenticated_request_still_rejected` — regression: no token still
  gets `401` (unchanged; `get_current_user`'s dependency resolution runs
  before the new tenant check, so this ordering was never at risk).
- `test_nonexistent_batch_returns_404_not_leaked_files` — **new.** A random
  `batch_id` with no `BatchJob` row returns `404` rather than falling through
  to any filesystem check.
- All 5 existing path-traversal tests (`../`, backslash, Windows drive-letter,
  deep `.env` traversal) rerun unchanged and still pass — confirming the
  traversal containment check added earlier in this phase was not weakened
  or reordered by this fix.

**Fixture change:** `TestFileDownloadPathTraversal.setUp` previously created
files on disk for `self.batch_id` but no corresponding `BatchJob` row (the
tenant check didn't exist yet, so nothing required one). Updated to create a
`BatchJob` row owned by `self.tenant`, plus a second tenant/user pair for the
new cross-tenant test — this is what the pre-existing "regression" tests in
this class were implicitly relying on being irrelevant; it's now load-bearing.

---

### 4. Unauthenticated `PUT /api/items/{item_id}` — CONFIRMED, FIXED

**File:** `backend/main.py:1306-1326`

**Root cause:** The endpoint had **no** `current_user` dependency at all —
not even `get_current_user`. Anyone, unauthenticated, could overwrite any
field (amounts, GSTINs, tax values) on any sales/purchase line item by
iterating `item_id`.

**Fix:** Added `current_user: User = Depends(RoleChecker(["owner", "auditor"]))`,
matching the role set already used for the equivalent correction-acceptance
endpoint (`PATCH /api/tasks/{task_id}/accept-correction`, line 697) — these
are both "CA reviewer corrects/accepts a value" actions, so reusing that
existing role decision keeps the RBAC model consistent rather than inventing
a new policy. Then added tenant-ownership enforcement, since a line item
doesn't carry `tenant_id` directly — it's derived via `item.task.batch.tenant_id`:

```python
resource_tenant_id = item.task.batch.tenant_id if item.task and item.task.batch else None
require_same_tenant(resource_tenant_id, current_user)
```

`require_same_tenant` is the same helper already used elsewhere in the file
(e.g. `get_job_status`); its existing "graceful" semantics for
legacy/unenrolled resources (`tenant_id is None`) were preserved unchanged.

**Tests added** (`backend/tests/test_security_phase1.py::TestItemUpdateAuth`):
- Unauthenticated request → `401`.
- Authenticated as a role outside `["owner", "auditor"]` (e.g. `hr`) → `403`.
- Authenticated as an `auditor` belonging to a **different** tenant than the
  item's batch → `403`.
- Regression: an `auditor` in the **same** tenant can still update the item,
  and the value is actually persisted.

---

### 5. Unauthenticated `GET /api/export/{batch_id}` — CONFIRMED, FIXED

**File:** `backend/main.py:883-899`

**Root cause:** No auth dependency and no tenant check at all — anyone who
obtained or guessed a `batch_id` could download another tenant's full
Excel invoice register (GSTINs, amounts, party details) with no credentials.

**Fix:** Added `current_user: User = Depends(get_current_user)` and
`require_same_tenant(batch.tenant_id, current_user)`, copying the exact
pattern already used by the sibling endpoint two hundred lines below it,
`GET /api/export/{batch_id}/gstr1` (line 999-1016), which already had this
protection. This was the most direct evidence that the missing check on the
primary export endpoint was an oversight rather than an intentional design
choice — a near-identical endpoint in the same file already does it
correctly.

**Tests added** (`backend/tests/test_security_phase1.py::TestExportAuth`):
- Unauthenticated request → `401`.
- Authenticated user from a different tenant → `403`.
- Regression: authenticated user from the same tenant still downloads
  successfully.

---

## Frontend changes required to preserve behavior

Adding auth requirements to `PUT /api/items/{item_id}` and
`GET /api/export/{batch_id}` would have **broken the app** for legitimate
users, because two of the three frontend call sites for these endpoints were
not sending an `Authorization` header at all (they were relying on the
endpoints' prior lack of auth). Fixing the backend without fixing these call
sites would not "preserve existing behaviour" — it would silently break
inline cell editing and Excel export for every real user. Updated:

- `frontend/src/app/invoice-extractor/page.tsx` — both `PUT /api/items/`
  call sites (inline cell edit, GSTR-1 category dropdown) and the
  `GET /api/export/{batch_id}` call site now send
  `Authorization: Bearer <token>`, matching the pattern already used
  elsewhere in the same file (`handleDownloadGSTR1`).
- `frontend/src/app/google-drive-sync/page.tsx` — `downloadExcel` previously
  triggered the export via a plain `<a href>` click with the JWT passed as a
  `?token=` **query string parameter**. The backend has never read auth
  tokens from query strings (only the `Authorization` header, via
  `OAuth2PasswordBearer`), so this was already a dead/no-op code path, and
  extending server-side auth to accept query-string tokens would introduce a
  new problem (tokens leak via browser history, proxy/access logs, and
  `Referer` headers). Instead, converted `downloadExcel` to the same
  `fetch` + `Authorization` header + `Blob` pattern already proven correct in
  `handleDownloadGSTR1`, rather than expanding the backend's auth surface.

---

## Adversarial review (post-fix)

After the 4 fixes above landed, a dedicated adversarial pass attempted to
bypass each one — alternative attack paths, encoding tricks, IDOR variants,
path-normalization edge cases, and tenant-isolation failures — rather than
trusting that "auth dependency added" meant "actually secure." **3 real,
independently-exploitable bypasses were found and closed.** All three were
proven exploitable with a live reproduction against the running app before
being fixed, and reproduction was rerun after the fix to confirm closure.

### Bypass 1 — `require_same_tenant` granted a blanket pass to any unassigned caller

**Attack:** Every user's `tenant_id` is `None` immediately after registration
(finding #2's fix doesn't change this — it only restricts *which* role can be
chosen, not whether a tenant is assigned). `require_same_tenant`
(`services/auth.py`) read:

```python
if not resource_tenant_id or not current_user.tenant_id:
    return  # graceful: unenrolled tenants (legacy data) are not blocked
```

`not current_user.tenant_id` is `True` for every brand-new account, so the
tenant check added for Critical #4 and #5 was a no-op against the single most
common attacker shape: register, log in, hit the endpoint. Reproduced live:
a freshly registered, never-assigned `auditor` account could `GET` any
tenant's export and `PUT` any tenant's line items (`200` both times, value
actually written).

**Fix:** `require_same_tenant` now only grants the graceful pass when the
**resource** has no tenant (true legacy/untenanted data). A caller with no
tenant of their own is no longer treated as exempt:

```python
if not resource_tenant_id:
    return  # graceful: legacy/global resources with no tenant are not blocked
if resource_tenant_id != current_user.tenant_id:
    raise HTTPException(status_code=403, ...)
```

This is a shared helper used at 6 call sites in `main.py`, not just the 2 I
added — all 6 follow the identical "fetch resource, check same tenant"
pattern, so tightening it is a strict improvement everywhere it's used, not a
scoped patch. No legitimate flow depended on an unassigned user matching a
tenanted resource. Verified via `test_legacy_untenanted_resource_still_accessible`
that the original, actually-intended exemption (resource itself has no
tenant) still works.

### Bypass 2 — tenant-hopping via `assign-user`, no unassigned-caller trick needed

**Attack:** `POST /api/admin/tenants/{tenant_id}/assign-user` was missing the
`current_user.role == "owner" and current_user.tenant_id != tenant_id` check
present on its 3 sibling admin endpoints (`list_tenant_users`,
`remove_user_from_tenant`, `update_tenant`). Since `"owner"` is a legitimately
self-registrable role, an attacker could register as `owner` and call this
endpoint directly to assign themselves into **any existing tenant**,
regardless of whether they'd ever belonged to it — a more direct bypass than
Bypass 1, since it makes the attacker a *bona fide* member of the victim
tenant rather than relying on a gap in a check. Reproduced live: self-registered
`owner` → `assign-user` into an unrelated populated tenant → `200` → then
legitimately passed `require_same_tenant` on that tenant's export.

**Why a simple tenant-scoping check wasn't enough:** the frontend
(`firm-settings/page.tsx`) has two legitimate call patterns for this same
endpoint — an owner bootstrapping their *own newly created* tenant (where
their `tenant_id` is still `None` at call time) and an owner inviting a
colleague into a tenant they already belong to. A first attempt using a
"tenant has zero existing members" heuristic to distinguish bootstrap from
attack was tested and found insufficient: a tenant can legitimately have real
batch/invoice data with zero currently-assigned users (e.g. after an admin
offboarded its last member), so the heuristic let the same attack through
against such a tenant.

**Fix:** Removed the ambiguity at the source instead of trying to
heuristically distinguish it after the fact. `POST /api/admin/tenants` now
atomically assigns the creating `owner` to the tenant they just created
(only when they don't already belong to one; `developer` accounts
provisioning on behalf of a client are deliberately not auto-assigned).
`assign-user` no longer needs, or allows, a bootstrap special case at all —
an `owner` caller must already belong to the target tenant, full stop:

```python
if current_user.role == "owner" and current_user.tenant_id != tenant_id:
    raise HTTPException(status_code=403, ...)
```

Verified both legitimate frontend flows still work end-to-end
(`test_owner_bootstrap_create_tenant_auto_assigns_self` — including the
frontend's follow-up self-assign call now being a harmless no-op — and
`test_owner_can_still_invite_colleague_into_own_firm`), and that the hop
attack is blocked (`test_owner_cannot_hop_into_unrelated_existing_tenant`).

### Bypass 3 — mass assignment on `PUT /api/items/{item_id}` via unrestricted `setattr`

**Attack:** The tenant check added for Critical #4 validates the item's
tenant at *read* time, but the handler then does
`setattr(item, req.field, req.value)` for **any** `req.field` that
`hasattr(item, ...)` returns true for — including `task_id`, the foreign key
that determines which task (and therefore which batch and tenant) the item
belongs to. A legitimate, same-tenant `auditor` could pass
`field=task_id, value=<another tenant's task id>` to re-parent their own item
onto a different tenant's task after passing the tenant check, corrupting the
victim tenant's data. Reproduced live: re-parent succeeded (`200`), item's
`task_id` was rewritten to point at the other tenant's task.

**Fix:** Added an explicit denylist for primary/foreign-key columns that must
never be client-writable:

```python
NON_EDITABLE_FIELDS = {"id", "task_id"}
if req.field in NON_EDITABLE_FIELDS or not hasattr(item, req.field):
    raise HTTPException(status_code=400, detail="Invalid field")
```

Verified the re-parent attack is now rejected (`400`, `task_id` unchanged)
and that legitimate data-field edits (`taxable_value`, etc.) are unaffected.

### Other adversarial angles tried and found to already be closed

- **Path traversal, alternate encodings:** the realpath-containment check
  from the original fix was re-attacked with percent-encoded backslashes
  (`..%5c`, Windows-style separators) and a fully-encoded absolute Windows
  drive path (`C%3a%5cWindows%5cwin.ini` — `os.path.join` silently *discards*
  the batch directory when the second argument is an absolute path, a
  different bypass mechanism than relative `../`). Both were already blocked
  by the existing realpath check, since it operates after decoding rather
  than pattern-matching the raw string. Added as explicit regression tests
  rather than a code change.
- **Role-escalation, alternate paths:** searched `main.py` for any other
  place a user's `role` can be mutated post-registration (profile/preference
  update endpoints) — none exists; `role` is set once at registration and
  never touched again outside direct DB access.
- **IDOR via 403-vs-404 oracle:** `PUT /api/items/{item_id}` and
  `GET /api/export/{batch_id}` return `404` for a nonexistent resource but
  `403` for a real resource in another tenant, which lets an attacker
  distinguish "exists elsewhere" from "doesn't exist" — a minor tenant/ID
  enumeration side channel. This is a pre-existing, app-wide convention
  (`get_job_status` and others already do the same 404-then-403 ordering), not
  something introduced by these fixes. Changing it would mean altering a
  shared status-code convention across every `require_same_tenant` call site,
  which is a broader behavior change than "close the bypasses in what I
  shipped this phase." Flagged here for Phase 2 rather than fixed silently.

---

## Test results

```
python -m unittest tests.test_security_phase1 -v
  Ran 28 tests in ~65s — OK (28/28 passed)
  (16 from the original fixes + 10 from the adversarial follow-up + 2 from
  the get_pdf_file tenant-isolation fix found in the Phase 1 Review:
  cross-tenant denial and nonexistent-batch 404)

python tests/regression/run_regression.py
  103 tests · 103 passed · 0 failed · 0 skipped — ALL PASSED (pre-existing suite, unaffected)
```

New test file: `backend/tests/test_security_phase1.py`. It boots the real
FastAPI app (`main.app`) against an isolated on-disk SQLite database (a fresh
temp file per run, via `DATABASE_URL` set before `main` is imported) and
drives it through `fastapi.testclient.TestClient`, seeding tenants/users/
batches directly via the ORM rather than through the (now-restricted)
`/register` endpoint where a privileged role is needed for a test fixture.

**Not currently wired into CI** — no CI/CD pipeline exists in this repo at
all (a separate High/Medium-tier finding from the original audit, out of
scope for this phase). Until CI exists, this suite and the existing
regression harness must be run manually before merging security-sensitive
changes:

```
python backend/tests/test_security_phase1.py
python backend/tests/regression/run_regression.py
```

---

## Self-review: regressions searched for and ruled out

- **Existing legitimate flows for all 4 fixed endpoints** are covered by a
  passing regression test in the new suite (see above) — not just the attack
  path.
- **Full pre-existing regression suite (103 tests)** still passes unchanged.
- **TypeScript compiles cleanly** (`tsc --noEmit`) on both edited frontend
  files.
- **Other call sites** of the four endpoints were searched for across the
  frontend (`ReviewPanel.tsx` also calls the file-download endpoint) —
  confirmed it already sent an `Authorization` header before this change, so
  it needed no update.
- **`require_same_tenant`'s "graceful" exemption was revisited during the
  adversarial pass** (see Bypass 1 above) — the half of it that exempted
  *unassigned callers* was a live vulnerability and has been removed; the
  half that exempts *untenanted resources* (true legacy data) was
  deliberately preserved and has a regression test proving it still works.
- **No new dependencies or schema changes.** One migration-shaped concern:
  `create_tenant` now writes `current_user.tenant_id` in the same request —
  no schema change, but worth knowing it's no longer a read-only endpoint for
  the calling user's own row.
- **Temp/test artifacts** (`audit_os.db`, `pdf_debug.log`, ephemeral test
  SQLite files) were confirmed already `.gitignore`d or manually cleaned up;
  nothing new is tracked by git as a result of this work.

## Findings NOT fixed in this phase (explicitly out of scope)

Per instructions, only the 5 Critical findings were addressed. The following
remain open and were **not** touched:
- High: unauthenticated `/api/tasks/{task_id}/review` and `/observability`;
  missing tenant check on `accept-correction`; Zip Slip in batch upload;
  CORS `*` + credentials fallback.
- Medium/Low: JWT default-secret fallback outside `production` env, disabled
  TLS verification on the Redis broker, unpurged git history, missing
  `.dockerignore`/Docker hardening, absence of CI/CD, missing frontend/API
  test coverage beyond what was added here, unpinned dependencies, Sentry
  `send_default_pii=True`.

These map to `security/phase-2` and later workflow stages and should be
scoped as separate work.

---

## Phase 1 Review (Principal Engineer pass)

A final read-through of every modified file, done as a reviewer who didn't
write the code — not another implementation pass. Verified: authorization
consistency across the codebase, whether the new tests assert behavior vs
implementation, whether every security change has a test, naming/comments,
and whether anything unrelated changed. This pass surfaced two real findings
that the earlier adversarial round did not catch, documented honestly below
rather than silently fixed.

### What I am most confident about

- **Every one of the 5 Critical findings was independently re-derived from
  source**, not trusted from the audit report, and every fix (including the
  3 adversarial-round bypasses) was proven exploitable with a live
  reproduction against the running app *before* being patched, then
  reproduced again to confirm closure. Nothing in this phase was "added a
  check and assumed it worked."
- **The new test suite exercises behavior, not implementation.** All 26 tests
  drive the real FastAPI app through `TestClient` over HTTP and assert on
  response status codes and actual persisted DB state after the call (e.g.
  `db.refresh(item); assertEqual(item.taxable_value, ...)`) — no mocking of
  internals, no asserting on call counts or private method invocations.
  Cross-checked against every security-relevant code change: each one
  (`register` role denylist, traversal containment, `update_item` auth +
  tenant check + field denylist, `export_to_excel` auth + tenant check,
  `require_same_tenant` tightening, `assign_user_to_tenant` scoping,
  `create_tenant` auto-assign) has at least one dedicated test, and the two
  legitimate frontend flows that could have silently broken (self-serve
  firm creation, inviting a colleague) are both tested end-to-end, not just
  the attack path.
- **The `assign_user_to_tenant` fix reused an existing convention instead of
  inventing one.** The scoping check I added
  (`current_user.role == "owner" and current_user.tenant_id != tenant_id`) is
  character-for-character the same pattern already used by its three sibling
  endpoints (`list_tenant_users`, `remove_user_from_tenant`, `update_tenant`).
  That consistency was verified by grep, not assumed.
- **Nothing unrelated changed.** The repo had substantial pre-existing,
  uncommitted work in progress (Google Drive sync batching/subfolder
  features) before this phase started. Diffed every touched file line-by-line
  against that baseline; my edits are isolated to the specific
  functions/lines documented above, and the pre-existing WIP is untouched.
- **The full pre-existing 103-test regression suite and a TypeScript compile
  pass cleanly after every round of changes** (initial fixes, adversarial
  fixes, and this review found no code that needed further changes to keep
  them green).

### What I found in this review that earlier rounds missed

**1. `GET /api/jobs/{batch_id}/files/{filename:path}` has no tenant-isolation
check at all — reproduced live during this review.** This is the same
endpoint patched for path traversal (Critical #3). It requires *a* valid JWT
(`get_current_user`) but never calls `require_same_tenant`, unlike every
other resource-by-ID endpoint in the file. A user from Tenant B, given or
guessing Tenant A's `batch_id`, can currently download Tenant A's uploaded
PDFs:

```
tenant B user reading tenant A file: 200 35   (bytes of tenant A's PDF returned)
```

This was not one of the 5 enumerated Criticals (that finding was specifically
about path traversal, which is fixed and verified), and the earlier
adversarial round didn't catch it because that round was scoped to
*bypassing the fixes I had just implemented*, not auditing untouched
authorization gaps in a file I happened to be editing for an unrelated
reason. It should have been checked given how directly comparable this
endpoint is to the two I did fix.

> **UPDATE — reclassified and fixed.** Originally left open ("flagged for
> Phase 2") since this review pass was scoped as read-only. On review, this
> was reclassified as a Phase 1 blocker — it's a direct tenant-confidentiality
> failure on data already in scope this phase, not a new category of work —
> and fixed in a dedicated follow-up implementation pass. See
> "3a. Missing tenant isolation on the same file-download endpoint" above for
> the fix, live re-verification, and the 2 new regression tests
> (`test_cross_tenant_file_access_rejected`,
> `test_nonexistent_batch_returns_404_not_leaked_files`). The rest of this
> review section is left as originally written, since it reflects what was
> true and known at the time of the review; treat any later reference to this
> item in "Phase 2" or "assumptions" below as superseded by this update.

**2. Three of my four frontend `Authorization` header edits are redundant.**
`frontend/src/components/AuthGuard.tsx` monkey-patches `window.fetch` at
module load time to auto-inject `Authorization: Bearer <token>` into every
`fetch()` call targeting the API, for the entire app (it's wrapped around
everything via the root `layout.tsx`). This means the original, unmodified
`PUT /api/items/...` and `GET /api/export/...` calls in
`invoice-extractor/page.tsx` were almost certainly already being
authenticated at runtime, even though their source showed no explicit
`Authorization` header — my earlier "the frontend was calling these
without auth" diagnosis was based on reading the fetch call's source, not on
knowing about this global interceptor. The explicit headers I added there are
harmless (the interceptor skips injection if a header is already present,
so there's no conflict) but duplicate a concern the app already handles
globally. The one edit that **was** strictly necessary is the
`google-drive-sync/page.tsx` `downloadExcel` rewrite — its original
implementation used `<a href>` anchor-click navigation, which does **not**
go through `window.fetch` and therefore bypasses the interceptor entirely;
converting it to a real `fetch()` call was required, and that call is now
also covered by the interceptor regardless of its own explicit header.
**Not reverted here** — removing the 3 redundant headers is a non-security
cleanup that this "no implementation" review pass shouldn't perform, but the
`SECURITY_REMEDIATION_PHASE1.md` narrative above should be read with this
correction in mind.

### Authorization model consistency — verified across the codebase

Tabulating every `require_same_tenant` / `RoleChecker` / inline scoping check
in `main.py` confirms two consistent, intentional tiers:
- **Read/export endpoints** (`get_job_status`, `export_to_excel`,
  `export_gstr1_json`, `get_duplicate_invoices`, etc.): `get_current_user` +
  `require_same_tenant` — any authenticated member of the resource's tenant
  may read it.
- **Mutation endpoints** (`update_item`, `upload_batch`): `RoleChecker([...])`
  (a specific role list) + `require_same_tenant` — only certain roles may
  write, and only within their own tenant.
- **Tenant-admin endpoints** (`assign_user_to_tenant`, `list_tenant_users`,
  `remove_user_from_tenant`, `update_tenant`): `RoleChecker(["owner",
  "developer"])` + an inline "owner must already belong to this exact
  tenant" check (developer bypasses, by design — see `RoleChecker`).

This model is coherent and my fixes fit it without introducing a new shape.
The one inconsistency found — `get_pdf_file` sitting in the first tier by
function but missing its `require_same_tenant` call — is now fixed (see
"3a." above), bringing it in line with the rest of the tier.

### Technical debt remaining

- **The "owner must belong to this tenant" check is now duplicated
  verbatim 4 times** (`assign_user_to_tenant`, `list_tenant_users`,
  `remove_user_from_tenant`, `update_tenant`) — 3 pre-existing, 1 added by
  this phase's fix, deliberately matching the existing pattern rather than
  introducing a 5th shape. It should be extracted into a shared helper
  (e.g. `require_owner_of_tenant(current_user, tenant_id)`) the same way
  `require_same_tenant` already centralizes tenant-resource checks — right
  now a future 5th endpoint could easily copy it wrong or forget it, the
  same class of gap that caused Bypass 2 in the first place.
- **`update_item`'s field guard is a denylist (`{"id", "task_id"}`), not an
  allowlist.** It's complete for the current schema (those are the only two
  PK/FK columns on `SalesLineItem`/`PurchaseLineItem`), but it's fragile
  against schema drift — a new FK column added to either model later won't
  be protected unless someone remembers to add it here. An allowlist of the
  actual editable business fields would be more robust and wouldn't need to
  be revisited when the schema changes for unrelated reasons.
- **3 redundant frontend `Authorization` header additions** (see finding #2
  above) — harmless, but worth a small follow-up cleanup for consistency,
  paired with a comment on those pages (or in `utils/api.ts`, which already
  documents the interceptor) so the next person doesn't repeat the same
  "no explicit header = no auth" misreading.
- **The 403-vs-404 cross-tenant existence oracle** (a `PUT`/`GET` on a
  real-but-foreign-tenant resource returns `403`; on a nonexistent one,
  `404`) remains open. Pre-existing, app-wide convention, not introduced by
  these fixes — noted in the original remediation section and repeated here
  for completeness.

### What should be addressed in Phase 2

1. ~~Add `require_same_tenant` to `GET /api/jobs/{batch_id}/files/{filename:path}`~~
   — **done.** Reclassified as a Phase 1 blocker and fixed in a follow-up pass
   (see "3a." above) rather than deferred to Phase 2.
2. Extract the duplicated owner-tenant-scoping check into a shared helper.
3. Migrate `update_item`'s field guard from a denylist to an allowlist.
4. Clean up the 3 redundant frontend `Authorization` headers once confirmed
   safe (they are, per the analysis above) — low priority, consistency-only.
5. Proceed with the original deferred High findings: unauthenticated
   `/api/tasks/{task_id}/review` and `/observability`; missing tenant check
   on `accept-correction`; Zip Slip in batch upload; CORS `*` + credentials
   fallback.
6. Decide and apply one consistent resolution to the 403-vs-404 enumeration
   oracle across every `require_same_tenant` call site, rather than
   per-endpoint.
7. **Re-audit the whole file for the `get_pdf_file` pattern**: grep every
   `@app.get/put/post/delete` route with an ID path parameter and manually
   verify each one calls `require_same_tenant` (or intentionally doesn't,
   with a comment saying why). Phase 1 and its adversarial round together
   covered the 5 enumerated Criticals and the bypasses of those specific
   fixes thoroughly, and the one gap they missed (`get_pdf_file`) is now
   fixed too, but none of these passes was an exhaustive sweep of the whole
   file's authorization surface — treat item 1 as one instance found, not
   proof no others exist.

### Architectural concerns discovered

- **`AuthGuard.tsx`'s global `window.fetch` monkey-patch is a significant
  hidden mechanism.** It silently rewrites every fetch to the API across the
  entire app, and its existence isn't discoverable from reading any
  individual page's source — you have to know to look in `AuthGuard.tsx`.
  This is precisely why the original remediation write-up in this document
  overstated the necessity of 3 of the 4 frontend edits. It's a reasonable
  pattern (centralizes token injection and 401 handling in one place) but is
  a trap for future auditing: "grep the page for an Authorization header" is
  not a reliable way to determine whether a frontend call is authenticated in
  this codebase. Worth a comment at the top of `main.py`'s route file, or a
  short architecture note, pointing this out explicitly.
- **No data-model support for tenant provenance.** `Tenant` has no
  `created_by` field, so there was no way to distinguish "the tenant I just
  created" from "any other tenant with the same emptiness profile" when
  designing the fix for Bypass 2. The fix taken (atomic self-assignment at
  creation time) sidesteps the need for provenance tracking entirely and is
  the right minimal fix, but it forecloses future flows like "an owner
  creates a tenant on behalf of a colleague who will actually run it" or
  "two co-founders both need to be assigned at creation time." If either
  becomes a real product requirement, this will need a proper `created_by`
  column and an explicit claim/invite flow rather than the current
  create-implies-assign shortcut.
- **Two parallel tenant-authorization mechanisms exist side by side**:
  `require_same_tenant` (a shared helper, used 6 places) and the inline
  "owner must belong to this tenant" check (copy-pasted 4 places). They
  express a very similar idea — does this caller have a legitimate
  relationship to this tenant — through two different code shapes. Phase 2's
  deduplication work (above) should also consider whether these two
  mechanisms can be unified rather than just deduplicating the second one in
  isolation.
- **The `hasattr`/`setattr`-against-client-supplied-field-name pattern**
  that caused Bypass 3 is a generic anti-pattern (dynamic mass assignment).
  `update_item` is the only place it's used in the code reviewed this phase,
  but if it's copied into a new endpoint later without awareness of why the
  denylist exists here, the same bug class reappears. Worth a short note in
  the file or a lint rule if this pattern is likely to recur.

### Assumptions this phase depends upon

- **The set of endpoints needing tenant isolation was found via grepping
  `require_same_tenant` and the auth dependencies already in place** — this
  is provably not exhaustive (`get_pdf_file` was a counter-example found by
  this review and has since been fixed). Phase 2 should not assume
  "everything reachable by ID is now protected" just because this one gap
  was closed; it should re-derive the list from every route with an ID path
  parameter, independent of what already happens to call the helper.
- **`RoleChecker`'s "developer bypasses every role check" behavior is
  intentional platform design**, not a bug — this is corroborated by the
  `User` model's own docstring (`"developer"` is documented as an ops/
  superadmin tier) and was treated as a design constraint to work within
  (e.g. `create_tenant`'s auto-assign deliberately excludes `developer`),
  not something to "fix."
- **`AuthGuard.tsx`'s global fetch interceptor is assumed to cover every
  page that needs it**, verified for `invoice-extractor` and
  `google-drive-sync` via the root `layout.tsx` wrap. Any future page
  rendered outside that layout (a standalone route, an embedded iframe view,
  a server action) would silently lose this protection and needs its own
  explicit `Authorization` header — this isn't hypothetical, it's exactly
  the anchor-click gap that made the `downloadExcel` fix necessary.
- **All new tests run against SQLite**, matching this repo's existing
  regression harness convention, not the Postgres/Supabase target used in
  staging/production (`DATABASE_URL` per `render.yaml`). Column-casting
  behavior (e.g. the `Float` coercion in `update_item`), JSON handling, and
  any Postgres-specific constraint behavior are unverified against the real
  production database engine. This is a pre-existing gap in this repo's
  testing story, not something introduced by this phase, but it's a load-
  bearing assumption worth stating plainly: these tests prove correctness
  against SQLite; Postgres-specific behavior is unverified.
- **No concurrency/race testing was performed** — e.g. two simultaneous
  `create_tenant` calls from the same never-assigned owner, or a
  `require_same_tenant` check racing a `remove_user_from_tenant` call on the
  same user. Tenant administration is a low-frequency, human-driven action
  in this product, so the risk is assessed as low, but it is an assumption,
  not a verified property.
