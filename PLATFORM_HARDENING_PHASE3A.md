# Platform Hardening — Phase 3A

**Scope:** Dockerfiles, .dockerignore, startup scripts, health/readiness checks, config validation, env var handling, container security, image optimization, local developer experience.

**Explicitly out of scope (per instructions):** CI/CD, GitHub Actions, cloud infra, Render, Kubernetes, deployment config (`render.yaml` untouched), business logic, and the unrelated WIP already present on this branch (Google Drive sync, reconciliation adapter, etc. — left untouched).

**Not committed.** All changes are in the working tree, awaiting review.

---

## Inventory (verified independently, not assumed)

- One Dockerfile in the repo: `backend/Dockerfile`. No frontend Dockerfile exists.
- No `docker-compose*.yml` anywhere in the repo.
- No `.dockerignore` anywhere in the repo (root or `backend/`) — **fixed**.
- Local dev startup is via `START_ALL_LINUX.sh` / `START_ALL_WINDOWS.bat`, which run Celery, Uvicorn, and Next.js directly (no Docker). Reviewed for correctness; no changes needed — they already fail fast on missing Redis/Node/Python and give actionable error messages.
- Config validation for `JWT_SECRET_KEY` and `ALLOWED_ORIGINS` already fails closed in production (`backend/services/auth.py`, `backend/main.py`) from prior security work — reviewed, no gaps found, left as-is (business-logic-adjacent, not a container concern).
- No liveness/readiness route existed independent of Celery/Redis state — only `/api/health/workers`, which reports task-queue health but is unsuitable as a basic "is the process alive" container probe (would flap unhealthy any time Redis/Celery is down even though FastAPI itself is fine).

---

## Findings & Fixes

### 1. No `.dockerignore` — real secrets and dev artifacts get baked into the image

**Why it matters:** `backend/Dockerfile` does `COPY . .` with no `.dockerignore` anywhere in the repo. `.gitignore` only controls what `git` tracks — it has no effect on `docker build`. I verified `backend/.env` exists locally with live configuration (59 lines, 26 real key=value entries — Celery broker URL, Google Drive credentials paths, etc.), and confirmed `docker build` would copy it verbatim into an image layer. Anyone with pull access to that image — or access to a layer cache/registry — gets the secrets, and they persist in image history even if a later layer "removes" the file. Same problem for stray SQLite DBs (`antigravity.db`, `antigravity_v2.db`) and generated Excel output left in the working tree.

**Fix:** Added `backend/.dockerignore`, scoped to what's actually unneeded/unsafe in the image:
- `.git`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, venvs
- `.env` / `.env.*` (keeps `.env.example` via negation — that one's meant to ship)
- `*.db`, `*.sqlite*` (the app creates/opens its DB via `DATABASE_URL` at startup — verified in `backend/database.py`; nothing reads a pre-existing dev DB file at build time)
- `logs/`, `*.log`
- `data/output/` (generated Excel exports only)
- `docs/`, `tests/`, `scripts/` (dev-only; verified via grep that nothing in `main.py`/`celery_app.py`/`services/` imports from any of these three)

**What I deliberately did *not* exclude:** `data/vendor_profiles/*.json` and `data/beat_schedules.json`. I grepped first and confirmed `services/vendor_profile.py` and `celery_app.py` load these at runtime — excluding them would have broken vendor-profile extraction and the Celery Beat schedule. This is the kind of mistake a blanket `*.json` or `data/` exclusion would have caused, so I checked before writing the rule rather than after.

### 2. Container ran as root

**Why it matters:** The image had no `USER` directive, so the Uvicorn process — which parses untrusted uploaded PDFs/ZIPs — ran as root inside the container. Standard container-security baseline is to drop to an unprivileged user; it doesn't prevent every escape but removes a large class of "found a way out" severity escalation.

**Fix:** Added a dedicated `app` system user/group, `chown -R app:app /app` after all files are in place, then `USER app` before `EXPOSE`/`CMD`. Ordering matters: `pip install` still runs as root (so it can write to system site-packages), and the chown happens after `COPY . .` so the app user owns everything it needs to read/write (including the SQLite file it creates in `/app` and `data/` at runtime).

### 3. No `HEALTHCHECK`, and no liveness endpoint that didn't depend on Celery/Redis

**Why it matters:** Without `HEALTHCHECK`, `docker ps` / `docker inspect` can't tell you the container is actually serving traffic — you only find out it's stuck when a request times out. The existing `/api/health/workers` endpoint was the only health route, but it reports Celery/Redis status, not "is Uvicorn alive" — using it as a container probe would mark the container unhealthy any time the task queue is down, even though the API itself is fine.

**Fix:**
- Added `GET /health` in `backend/main.py` — a bare liveness probe, no DB/Celery/Redis dependency, returns `{"status": "ok"}`. Left `/api/health/workers` untouched for task-queue readiness checks (different concern, different consumer).
- Added the request-logging middleware's existing skip-list entry for `/health` (it already skipped `/`, `/docs`, `/openapi.json` to keep logs clean — same treatment).
- Wired `HEALTHCHECK` in the Dockerfile to hit it, using Python's stdlib `urllib` instead of installing `curl`/`wget` — keeps the image from growing by a new apt package just for the probe.

### 4. Redundant/dead package installs in the Dockerfile

**Why it matters:** `RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi python-multipart pydantic-settings` re-specified `uvicorn`, `fastapi`, and `python-multipart` even though `requirements.txt` already declares `fastapi[standard]` (which pulls in `uvicorn[standard]` and `python-multipart` as extras) and `python-multipart` directly. `pydantic-settings` isn't imported anywhere in the codebase (verified via grep for `pydantic_settings`/`BaseSettings` — zero matches) — it was dead weight.

**Fix:** Simplified to `pip install --no-cache-dir -r requirements.txt`. No behavior change — same packages end up installed, just without the redundant/dead specifiers cluttering the layer and the pip resolution.

### 5. Build-blocking: `apt-get install libgl1-mesa-glx` fails on the current base image

**Discovered by:** actually running `docker build` (see "Verification" below) — this is a real, reproduced build failure, not an inferred one.

**Why it matters:** `libgl1-mesa-glx` is a transitional dummy package Debian removed starting with **trixie** (Debian 13). `python:3.10-slim` tracks the current Debian release, and by the time of this build it resolves to trixie, so `apt-get install -y --no-install-recommends build-essential libgl1-mesa-glx libglib2.0-0` fails with `E: Unable to locate package libgl1-mesa-glx` before the build ever reaches the `pip install` layer. (Independently, a `pip download --platform manylinux2014_x86_64 --python-version 310` dry run of every package in `requirements.txt` confirmed the Python dependency layer resolves cleanly — the apt layer was the only real suspect, which is exactly where the failure was.)

**Fix:** `backend/Dockerfile` — replaced `libgl1-mesa-glx` with the two packages it used to depend on, `libgl1` (GL dispatch library) and `libglx-mesa0` (the actual Mesa GL implementation), preserving identical runtime GL capability under the current, correct package names.

### 6. Runtime-blocking: container crashes on startup — hard top-level `import easyocr`

**Discovered by:** running the built image and inspecting `docker logs` after the container reported `unhealthy` — a real crash, not a guess.

**Why it matters:** `backend/services/document_core.py` had `import easyocr` at module top level (line 18), executed unconditionally the moment `main.py` imports `document_core`. But `easyocr` is explicitly commented out in `requirements.txt` as an **optional** dependency (`# OCR (Optional — install if needed) ... easyocr>=1.7.0 # Tier 3 OCR (ML-based, ~250MB download)`), so it's never installed in the image. Result: `uvicorn` crash-loops on startup with `ModuleNotFoundError: No module named 'easyocr'`, nothing ever binds to port 8000, and the container sits `unhealthy` forever. This bug was invisible in every check I ran before actual Docker execution was available, because `easyocr` happens to be installed in the local host Python environment (confirmed: `python -c "import easyocr"` succeeds on the host) — it only surfaces in the image, which correctly omits the optional dependency. This is precisely why "verify by actually executing" catches things "verify by reasoning" cannot.

**Fix:** `backend/services/document_core.py` — moved `import easyocr` from module top-level into `get_ocr_reader()`, the one function that uses it. This matches the lazy-import pattern the same file already uses for its other optional OCR dependency, `pytesseract` (imported inside functions at lines 657 and 696, not at module top). Behavior is unchanged when `easyocr` is installed (Tier 3 OCR still works identically); when it isn't installed, the failure now happens only if Tier 3 OCR is actually invoked, instead of crashing the entire application at import time. No business logic changed — only where the import statement lives.

---

## What I looked at and deliberately left alone

- **Multi-stage build to drop `build-essential` from the final image.** This is a legitimate image-optimization opportunity (most of the requirements — `pandas`, `psycopg2-binary`, `pymupdf`, `opencv-python-headless` — ship manylinux wheels for `python:3.10-slim` and likely don't need a compiler at all). Docker became available partway through this phase and was used to fix the two build/runtime bugs above, but a multi-stage refactor is a larger, separately-verified change than a build/health fix pass — restructuring the image into build and runtime stages, re-verifying every package still resolves, and confirming nothing relies on a build-time tool at runtime is its own piece of work, not a minimal fix. Deliberately left out of this pass to keep changes minimal; **recommend as a scoped follow-up**, not bundled here.
- **Pinning apt/base-image versions further** (e.g., a full `python:3.10.x-slim` digest pin) — would improve reproducibility but is a larger policy decision (digest pins require a maintenance process to bump); flagging rather than doing unilaterally.
- **`render.yaml`, CI/CD, deployment config** — explicitly out of scope.
- **The pre-existing `ENV OPENAI_API_BASE` / `MODEL_NAME` defaults baked into the image** — these are non-secret routing defaults (Groq endpoint + model name), not credentials; left as-is since changing them would alter runtime behavior.
- **The root-level `audit-os-production-*.json` GCP service-account key** — present locally but *not* git-tracked (verified via `git ls-files`) and outside the `backend/` Docker build context, so it isn't at risk of being baked into the image. No action needed here, noting it for awareness only.

---

## Verification — actually executed (Docker Desktop + WSL2, this session)

Docker Desktop was installed partway through this phase. Everything below is a real command I ran in this session, with real output — not inferred, not a checklist for someone else to run. `docker --version` → `Docker version 29.6.1, build 8900f1d`.

**Round 1 — build, as originally hardened:**
```
docker build -t auditos-backend:phase3a ./backend
```
Result: **failed** at the apt layer — `E: Unable to locate package libgl1-mesa-glx`. This is Finding 5 above. Fixed the Dockerfile, rebuilt.

**Round 2 — build after the apt fix:**
```
docker build -t auditos-backend:phase3a ./backend
```
Result: **succeeded**, exit code 0. `docker images auditos-backend:phase3a` → present, 424MB content size.

**Round 2 — run + health check:**
```
docker run -d --name auditos-backend-verify -p 8000:8000 auditos-backend:phase3a
docker inspect --format "{{.State.Health.Status}}" auditos-backend-verify
```
Result: `starting` → **`unhealthy`**. `docker logs auditos-backend-verify` showed the container crash-looping with `ModuleNotFoundError: No module named 'easyocr'` on every restart — the process never bound to port 8000, so every health probe got `ConnectionRefusedError`. This is Finding 6 above. Fixed `document_core.py`, rebuilt.

**Round 3 — full re-verification from a clean container, after both fixes:**
```
docker build -t auditos-backend:phase3a ./backend
```
→ exit 0, all layers built (apt layer and pip layer both cached from the correct prior build; `COPY . .` and the `useradd`/`chown` layer rebuilt fresh).
```
docker run -d --name auditos-backend-verify -p 8000:8000 auditos-backend:phase3a
docker inspect --format "{{.State.Health.Status}}" auditos-backend-verify
```
→ `starting` (poll 1) → **`healthy`** (poll 2, ~10s later — well inside the 15s `start-period`).
```
curl -s -o - -w "\nHTTP_STATUS:%{http_code}\n" http://localhost:8000/health
```
→ `{"status":"ok"}` / **`HTTP_STATUS:200`**
```
docker exec auditos-backend-verify python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/health', timeout=3); print(r.status, r.read())"
```
→ **`200 b'{"status":"ok"}'`** — confirms the exact probe Docker's own `HEALTHCHECK` runs succeeds from inside the container's network namespace, not just from the host.
```
docker exec auditos-backend-verify whoami && docker exec auditos-backend-verify id
```
→ **`app`** / **`uid=999(app) gid=999(app) groups=999(app)`** — confirms the non-root user from Finding 2 is actually in effect at runtime, not just present in the Dockerfile.

`docker logs auditos-backend-verify` on the healthy container showed only expected, non-fatal startup warnings (no `.env` was passed to this bare smoke-test run, so these are correct-and-graceful, not bugs):
- `Failed to initialize GCS client with default credentials` — expected, no GCS credentials supplied to this smoke test.
- `[TaskQueue] WARNING: CELERY_BROKER_URL not set. Using in-process BackgroundTasks` — expected, existing designed fallback.
- `[AUTH WARNING] JWT_SECRET_KEY is using the default development secret` — expected, existing fail-open-in-dev/fail-closed-in-prod behavior from prior security work, untouched.

Container removed after verification (`docker rm -f auditos-backend-verify`) — nothing left running.

**Regression suite, re-run after the `document_core.py` change** (to confirm moving the `easyocr` import didn't break anything on the host, where `easyocr` happens to already be installed):
```
python backend/tests/regression/run_regression.py
```
→ **103/103 passed**, 0 failed.

### docker-compose.yml / frontend Dockerfile — judged not genuinely required, not added

Re-confirmed: no `docker-compose*.yml` and no frontend `Dockerfile` exist anywhere in this repo. Now that Docker is actually available, I could add either — but didn't, because neither is *required*: the existing local dev flow (`START_ALL_LINUX.sh` / `START_ALL_WINDOWS.bat`, reviewed in Phase 3A's first pass) already starts Celery, Uvicorn, and Next.js directly and works without Docker. Adding a compose file or a frontend Dockerfile would be new infrastructure on top of a working, un-broken local dev experience — outside "fix what's broken, keep changes minimal." If you want a fully Dockerized local stack, say so explicitly and I'll scope it as its own piece of work rather than bundling it into a build-fix pass.

---

## Files changed

- `backend/Dockerfile` — non-root user, `HEALTHCHECK`, removed redundant pip installs, fixed `libgl1-mesa-glx` → `libgl1` + `libglx-mesa0` (Finding 5).
- `backend/.dockerignore` — new file.
- `backend/main.py` — added `GET /health` liveness route; added it to the existing health-check log-skip list.
- `backend/services/document_core.py` — moved `import easyocr` from module top-level into `get_ocr_reader()` (Finding 6).
- `PLATFORM_HARDENING_PHASE3A.md` — this report.

No other files were touched. Pre-existing uncommitted WIP on this branch (Google Drive sync, reconciliation adapter/engine changes, `backend/backend_log.txt`, `backend - Copy/`, `scratch_verify/`, etc.) was left exactly as found.
