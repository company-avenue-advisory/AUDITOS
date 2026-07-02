"""
Security regression suite — Phase 1 Critical fixes.
=====================================================
Covers the 5 Critical findings verified in the DevOps/Security audit:

  1. Live secrets in backend/.env               -> operational, not code-testable here.
  2. Role self-escalation via /api/auth/register -> TestRegisterRoleEscalation
  3. Path traversal in /api/jobs/.../files/...   -> TestFileDownloadPathTraversal
  4. Unauthenticated PUT /api/items/{item_id}    -> TestItemUpdateAuth
  5. Unauthenticated GET /api/export/{batch_id}  -> TestExportAuth

Each suite asserts BOTH that the vulnerability is closed AND that the
legitimate/authenticated-same-tenant path still behaves as before the fix
(regression protection).

Adversarial follow-up review (same phase) found and closed 3 additional
bypasses of the above fixes:
  - TestUnassignedUserTenantBypass  -> require_same_tenant's blanket pass for
    callers with no tenant of their own (the default state of every freshly
    registered account) defeated the #4/#5 fixes entirely.
  - TestTenantAssignmentIsolation   -> POST /api/admin/tenants/{id}/assign-user
    was missing the tenant-scoping check present on its sibling endpoints,
    letting a self-registered "owner" hop into any existing tenant directly.
  - test_mass_assignment_*          -> PUT /api/items/{id} allowed rewriting
    the task_id/id primary/foreign-key columns via unrestricted setattr,
    letting an in-tenant caller re-parent an item into another tenant's data.

A subsequent Principal Engineer review pass (same phase) found that
GET /api/jobs/{batch_id}/files/{filename:path} -- the endpoint hardened
against path traversal above -- had no tenant-isolation check at all, unlike
every sibling batch-resource endpoint. Fixed and covered by
TestFileDownloadPathTraversal::test_cross_tenant_file_access_rejected and
::test_nonexistent_batch_returns_404_not_leaked_files.

Run:
    python -m unittest backend.tests.test_security_phase1 -v
    (or via backend/tests/regression/run_regression.py -- see note in file)
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

# Use an isolated on-disk SQLite DB for this test run, and avoid contacting
# real Sentry. Must happen BEFORE `main` (and therefore `database`) is imported,
# since the SQLAlchemy engine is created at module import time.
_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"auditos_test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("SENTRY_DSN", "")

import main  # noqa: E402  (import after env setup, by design)
from fastapi.testclient import TestClient  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import User, Tenant, BatchJob, InvoiceTask, SalesLineItem, TaskStatus  # noqa: E402
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


def _make_batch_with_item(db, tenant_id):
    batch = BatchJob(id=str(uuid.uuid4()), total_files=1, status=TaskStatus.COMPLETED, tenant_id=tenant_id)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    task = InvoiceTask(id=str(uuid.uuid4()), batch_id=batch.id, file_name="a.pdf", status=TaskStatus.COMPLETED, invoice_type="Sales")
    db.add(task)
    db.commit()
    db.refresh(task)

    item = SalesLineItem(task_id=task.id, invoice_no="INV-001", voucher_type="Sales", taxable_value=100.0)
    db.add(item)
    db.commit()
    db.refresh(item)

    return batch, task, item


class SecurityPhase1TestCase(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Critical #2: role self-escalation at registration
# ─────────────────────────────────────────────────────────────────────────────
class TestRegisterRoleEscalation(SecurityPhase1TestCase):
    def test_developer_role_rejected_at_registration(self):
        """The 'developer' role is a full RBAC bypass and must not be self-assignable."""
        resp = client.post("/api/auth/register", json={
            "email": _unique_email("escalate"),
            "password": "Password123!",
            "role": "developer",
        })
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("Invalid role", resp.json()["detail"])

    def test_developer_role_rejected_case_insensitive(self):
        resp = client.post("/api/auth/register", json={
            "email": _unique_email("escalate2"),
            "password": "Password123!",
            "role": "DEVELOPER",
        })
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_legitimate_roles_still_allowed(self):
        """Regression: owner/hr/auditor/other must continue to work exactly as before."""
        for role in ["owner", "hr", "auditor", "other"]:
            email = _unique_email(role)
            resp = client.post("/api/auth/register", json={
                "email": email, "password": "Password123!", "role": role,
            })
            self.assertEqual(resp.status_code, 201, f"role={role}: {resp.text}")
            self.assertEqual(resp.json()["role"], role)

    def test_default_role_is_auditor_when_omitted(self):
        email = _unique_email("defaultrole")
        resp = client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["role"], "auditor")

    def test_registered_user_cannot_obtain_developer_privileges(self):
        """End-to-end: register, log in, confirm the RoleChecker bypass role was never granted."""
        email = _unique_email("e2e")
        password = "Password123!"
        reg = client.post("/api/auth/register", json={"email": email, "password": password, "role": "developer"})
        self.assertEqual(reg.status_code, 400)
        # user must not exist in the DB at all
        user = self.db.query(User).filter(User.email == email).first()
        self.assertIsNone(user)


# ─────────────────────────────────────────────────────────────────────────────
# Critical #3: path traversal on file download
# ─────────────────────────────────────────────────────────────────────────────
class TestFileDownloadPathTraversal(SecurityPhase1TestCase):
    def setUp(self):
        super().setUp()
        self.tenant = _make_tenant(self.db, "FilesTenant")
        self.user, self.password = _make_user(self.db, role="auditor", tenant_id=self.tenant.id)
        self.token = _login(self.user.email, self.password)

        self.other_tenant = _make_tenant(self.db, "FilesOtherTenant")
        self.other_user, self.other_password = _make_user(self.db, role="auditor", tenant_id=self.other_tenant.id)
        self.other_token = _login(self.other_user.email, self.other_password)

        self.batch_id = str(uuid.uuid4())
        self.batch = BatchJob(id=self.batch_id, total_files=1, status=TaskStatus.COMPLETED, tenant_id=self.tenant.id)
        self.db.add(self.batch)
        self.db.commit()

        self.batch_dir = os.path.join(tempfile.gettempdir(), f"batch_{self.batch_id}")
        os.makedirs(self.batch_dir, exist_ok=True)
        with open(os.path.join(self.batch_dir, "legit.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 fake content")

        # A "secret" file placed OUTSIDE the batch dir, sibling to it, that a
        # traversal payload could try to reach.
        self.secret_path = os.path.join(tempfile.gettempdir(), f"secret_{self.batch_id}.txt")
        with open(self.secret_path, "w") as f:
            f.write("TOP-SECRET-VALUE")

    def tearDown(self):
        super().tearDown()
        for p in (self.secret_path,):
            if os.path.exists(p):
                os.remove(p)

    def test_legit_filename_still_downloads(self):
        """Regression: normal file retrieval within the batch dir, by a same-tenant user, must keep working."""
        resp = client.get(f"/api/jobs/{self.batch_id}/files/legit.pdf", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn(b"PDF", resp.content)

    def test_cross_tenant_file_access_rejected(self):
        """
        A user from a different tenant than the batch's owner must not be
        able to download its files, even with a valid JWT and a correct
        filename (no traversal payload involved) -- this is the tenant
        isolation gap found during the Phase 1 principal-engineer review.
        """
        resp = client.get(f"/api/jobs/{self.batch_id}/files/legit.pdf", headers=_auth_headers(self.other_token))
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertNotIn(b"PDF", resp.content)

    def test_nonexistent_batch_returns_404_not_leaked_files(self):
        """A batch_id with no corresponding BatchJob row must 404, not fall through to the filesystem."""
        resp = client.get(f"/api/jobs/{uuid.uuid4()}/files/legit.pdf", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_traversal_with_dotdot_is_rejected(self):
        """
        Percent-encode the dot-segments so the traversal payload survives
        client-side URL normalization (httpx/browsers collapse literal '../'
        before the request is even sent) and actually reaches the server's
        route handler, exercising the containment check under test.
        """
        secret_name = os.path.basename(self.secret_path)
        traversal = f"%2e%2e%2f{secret_name}"
        resp = client.get(f"/api/jobs/{self.batch_id}/files/{traversal}", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertNotIn(b"TOP-SECRET-VALUE", resp.content)

    def test_deep_traversal_to_env_file_is_rejected(self):
        traversal = "%2e%2e%2f" * 8 + "backend%2f.env"
        resp = client.get(f"/api/jobs/{self.batch_id}/files/{traversal}", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertNotIn(b"JWT_SECRET", resp.content)

    def test_unauthenticated_request_still_rejected(self):
        """Confirm the pre-existing auth requirement on this endpoint was not weakened."""
        resp = client.get(f"/api/jobs/{self.batch_id}/files/legit.pdf")
        self.assertEqual(resp.status_code, 401)

    def test_backslash_traversal_is_rejected(self):
        """
        Windows-style '..\\' traversal, independent of the '../' payload above —
        os.path.join treats backslashes as separators on Windows even when the
        rest of the app uses forward slashes, so this must be checked too.
        """
        secret_name = os.path.basename(self.secret_path)
        traversal = f"%2e%2e%5c{secret_name}"
        resp = client.get(f"/api/jobs/{self.batch_id}/files/{traversal}", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertNotIn(b"TOP-SECRET-VALUE", resp.content)

    def test_windows_absolute_drive_path_is_rejected(self):
        """
        os.path.join("<batch_dir>", "C:\\Windows\\win.ini") silently DISCARDS
        batch_dir on Windows and returns the absolute path verbatim — a
        different bypass mechanism than a relative '../' traversal, so it
        needs its own coverage.
        """
        traversal = "C%3a%5cWindows%5cwin.ini"
        resp = client.get(f"/api/jobs/{self.batch_id}/files/{traversal}", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 400, resp.text)


# ─────────────────────────────────────────────────────────────────────────────
# Critical #4: unauthenticated item mutation
# ─────────────────────────────────────────────────────────────────────────────
class TestItemUpdateAuth(SecurityPhase1TestCase):
    def setUp(self):
        super().setUp()
        self.tenant_a = _make_tenant(self.db, "TenantA")
        self.tenant_b = _make_tenant(self.db, "TenantB")

        self.auditor_a, pw = _make_user(self.db, role="auditor", tenant_id=self.tenant_a.id)
        self.token_a = _login(self.auditor_a.email, pw)

        self.auditor_b, pw_b = _make_user(self.db, role="auditor", tenant_id=self.tenant_b.id)
        self.token_b = _login(self.auditor_b.email, pw_b)

        self.hr_a, pw_hr = _make_user(self.db, role="hr", tenant_id=self.tenant_a.id)
        self.token_hr = _login(self.hr_a.email, pw_hr)

        self.batch, self.task, self.item = _make_batch_with_item(self.db, self.tenant_a.id)

    def test_unauthenticated_update_rejected(self):
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "taxable_value", "value": 999.0},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_disallowed_role_rejected(self):
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "taxable_value", "value": 999.0},
            headers=_auth_headers(self.token_hr),
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_cross_tenant_update_rejected(self):
        """A user from Tenant B must not be able to edit Tenant A's line item."""
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "taxable_value", "value": 999.0},
            headers=_auth_headers(self.token_b),
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_same_tenant_auditor_can_still_update(self):
        """Regression: the legitimate edit flow (auditor, same tenant) must still work."""
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "taxable_value", "value": 555.5},
            headers=_auth_headers(self.token_a),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.db.refresh(self.item)
        self.assertEqual(self.item.taxable_value, 555.5)

    def test_mass_assignment_reparent_via_task_id_rejected(self):
        """
        Adversarial: a legitimate same-tenant auditor tries to rewrite the
        item's task_id foreign key to re-parent it onto a DIFFERENT tenant's
        task. Since the tenant check only validates the item's tenant at read
        time, an unrestricted setattr(item, req.field, req.value) would let
        this write silently smuggle the row into another tenant's data.
        """
        other_batch, other_task, _ = _make_batch_with_item(self.db, self.tenant_b.id)
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "task_id", "value": other_task.id},
            headers=_auth_headers(self.token_a),
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.db.refresh(self.item)
        self.assertEqual(self.item.task_id, self.task.id)

    def test_mass_assignment_id_field_rejected(self):
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "id", "value": 999999},
            headers=_auth_headers(self.token_a),
        )
        self.assertEqual(resp.status_code, 400, resp.text)


# ─────────────────────────────────────────────────────────────────────────────
# Adversarial finding: require_same_tenant granted a blanket pass whenever the
# CALLER had no tenant (current_user.tenant_id is None) — the default state of
# every freshly self-registered account. This defeated the tenant checks added
# for Critical #4 and #5 for the most common attacker scenario, since a brand
# new account never needs to be assigned to any tenant to exploit it.
# ─────────────────────────────────────────────────────────────────────────────
class TestUnassignedUserTenantBypass(SecurityPhase1TestCase):
    def setUp(self):
        super().setUp()
        self.victim_tenant = _make_tenant(self.db, "UnassignedBypassVictim")
        self.batch, self.task, self.item = _make_batch_with_item(self.db, self.victim_tenant.id)

        # A brand-new self-registered user, never assigned to any tenant --
        # the default post-registration state (see /api/auth/register).
        email = _unique_email("unassigned")
        password = "Password123!"
        reg = client.post("/api/auth/register", json={"email": email, "password": password, "role": "auditor"})
        assert reg.status_code == 201, reg.text
        self.token = _login(email, password)

    def test_unassigned_user_cannot_export_other_tenants_batch(self):
        resp = client.get(f"/api/export/{self.batch.id}?type=sales", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_unassigned_user_cannot_update_other_tenants_item(self):
        resp = client.put(
            f"/api/items/{self.item.id}?type=sales",
            json={"field": "taxable_value", "value": 1.0},
            headers=_auth_headers(self.token),
        )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.db.refresh(self.item)
        self.assertEqual(self.item.taxable_value, 100.0)

    def test_legacy_untenanted_resource_still_accessible(self):
        """
        Regression: require_same_tenant's original "graceful" exemption for
        resources with NO tenant at all (legacy pre-multi-tenant data) must
        still work -- only the "caller has no tenant" half of the old
        condition was the vulnerability, not the "resource has no tenant" half.
        """
        legacy_batch, _legacy_task, legacy_item = _make_batch_with_item(self.db, tenant_id=None)
        resp = client.get(f"/api/export/{legacy_batch.id}?type=sales", headers=_auth_headers(self.token))
        self.assertEqual(resp.status_code, 200, resp.text)


# ─────────────────────────────────────────────────────────────────────────────
# Adversarial finding: POST /api/admin/tenants/{tenant_id}/assign-user was
# missing the tenant-scoping check its sibling admin endpoints all have,
# letting any self-registered "owner" assign themselves (or anyone) into any
# existing, populated tenant -- fully legitimizing subsequent cross-tenant
# access without even needing the unassigned-user bypass above.
# ─────────────────────────────────────────────────────────────────────────────
class TestTenantAssignmentIsolation(SecurityPhase1TestCase):
    def test_owner_cannot_hop_into_unrelated_existing_tenant(self):
        victim_tenant = _make_tenant(self.db, "HopVictim")
        victim_owner, victim_pw = _make_user(self.db, role="owner", tenant_id=victim_tenant.id)

        attacker_email = _unique_email("hopper")
        attacker_pw = "Password123!"
        reg = client.post("/api/auth/register", json={
            "email": attacker_email, "password": attacker_pw, "role": "owner",
        })
        self.assertEqual(reg.status_code, 201)
        attacker_token = _login(attacker_email, attacker_pw)

        resp = client.post(
            f"/api/admin/tenants/{victim_tenant.id}/assign-user?user_email={attacker_email}",
            headers=_auth_headers(attacker_token),
        )
        self.assertEqual(resp.status_code, 403, resp.text)

        attacker = self.db.query(User).filter(User.email == attacker_email).first()
        self.db.refresh(attacker)
        self.assertIsNone(attacker.tenant_id)

    def test_owner_bootstrap_create_tenant_auto_assigns_self(self):
        """Regression: the self-serve 'create firm' flow must still work end-to-end."""
        owner_email = _unique_email("bootstrap")
        owner_pw = "Password123!"
        client.post("/api/auth/register", json={"email": owner_email, "password": owner_pw, "role": "owner"})
        token = _login(owner_email, owner_pw)

        resp = client.post(
            "/api/admin/tenants",
            json={"name": "Bootstrap Firm", "slug": f"bootstrap-{uuid.uuid4().hex[:8]}"},
            headers=_auth_headers(token),
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        tenant_id = resp.json()["tenant_id"]

        owner = self.db.query(User).filter(User.email == owner_email).first()
        self.assertEqual(owner.tenant_id, tenant_id)

        # The frontend fires this immediately after create -- must be a harmless no-op now.
        resp = client.post(
            f"/api/admin/tenants/{tenant_id}/assign-user?user_email={owner_email}",
            headers=_auth_headers(token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_owner_can_still_invite_colleague_into_own_firm(self):
        """Regression: inviting a colleague into a firm you already belong to must still work."""
        tenant = _make_tenant(self.db, "InviteFirm")
        owner, owner_pw = _make_user(self.db, role="owner", tenant_id=tenant.id)
        owner_token = _login(owner.email, owner_pw)

        colleague_email = _unique_email("colleague")
        client.post("/api/auth/register", json={
            "email": colleague_email, "password": "Password123!", "role": "auditor",
        })

        resp = client.post(
            f"/api/admin/tenants/{tenant.id}/assign-user?user_email={colleague_email}",
            headers=_auth_headers(owner_token),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        colleague = self.db.query(User).filter(User.email == colleague_email).first()
        self.db.refresh(colleague)
        self.assertEqual(colleague.tenant_id, tenant.id)


# ─────────────────────────────────────────────────────────────────────────────
# Critical #5: unauthenticated export
# ─────────────────────────────────────────────────────────────────────────────
class TestExportAuth(SecurityPhase1TestCase):
    def setUp(self):
        super().setUp()
        self.tenant_a = _make_tenant(self.db, "ExportTenantA")
        self.tenant_b = _make_tenant(self.db, "ExportTenantB")

        self.user_a, pw_a = _make_user(self.db, role="auditor", tenant_id=self.tenant_a.id)
        self.token_a = _login(self.user_a.email, pw_a)

        self.user_b, pw_b = _make_user(self.db, role="auditor", tenant_id=self.tenant_b.id)
        self.token_b = _login(self.user_b.email, pw_b)

        self.batch, self.task, self.item = _make_batch_with_item(self.db, self.tenant_a.id)

    def test_unauthenticated_export_rejected(self):
        resp = client.get(f"/api/export/{self.batch.id}?type=sales")
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_cross_tenant_export_rejected(self):
        resp = client.get(f"/api/export/{self.batch.id}?type=sales", headers=_auth_headers(self.token_b))
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_same_tenant_export_still_works(self):
        """Regression: the legitimate export flow (same tenant) must still succeed."""
        resp = client.get(f"/api/export/{self.batch.id}?type=sales", headers=_auth_headers(self.token_a))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertGreater(len(resp.content), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
