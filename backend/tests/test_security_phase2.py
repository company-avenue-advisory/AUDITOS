"""
Security regression suite — Phase 2 (remaining High findings).
================================================================
Independently re-verified (not trusted from the Phase 1 audit write-up) and,
where real, fixed here:

  1. Unauthenticated GET /api/tasks/{task_id}/review          -> TestTaskReviewAuth
  2. Unauthenticated GET /api/tasks/{task_id}/observability    -> TestTaskObservabilityAuth
  3. Missing tenant check on PATCH .../accept-correction       -> TestAcceptCorrectionTenant
  4. CORS wildcard + allow_credentials=True                    -> TestCorsConfig (unit-level,
     not TestClient-driven; see class docstring)

A second, previously-undocumented High finding was discovered while fixing
#2 above (same file, adjacent function): GET /api/observability/stats
aggregated batch/file counts, quality scores, and LLM cost totals across
EVERY tenant on the platform with no tenant filter at all -- only its
`recent_jobs` sub-section was correctly tenant-scoped. Fixed here
(TestObservabilityStatsTenantScoping) by scoping every aggregate to the
caller's tenant via BatchJob.tenant_id, the same trustworthy join key
Phase 1 established elsewhere in this file.

One originally-flagged "High" finding was independently re-verified and found
to be a FALSE POSITIVE on this codebase's runtime (Python 3.12): Zip Slip via
`zipfile.ZipFile.extractall()` in `upload_batch`. CPython's stdlib has
stripped '..'/absolute-path components from archive member names since long
before 3.6 (see `zipfile.Path._normalize` / `_extract_member`'s
`invalid_path_parts` filtering) -- reproduced empirically against this repo's
exact call pattern (`extractall(extract_dir)` with no member-name handling of
its own) with `../`, backslash, and absolute Windows-drive payloads; all three
land inside `extract_dir`, none escape it. No code fix applied for this one;
see SECURITY_REMEDIATION_PHASE2.md for the reproduction transcript.

Run:
    python -m unittest backend.tests.test_security_phase2 -v
"""
import os
import sys
import tempfile
import unittest
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"auditos_test2_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("SENTRY_DSN", "")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import User, Tenant, BatchJob, InvoiceTask, TaskStatus, ObservabilityLog  # noqa: E402
from services.auth import hash_password  # noqa: E402

client = TestClient(main.app)


def _unique_email(prefix="user"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}@test.local"


def _make_tenant(db, name="Tenant"):
    t = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_user(db, role="auditor", tenant_id=None, password="Password123!"):
    u = User(
        id=str(uuid.uuid4()),
        email=_unique_email(role),
        hashed_password=hash_password(password),
        role=role,
        tenant_id=tenant_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, password


def _login(email, password):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_batch_with_task(db, tenant_id, recon_status=None, recon_report_json=None):
    batch = BatchJob(id=str(uuid.uuid4()), total_files=1, status=TaskStatus.COMPLETED, tenant_id=tenant_id)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    task = InvoiceTask(
        id=str(uuid.uuid4()),
        batch_id=batch.id,
        file_name="a.pdf",
        status=TaskStatus.COMPLETED,
        invoice_type="Sales",
        recon_status=recon_status,
        recon_report_json=recon_report_json,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return batch, task


class SecurityPhase2TestCase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.tenant = _make_tenant(self.db, "P2Tenant")
        self.user, self.password = _make_user(self.db, role="auditor", tenant_id=self.tenant.id)
        self.token = _login(self.user.email, self.password)

        self.other_tenant = _make_tenant(self.db, "P2OtherTenant")
        self.other_user, self.other_password = _make_user(self.db, role="auditor", tenant_id=self.other_tenant.id)
        self.other_token = _login(self.other_user.email, self.other_password)

        self.batch, self.task = _make_batch_with_task(
            self.db, self.tenant.id,
            recon_status="NEEDS_REVIEW",
            recon_report_json='{"lines": [{"flag": "variance"}]}',
        )

    def tearDown(self):
        self.db.close()


# ─────────────────────────────────────────────────────────────────────────────
# High: unauthenticated GET /api/tasks/{task_id}/review
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskReviewAuth(SecurityPhase2TestCase):
    def test_unauthenticated_request_rejected(self):
        resp = client.get(f"/api/tasks/{self.task.id}/review")
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_cross_tenant_access_rejected(self):
        resp = client.get(f"/api/tasks/{self.task.id}/review", headers=_auth_headers(self.other_token))
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertNotIn(b"variance", resp.content)

    def test_nonexistent_task_returns_404(self):
        resp = client.get(f"/api/tasks/{uuid.uuid4()}/review", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_same_tenant_access_still_works(self):
        """Regression: legitimate same-tenant read of the review report is unaffected."""
        resp = client.get(f"/api/tasks/{self.task.id}/review", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["task_id"], self.task.id)
        self.assertEqual(body["recon_status"], "NEEDS_REVIEW")
        self.assertIsNotNone(body["recon_report"])


# ─────────────────────────────────────────────────────────────────────────────
# High: unauthenticated GET /api/tasks/{task_id}/observability
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskObservabilityAuth(SecurityPhase2TestCase):
    def setUp(self):
        super().setUp()
        log = ObservabilityLog(
            batch_id=self.batch.id,
            file_id=self.task.id,
            event_type="extraction_quality_score",
            stage="extraction",
            severity="info",
            payload_json='{"composite_score": 0.9, "marker": "secret-pipeline-detail"}',
        )
        self.db.add(log)
        self.db.commit()

    def test_unauthenticated_request_rejected(self):
        resp = client.get(f"/api/tasks/{self.task.id}/observability")
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_cross_tenant_access_rejected(self):
        resp = client.get(f"/api/tasks/{self.task.id}/observability", headers=_auth_headers(self.other_token))
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertNotIn(b"secret-pipeline-detail", resp.content)

    def test_nonexistent_task_returns_404(self):
        resp = client.get(f"/api/tasks/{uuid.uuid4()}/observability", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_same_tenant_access_still_works(self):
        """Regression: legitimate same-tenant read of pipeline logs is unaffected."""
        resp = client.get(f"/api/tasks/{self.task.id}/observability", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["task_id"], self.task.id)
        self.assertEqual(len(body["events"]), 1)
        self.assertIn("secret-pipeline-detail", body["events"][0]["payload"]["marker"])


# ─────────────────────────────────────────────────────────────────────────────
# High: missing tenant check on PATCH /api/tasks/{task_id}/accept-correction
# ─────────────────────────────────────────────────────────────────────────────
class TestAcceptCorrectionTenant(SecurityPhase2TestCase):
    def test_cross_tenant_correction_rejected(self):
        """
        Before the fix, any authenticated owner/auditor -- regardless of
        tenant -- could mark ANOTHER tenant's task as HUMAN_CORRECTED,
        corrupting that tenant's audit trail state.
        """
        resp = client.patch(
            f"/api/tasks/{self.task.id}/accept-correction",
            headers=_auth_headers(self.other_token),
        )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.db.refresh(self.task)
        self.assertEqual(self.task.recon_status, "NEEDS_REVIEW")

    def test_nonexistent_task_returns_404(self):
        resp = client.patch(f"/api/tasks/{uuid.uuid4()}/accept-correction", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_same_tenant_correction_still_works(self):
        """Regression: an in-tenant owner/auditor can still accept a correction."""
        resp = client.patch(
            f"/api/tasks/{self.task.id}/accept-correction",
            headers=_auth_headers(self.token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["recon_status"], "HUMAN_CORRECTED")
        self.db.refresh(self.task)
        self.assertEqual(self.task.recon_status, "HUMAN_CORRECTED")

    def test_unauthenticated_request_still_rejected(self):
        """Confirm the pre-existing RoleChecker auth requirement is unchanged."""
        resp = client.patch(f"/api/tasks/{self.task.id}/accept-correction")
        self.assertEqual(resp.status_code, 401)

    def test_wrong_role_still_rejected(self):
        hr_user, hr_password = _make_user(self.db, role="hr", tenant_id=self.tenant.id)
        hr_token = _login(hr_user.email, hr_password)
        resp = client.patch(
            f"/api/tasks/{self.task.id}/accept-correction",
            headers=_auth_headers(hr_token),
        )
        self.assertEqual(resp.status_code, 403, resp.text)


# ─────────────────────────────────────────────────────────────────────────────
# High (discovered during this phase): GET /api/observability/stats leaked
# aggregate financial/quality metrics across every tenant on the platform.
# ─────────────────────────────────────────────────────────────────────────────
class TestObservabilityStatsTenantScoping(SecurityPhase2TestCase):
    def setUp(self):
        super().setUp()
        # A second tenant with its own batch, task, and cost/flag logs --
        # none of this must be visible to self.user (P2Tenant).
        self.other_batch, self.other_task = _make_batch_with_task(self.db, self.other_tenant.id)
        cost_log = ObservabilityLog(
            batch_id=self.other_batch.id,
            file_id=self.other_task.id,
            event_type="file_metrics",
            payload_json='{"model_cost": {"total_cost_inr": 999.0}}',
        )
        flag_log = ObservabilityLog(
            batch_id=self.other_batch.id,
            file_id=self.other_task.id,
            event_type="system_flag",
            flag_id="OTHER_TENANT_SECRET_FLAG",
            severity="HIGH",
            payload_json='{"filename": "other-tenant-invoice.pdf", "trigger_detail": "leaked?"}',
        )
        self.db.add_all([cost_log, flag_log])
        self.db.commit()

    def test_stats_do_not_include_other_tenants_batches_or_files(self):
        resp = client.get("/api/observability/stats", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        # self.user's tenant has exactly 1 batch / 1 task from setUp; the
        # other tenant's batch/task must not be counted in.
        self.assertEqual(body["total_batches"], 1)
        self.assertEqual(body["total_files"], 1)

    def test_stats_do_not_include_other_tenants_cost_or_flags(self):
        resp = client.get("/api/observability/stats", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total_cost_inr"], 0.0)
        self.assertEqual(body["total_flags"], 0)
        flag_ids = [f.get("flag_id") for f in body["recent_flags"]]
        self.assertNotIn("OTHER_TENANT_SECRET_FLAG", flag_ids)

    def test_other_tenant_sees_only_their_own_stats(self):
        """Regression: the other tenant's own owner still sees their own real data."""
        resp = client.get("/api/observability/stats", headers=_auth_headers(self.other_token))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total_batches"], 1)
        self.assertEqual(body["total_cost_inr"], 999.0)
        self.assertEqual(body["total_flags"], 1)

    def test_unassigned_user_sees_only_legacy_untenanted_data_not_everything(self):
        """
        A freshly-registered, never-assigned user must not see every
        tenant's aggregate stats -- only truly untenanted (legacy) data,
        matching the tightened require_same_tenant semantics from Phase 1.
        """
        unassigned_user, unassigned_password = _make_user(self.db, role="owner", tenant_id=None)
        unassigned_token = _login(unassigned_user.email, unassigned_password)
        resp = client.get("/api/observability/stats", headers=_auth_headers(unassigned_token))
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total_batches"], 0)
        self.assertEqual(body["total_files"], 0)
        self.assertEqual(body["total_cost_inr"], 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# High: CORS wildcard + allow_credentials=True
# ─────────────────────────────────────────────────────────────────────────────
class TestCorsConfig(unittest.TestCase):
    """
    Not TestClient-driven (CORSMiddleware's origin-reflection logic runs at
    the ASGI layer using headers already resolved at app-construction time in
    this test process, where ALLOWED_ORIGINS was never set -- i.e. this
    process is already exercising the wildcard branch). Verifies directly
    against the running app's constructed middleware stack instead.
    """

    def test_wildcard_origin_does_not_grant_credentials(self):
        """
        With ALLOWED_ORIGINS unset (defaulting to '*'), allow_credentials
        must be False -- the middleware must not advertise the contradictory
        'wildcard origin + credentials allowed' combination.
        """
        found = False
        for mw in main.app.user_middleware:
            if mw.cls.__name__ == "CORSMiddleware":
                found = True
                options = mw.kwargs
                if options.get("allow_origins") == ["*"]:
                    self.assertFalse(
                        options.get("allow_credentials", False),
                        "allow_credentials must be False when allow_origins is '*'",
                    )
        self.assertTrue(found, "CORSMiddleware was not found in the app's middleware stack")

    def test_production_without_explicit_allowed_origins_fails_closed(self):
        """
        Re-import main.py in a subprocess with ENVIRONMENT=production and
        ALLOWED_ORIGINS='*' -- the module must refuse to start, the same
        fail-closed pattern already used for JWT_SECRET_KEY. ALLOWED_ORIGINS
        must be explicitly set to '*' here (not merely unset/popped): this
        repo's backend/.env sets a real ALLOWED_ORIGINS value, and
        python-dotenv's load_dotenv() (override=False by default) will
        happily fill an unset env var from that file, silently defeating a
        test that only pops the variable instead of pinning it.
        """
        import subprocess
        env = os.environ.copy()
        env["ENVIRONMENT"] = "production"
        env["ALLOWED_ORIGINS"] = "*"
        env["JWT_SECRET_KEY"] = "a" * 64  # avoid tripping the unrelated JWT guard
        env["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.gettempdir(), f'auditos_prod_probe_{uuid.uuid4().hex}.db')}"
        proc = subprocess.run(
            [sys.executable, "-c", "import main"],
            cwd=_BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0, "main.py must fail to start with ALLOWED_ORIGINS='*' in production")
        self.assertIn("ALLOWED_ORIGINS", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
