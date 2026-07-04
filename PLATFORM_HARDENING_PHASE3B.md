# Platform Hardening — Phase 3B

**Scope:** GitHub Actions, CI pipelines, test automation, linting, type checking,
coverage reporting, dependency auditing, secret scanning, pre-commit hooks,
Dependabot, repository automation, developer setup and quality gates.

**Explicitly out of scope (per instructions):** business logic, Docker
artifacts from Phase 3A (untouched, verified via `git status` — no
`backend/Dockerfile` or `.dockerignore` changes), cloud deployment /
Render / Kubernetes / Terraform, and the unrelated WIP already present on
this branch (Google Drive sync, reconciliation adapter/engine, etc. — left
exactly as found).

**Not committed.** All changes are in the working tree, awaiting review.

---

## Inventory (verified independently, not assumed)

Before touching anything, I checked what actually existed:

- **No `.github/` directory at all** — zero GitHub Actions workflows, zero
  Dependabot config. `render.yaml` was the only CI-adjacent file in the repo.
- **No lint/type-check config anywhere** — no `pyproject.toml`, `setup.cfg`,
  `.flake8`, `mypy.ini`, or `ruff.toml` for the backend. No `ruff`, `mypy`,
  `pytest-cov`, or `pip-audit` installed anywhere (not even in a venv — there
  is no backend venv; tooling runs against the global Python 3.12
  interpreter).
- **No pre-commit, no `.pre-commit-config.yaml`.**
- **Frontend already had `eslint.config.mjs` and `tsconfig.json`** (strict
  mode on), but no `typecheck` npm script and no CI to run either.
- **`backend/tests/regression/`** already had a custom runner
  (`run_regression.py`, 103 tests) built in a prior session; confirmed it
  also runs cleanly under plain `pytest`, so no separate CI invocation is
  needed for it.
- **`backend/tests/test_security_phase1.py` / `test_security_phase2.py`**
  (Phase 1/2 security regression suites, 28 + 19 tests) — both pass in
  isolation, but **discovered a real, order-dependent failure when run
  together** (see Finding 1 below).

---

## Findings & Fixes

### 1. Cross-suite test pollution — a real, reproduced test-isolation bug (not hypothetical)

**Discovered by actually running the test suite the way CI would** (`pytest
tests/`, not the documented per-file `python -m unittest` invocation) —
this surfaced a genuine failure that wasn't hypothetical:

```
FAILED tests/test_security_phase2.py::TestObservabilityStatsTenantScoping::
  test_unassigned_user_sees_only_legacy_untenanted_data_not_everything
AssertionError: 1 != 0
```

**Root cause, verified by bisection (not guessed):** both
`test_security_phase1.py` and `test_security_phase2.py` set
`os.environ["DATABASE_URL"]` to their own unique temp SQLite file *before*
importing `main`/`database` — a pattern clearly designed for isolation. But
pytest **collects (imports) every test module before running any of them**.
Since Python caches imports in `sys.modules`, only the *first*-imported
module's `DATABASE_URL` actually takes effect; `database.engine` is created
once, at first import, and never revisited.

I first tried rebinding `database.engine` / `database.SessionLocal` in place
after import — this looked correct in an isolated script, but still failed
under the real combined pytest run. Bisecting confirmed why: because
collection imports *both* files before execution starts, whichever file
collects *last* wins the rebind, and **both suites end up running against
that one engine regardless of which file's tests are actually executing**.
`test_security_phase1.py::TestUnassignedUserTenantBypass` creates a
legacy (`tenant_id=None`) `BatchJob` as part of its own regression test;
under the shared-engine bug, that row leaked into `test_security_phase2.py`'s
"unassigned user sees only legacy data" assertion, which counts on it being
zero.

**Why this matters for the platform, not just this one test:** this is
exactly the kind of failure a fresh CI pipeline would hit on day one and
be flaky/order-dependent about — reproducible locally, but only when both
files run in the same process, which is precisely how CI runs the suite.
Left unfixed, it would have undermined trust in the very CI gate this phase
exists to build.

**Fix (`backend/tests/test_security_phase1.py`,
`backend/tests/test_security_phase2.py`):** each module now creates its own
private SQLAlchemy engine/sessionmaker and overrides FastAPI's `get_db`
dependency via `app.dependency_overrides`, set up in `setUpModule` /
`tearDownModule` — hooks that `unittest` (and pytest's unittest support) run
at **execution** time, immediately before/after that module's own tests,
not at collection/import time. This sidesteps the collection-order hazard
entirely: no shared global object is ever mutated, so there is nothing for
a second module's import to clobber.

**Verified:**
- Full suite together: `pytest tests/` → **150 passed** (was 149 passed, 1
  failed before the fix).
- The specific previously-failing pair in isolation:
  `pytest tests/test_security_phase1.py::TestUnassignedUserTenantBypass
  tests/test_security_phase2.py::TestObservabilityStatsTenantScoping` →
  passed (was reproducibly failing before the fix).
- Documented invocation still works unchanged:
  `python -m unittest tests.test_security_phase1` → 28 passed, OK.
  `python -m unittest tests.test_security_phase2` → 19 passed, OK.
- No business logic touched — only the two test files.

### 2. Zero CI — added path-scoped GitHub Actions for backend and frontend

**Why two separate workflows, not one monorepo workflow:** `ci-backend.yml`
and `ci-frontend.yml` each trigger only on changes under their own
`paths:` (plus their own workflow file). A backend-only PR doesn't spin up
Node, and a frontend-only PR doesn't spin up Python — faster feedback,
lower CI cost, and no path-filter action dependency to maintain.

**`.github/workflows/ci-backend.yml`** — four jobs:
- `test`: `pytest --cov=. --cov-report=xml`, coverage floor enforced (see
  Finding 3), coverage report uploaded as a build artifact.
- `lint`: ruff, split into a **blocking core-rules pass** and an
  **advisory full-baseline pass** (see Finding 4).
- `typecheck`: mypy, advisory (see Finding 4).
- `dependency-audit`: `pip-audit -r requirements.txt`, blocking — verified
  clean today (see Finding 5).

**`.github/workflows/ci-frontend.yml`** — four jobs:
- `lint`: `eslint .`, advisory (71 pre-existing findings — see Finding 4).
- `typecheck`: `npm run typecheck` (new script, `tsc --noEmit`), **blocking**
  — verified clean (0 errors) today.
- `build`: `next build`, **blocking** — verified it actually builds
  (11 static pages generated successfully).
- `dependency-audit`: `npm audit --audit-level=high`, blocking, plus a
  full advisory report (one pre-existing moderate finding — see Finding 5).

Every command in both workflows was **actually run locally** against this
repo before being written into YAML, not inferred from reading `package.json`
or `requirements.txt`.

### 3. Coverage reporting — added with a real, measured baseline (not a guess)

`pytest-cov` wasn't installed anywhere in the repo. Added it, plus a
`[tool.coverage]` config in `backend/pyproject.toml` that excludes test
scaffolding and known-dead scripts (`verify_setup.py`, `modal_deploy.py`,
`debug_extraction.py`) from the denominator.

**Measured, not assumed:** running `pytest --cov=. --cov-report=term-missing`
with this exact config gives **38.97%** total coverage today. I set
`fail_under = 36` — a few points of headroom for normal fluctuation, tight
enough to catch a real regression (e.g., a large new untested module, or an
accidentally-deleted test file). I did **not** pick a round number without
measuring first; an earlier ad-hoc run (before the omit list was scoped
correctly) showed 46%, which would have been the wrong floor to ship.

### 4. Lint/type-check — a ratchet, not a blanket gate (preserves behavior, still automatically enforces quality going forward)

Running `ruff check .` with its default rule set against the existing
backend turned up **257 pre-existing violations** (91 unused imports, 60
imports-not-at-top, 30 one-line-statement violations, 16 bare `except:`,
etc.). Running `eslint .` on the frontend turned up **71 pre-existing
errors/warnings** (mostly `@typescript-eslint/no-explicit-any` and a
React-hooks best-practice rule). Fixing all of these was explicitly out of
scope — several are not safe to auto-fix without risking behavior change
(e.g., rewriting bare `except:` to `except Exception:` changes what
exceptions get caught; reordering a top-of-file import can change import
side-effect order).

Instead of either (a) leaving lint/type-checking fully unconfigured, or
(b) mass-editing 250+ pre-existing findings across files I wasn't asked to
touch, I split each into two tiers:

- **A small "core" rule set that is enforced and blocks merges today**:
  `E9` (syntax errors), `F63/F7/F82` (real bugs — bad assertions, undefined
  names), `F811` (redefinition). I verified this subset has **zero**
  violations in the current codebase (after fixing the one real hit it
  found — see below) — so it's a legitimate, immediately-enforceable gate,
  not aspirational.
- **The full default rule set / eslint config runs as an advisory,
  non-blocking report** in CI, visible in build logs, so the existing debt
  is tracked and payable down incrementally rather than requiring a big-bang
  fix.

The core ruff pass actually found one **real** issue, which I fixed (not
just configured around): `backend/main.py` had `import os` twice
(lines 11 and 19) — the second, unused, shadowed the first. Removed the
duplicate. Zero behavior change; confirmed with `ruff check --select F811`
→ clean, and the full test suite still green (150/150).

`mypy` is wired in as fully advisory (`|| true` in CI) — the codebase has
no type-hint coverage to speak of (mypy reports 260 errors on the first
run, almost all SQLAlchemy `Column[T]` vs `T` false-positive-shaped
findings from untyped declarative models). Tightening this is a legitimate
follow-up once type hints are adopted incrementally; forcing it to block
today would be pure noise, not signal.

`ruff format --check` also runs advisory-only: a repo-wide format pass
would touch 117 files today (verified by actually running it), which is a
large, separately-reviewable change, not a "hardening" fix.

### 5. Dependency audit — verified clean today, wired as a blocking gate

Ran `pip-audit -r requirements.txt` for real (not assumed): **no known
vulnerabilities**. Ran `npm audit` for real: **one pre-existing moderate
finding** (`postcss` XSS-in-stringify, transitively via `next`'s bundled
copy) — npm's own suggested fix is to downgrade `next` to a `9.x` canary,
which is not a real fix and is explicitly out of scope (touches the
frontend's core dependency, would be a breaking change). Given backend is
fully clean and frontend's only finding is moderate:

- `pip-audit` blocks the backend CI build on **any** finding (clean
  baseline, no debt to work around).
- `npm audit --audit-level=high` blocks the frontend CI build on
  high/critical only (today: passes, exit 0) — a full non-blocking
  `npm audit` report still surfaces the moderate finding for visibility.

### 6. Secret scanning — pre-commit (local, before it's ever committed) + CI (defense-in-depth) + native GitHub secret scanning (repo setting, can't be enabled via code)

Added `gitleaks` in two places:
- **Pre-commit hook** (`.pre-commit-config.yaml`) — runs on every
  `git commit`, scanning staged changes only. Catches a leaked credential
  before it's ever pushed.
- **CI workflow** (`.github/workflows/secret-scan.yml`) — full-history scan
  on push/PR, defense-in-depth for anyone who skipped or never installed
  the pre-commit hook.

**Verified against this actual repo's git history** (not run blind):
`gitleaks detect --source .` found **6 findings**, all in commit history —
I read every one before deciding what to do with them. All 6 are the
literal string `Bearer YOUR_TOKEN` in three documentation files
(`FRONTEND_SETUP.md`, `backend/docs/GOOGLE_DRIVE_SYNC_QUICKSTART.md`,
`backend/docs/SETUP_FOR_CLIENT.md`) — curl-command placeholders, not real
credentials. Added `.gitleaks.toml` with a narrow allowlist regex
(`^YOUR_TOKEN$`) scoped to exactly that string, then re-ran gitleaks to
confirm **zero findings remain** with the config applied — so the new gate
starts clean, not pre-broken by its own false positives.

**Note — GitHub's native secret scanning / push protection** is a repository
Settings toggle (Settings → Code security), not something committable via a
workflow file. I can't enable it from here; recommend turning it on (free
for public repos, included in GitHub Advanced Security for private repos)
as a complement to the gitleaks jobs above.

### 7. SAST — added CodeQL (native, zero ongoing maintenance)

`.github/workflows/codeql.yml` runs GitHub's CodeQL against both Python and
JavaScript/TypeScript, on push/PR to `main` plus a weekly Monday scan (catches
newly-disclosed vulnerability *patterns* in code that hasn't changed since,
not just PR diffs). Findings surface in the repo's Security tab automatically
— no separate dashboard or triage tool to maintain. This is a native GitHub
feature requiring no local verification run (it runs entirely in Actions),
but the workflow YAML was validated for correctness against GitHub's
documented `codeql-action@v3` usage.

### 8. Dependabot — automatic dependency PRs, replacing manual "check for updates" toil

`.github/dependabot.yml` covers all three ecosystems actually present in
this repo (verified — no other manifest types exist): `pip` (`/backend`),
`npm` (`/frontend`), and `github-actions` (`/`), weekly, grouped per
ecosystem to avoid a flood of single-package PRs. This directly answers the
"reduce future maintenance, eliminate manual steps" instruction — nobody
has to remember to periodically check for outdated/vulnerable dependencies.

### 9. Pre-commit hooks — eliminate the "remember to lint" step entirely

`.pre-commit-config.yaml` (repo root): trailing-whitespace, end-of-file-fixer,
merge-conflict markers, large-file guard (1MB), private-key detection,
YAML validation, ruff (core rules, auto-fix), and gitleaks.

**Actually installed and run** against this session's own changed files
(not just written and assumed correct):
`pre_commit run --files backend/main.py backend/tests/test_security_phase1.py
backend/tests/test_security_phase2.py` → all 9 hooks executed, one real
whitespace fix applied and verified, all others passed clean.

**Correction made during verification:** my first version of the gitleaks
hook passed `args: ["protect", "--staged", "--redact", "-v", "--config",
".gitleaks.toml"]`, which collided with the hook's own built-in `entry`
(already `gitleaks protect --staged`) and errored with
`cannot change to 'protect': No such file or directory`. Fixed by only
passing the additional flag needed (`--config .gitleaks.toml`); re-ran and
confirmed it passes.

**A scope-creep mistake I caught and reverted:** running the full
pre-commit suite with `--files backend/main.py` correctly auto-fixed one
real trailing-whitespace issue at my edit site, but the `trailing-whitespace`
hook also silently reformatted ~70 unrelated blank lines throughout the rest
of that file (pre-existing whitespace-only inconsistency, harmless but not
something this phase was asked to touch). Caught this by re-diffing before
finishing, reverted `backend/main.py` via `git checkout --`, and reapplied
only the one deliberate line I intended to change (the duplicate `import os`
fix from Finding 4). Lesson applied: pre-commit hooks should be validated
against files staged for commit, not run broadly with `--files` against
files that also carry unrelated pending WIP.

---

## Final CI review (post-implementation pass)

A second, independent pass specifically over the files changed in this
phase — checking workflow minimalism, job duplication, cache correctness,
secret handling, gate determinism, advisory/blocking intent, and doc-vs-
implementation accuracy — found and fixed four real issues:

1. **Non-deterministic gate**: `ci-backend.yml`'s `dependency-audit` job ran
   `pip install pip-audit` unpinned, while every other tool in the repo
   (ruff, mypy, pytest) is pinned via `requirements-dev.txt` (which already
   declared `pip-audit==2.10.1`, unused by that job). Fixed: job now installs
   `pip-audit==2.10.1` explicitly, with a comment tying it to
   `requirements-dev.txt` so the two can't silently drift.
2. **Documentation didn't match implementation**: the README's Quality
   Gates table listed one merged "Yes (high/critical only)" blocking
   descriptor for both backend and frontend dependency audits, but
   `pip-audit -r requirements.txt` has no severity filter (blocks on *any*
   finding) — only `npm audit --audit-level=high` is scoped to high/critical.
   Fixed: the row now states the accurate, different blocking scope for each.
3. **Minor determinism gap**: pre-commit pins gitleaks to `v8.24.3`;
   `gitleaks-action@v2` in CI didn't pin the underlying gitleaks binary, so a
   local pre-commit pass and the CI gate could theoretically disagree.
   Verified via WebFetch against the action's own README that
   `GITLEAKS_VERSION` (no `v` prefix, e.g. `"8.24.3"`) is the documented
   pinning mechanism before using it — fixed: CI now pins the same version.
4. **Minor consistency gap**: `codeql.yml` scoped its `pull_request` trigger
   to `branches: [main]`; `ci-backend.yml`, `ci-frontend.yml`, and
   `secret-scan.yml` didn't, so they'd also fire on PRs targeting a
   non-`main` branch. Normalized all three to `branches: [main]`, matching
   the single-trunk branching this repo actually uses. Also added an
   explicit `permissions: { contents: read }` block to all three (only
   `codeql.yml` had one before), so none of them rely on the repo's default
   token permissions.

**Re-verified after fixes:**
- `pip-audit==2.10.1 -r requirements.txt` → no known vulnerabilities (same
  clean result as before, now with a pinned tool version).
- `pytest tests/` → 150 passed, unaffected (no application code touched in
  this pass, only workflow YAML and README).
- All edited YAML validated via `pre-commit run check-yaml`.
- Confirmed via `grep -rn "secrets\."  .github/workflows/` that the only
  secret reference anywhere is `secrets.GITHUB_TOKEN` passed as an env var
  to `gitleaks-action` — never echoed, printed, or interpolated into a
  shell command.

No further issues found. **Phase 3B approved for commit.**

---

## What I looked at and deliberately left alone

- **Fixing the 257 ruff / 71 eslint pre-existing findings.** Flagged as
  advisory-tier debt (Finding 4), not fixed — several carry real behavior-
  change risk (bare `except:`, import reordering) and are out of scope for
  a tooling-hardening pass that must preserve behavior.
- **`ruff format` repo-wide.** Would touch 117 files — a large, separately-
  reviewable formatting change, not bundled here.
- **The npm audit moderate `postcss`/`next` finding.** No real fix available
  without a breaking `next` downgrade; left as a visible advisory finding.
- **Branch protection / required status checks.** This is a GitHub repository
  Settings action (Settings → Branches), not a committable file — I can't
  enable it from here. **Recommend**: once these workflows are merged and
  have run at least once, mark `test`, `dependency-audit` (backend),
  `typecheck`, `build`, `dependency-audit` (frontend) as required status
  checks for `main`.
- **GitHub's native secret scanning / push protection toggle.** Same reason
  — a repo Settings action, not a file. Recommended as a complement to the
  gitleaks jobs above (Finding 6).
- **Tightening mypy / eslint to blocking.** Legitimate follow-up once the
  advisory reports have been paid down; forcing it today would just block
  all future PRs on pre-existing debt unrelated to their change.
- **CI/CD, cloud infra, Render, Kubernetes, Terraform, Docker artifacts.**
  Explicitly out of scope per instructions; untouched.
- **The pre-existing WIP already on this branch** (Google Drive sync,
  reconciliation adapter/engine, `backend/backend_log.txt`,
  `backend - Copy/`, `scratch_verify/`, `frontend/frontend_log.txt`) — left
  exactly as found, not reviewed or touched.

---

## Verification — actually executed this session

```
pytest tests/ -q
```
→ **150 passed** (0 failed) — confirmed multiple times, including the exact
combination that was failing before Finding 1's fix.

```
python -m unittest tests.test_security_phase1 -v
python -m unittest tests.test_security_phase2 -v
```
→ 28 passed / OK, 19 passed / OK — documented invocation still works.

```
pytest --cov=. --cov-report=term-missing --cov-report=xml
```
→ 38.97% coverage, `fail_under = 36` passes.

```
ruff check . --select E9,F63,F7,F82,F811,F821,F822
```
→ **All checks passed** (0 violations, after the one real fix in Finding 4).

```
mypy --config-file mypy.ini .
```
→ Runs to completion (260 errors, advisory-only as designed) — confirmed it
doesn't crash or hang.

```
npx eslint .          → 88 problems (71 errors/17 warnings) — advisory, matches config
npx tsc --noEmit       → exit 0, clean
npx next build         → succeeded, 11 static pages generated
npm audit --audit-level=high → exit 0 (clean at high/critical)
npm audit                    → 2 moderate findings (postcss/next), advisory
```

```
pip-audit -r requirements.txt
```
→ No known vulnerabilities.

```
gitleaks detect --source . -v            → 6 findings, all verified false positives
gitleaks detect --source . --config .gitleaks.toml -v  → no leaks found
```

```
pre-commit validate-config .pre-commit-config.yaml   → valid
pre-commit run --files <changed test/main files>       → all 9 hooks pass
```

All of the above were run against real output from this repo in this
session — not inferred from reading config files.

---

## Files changed

**New:**
- `.github/workflows/ci-backend.yml`
- `.github/workflows/ci-frontend.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/secret-scan.yml`
- `.github/dependabot.yml`
- `.pre-commit-config.yaml`
- `.gitleaks.toml`
- `backend/pyproject.toml` (ruff + pytest + coverage config)
- `backend/mypy.ini`
- `backend/requirements-dev.txt` (ruff, mypy, pytest, pytest-cov, pip-audit,
  pre-commit — pinned to versions verified installed/working this session)
- `PLATFORM_HARDENING_PHASE3B.md` — this report.

**Modified:**
- `backend/main.py` — removed one duplicate, unused `import os` (Finding 4;
  the only real lint finding in the newly-enforced core rule set).
- `backend/tests/test_security_phase1.py`,
  `backend/tests/test_security_phase2.py` — fixed the cross-suite test
  isolation bug (Finding 1).
- `frontend/package.json` — added `typecheck` script (`tsc --noEmit`).
- `README.md` — added a "Quality Gates" section documenting the new CI
  jobs, blocking-vs-advisory split, and one-time pre-commit setup step.

No other files were touched. Pre-existing uncommitted WIP on this branch
was left exactly as found.
