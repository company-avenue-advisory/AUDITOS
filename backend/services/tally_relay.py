"""
tally_relay.py — server-side half of the Tally local bridge agent.

Problem this solves: once AuditOS's backend is cloud-hosted, it can't reach a
firm's on-prem TallyPrime directly (Tally's XML-over-HTTP server is LAN-local,
and a cloud server can't initiate a connection into a firm's private network).
The fix is the standard relay pattern (same shape as Zoom/ngrok/TeamViewer): a
small agent runs on the accountant's own machine and opens only OUTBOUND
connections to this backend — polling for pending jobs and posting results
back — while talking to Tally over localhost/LAN itself. See
tools/tally_relay_agent.py for the client half.

Job lifecycle: pending -> claimed -> success | failed (models.TallyRelayJob).
main.py's push_batch_to_tally enqueues a job per line item and blocks briefly
polling wait_for_job_result() — same synchronous response shape the direct
(same-LAN) push path already returns, so nothing about the API contract or
frontend changes between relay and direct mode.
"""

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models import TallyRelayAgent, TallyRelayJob, TallyRelayPairingCode

logger = logging.getLogger(__name__)

PAIRING_CODE_TTL = timedelta(minutes=10)
AGENT_FRESHNESS_WINDOW = timedelta(minutes=2)  # last_seen_at must be within this to count as "active"
JOB_WAIT_TIMEOUT_SECONDS = 45
JOB_WAIT_POLL_INTERVAL_SECONDS = 1.0


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_pairing_code(db: Session, tenant_id: str, created_by: str) -> dict:
    """Issues a fresh 6-digit code, retrying on the rare collision with an
    existing unexpired code (primary key is the code itself)."""
    now = datetime.utcnow()
    db.query(TallyRelayPairingCode).filter(TallyRelayPairingCode.expires_at < now).delete()

    for _ in range(5):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if db.query(TallyRelayPairingCode).filter(TallyRelayPairingCode.code == code).first():
            continue
        expires_at = now + PAIRING_CODE_TTL
        db.add(TallyRelayPairingCode(
            code=code, tenant_id=tenant_id, created_by=created_by, expires_at=expires_at,
        ))
        db.commit()
        return {"code": code, "expires_at": expires_at.isoformat()}

    raise RuntimeError("Could not generate a unique pairing code, try again")


def pair_agent(db: Session, code: str, agent_name: Optional[str]) -> dict:
    """Exchanges a pairing code for a persistent agent token. Returns the raw
    token exactly once — the caller (the agent process) must store it, since
    only its hash is kept server-side."""
    pairing = db.query(TallyRelayPairingCode).filter(TallyRelayPairingCode.code == code).first()
    if not pairing:
        raise ValueError("Invalid pairing code")
    if pairing.expires_at < datetime.utcnow():
        db.delete(pairing)
        db.commit()
        raise ValueError("Pairing code has expired — generate a new one")

    token = secrets.token_urlsafe(32)
    agent = TallyRelayAgent(
        tenant_id=pairing.tenant_id, name=agent_name, token_hash=_hash_token(token),
        paired_at=datetime.utcnow(),
    )
    db.add(agent)
    db.delete(pairing)
    db.commit()
    db.refresh(agent)
    return {"agent_id": agent.id, "token": token, "tenant_id": agent.tenant_id}


def authenticate_agent(db: Session, agent_id: str, token: str) -> TallyRelayAgent:
    agent = db.query(TallyRelayAgent).filter(TallyRelayAgent.id == agent_id).first()
    if not agent or agent.revoked_at is not None:
        raise ValueError("Unknown or revoked agent")
    if agent.token_hash != _hash_token(token):
        raise ValueError("Invalid agent token")
    return agent


def get_active_agent(db: Session, tenant_id: str) -> Optional[TallyRelayAgent]:
    """Returns this tenant's paired agent if it has polled recently enough to
    be considered online, else None (caller should fall back to direct
    same-LAN connection — see main.py:push_batch_to_tally)."""
    cutoff = datetime.utcnow() - AGENT_FRESHNESS_WINDOW
    return (
        db.query(TallyRelayAgent)
        .filter(
            TallyRelayAgent.tenant_id == tenant_id,
            TallyRelayAgent.revoked_at.is_(None),
            TallyRelayAgent.last_seen_at.isnot(None),
            TallyRelayAgent.last_seen_at >= cutoff,
        )
        .order_by(TallyRelayAgent.last_seen_at.desc())
        .first()
    )


def enqueue_job(db: Session, tenant_id: str, payload: dict, job_type: str = "push_voucher") -> TallyRelayJob:
    job = TallyRelayJob(
        tenant_id=tenant_id, job_type=job_type, payload_json=json.dumps(payload), status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next_job(db: Session, agent: TallyRelayAgent) -> Optional[TallyRelayJob]:
    """Claims the oldest pending job for this agent's tenant. Single UPDATE
    guarded by status="pending" so two concurrent polls (unlikely — normally
    one agent per tenant, but not assumed) can't both claim the same job."""
    agent.last_seen_at = datetime.utcnow()
    db.commit()

    job = (
        db.query(TallyRelayJob)
        .filter(TallyRelayJob.tenant_id == agent.tenant_id, TallyRelayJob.status == "pending")
        .order_by(TallyRelayJob.created_at.asc())
        .first()
    )
    if not job:
        return None

    claimed = (
        db.query(TallyRelayJob)
        .filter(TallyRelayJob.id == job.id, TallyRelayJob.status == "pending")
        .update({"status": "claimed", "agent_id": agent.id, "claimed_at": datetime.utcnow()})
    )
    db.commit()
    if claimed == 0:
        return None  # lost the race to another poll
    db.refresh(job)
    return job


def report_job_result(
    db: Session, agent: TallyRelayAgent, job_id: str, success: bool, result: dict, error: Optional[str],
) -> TallyRelayJob:
    job = db.query(TallyRelayJob).filter(TallyRelayJob.id == job_id).first()
    if not job:
        raise ValueError(f"No job {job_id}")
    if job.agent_id != agent.id:
        raise ValueError("This job was not claimed by this agent")
    job.status = "success" if success else "failed"
    job.result_json = json.dumps(result)
    job.error = error
    job.completed_at = datetime.utcnow()
    db.commit()
    return job


def wait_for_job_result(
    db: Session, job_id: str, timeout_seconds: float = JOB_WAIT_TIMEOUT_SECONDS,
) -> TallyRelayJob:
    """Blocks (polling the DB row) until the agent reports a result or the
    timeout elapses. Called synchronously from push_batch_to_tally, one item
    at a time — mirrors the direct-connect path's per-item HTTP round trip,
    just with the agent's poll interval added to the latency instead of a
    LAN hop. Times out to "failed" (agent likely offline) rather than
    hanging the request indefinitely."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        db.expire_all()  # force a fresh read, not SQLAlchemy's identity-mapped stale copy
        job = db.query(TallyRelayJob).filter(TallyRelayJob.id == job_id).first()
        if job and job.status in ("success", "failed"):
            return job
        time.sleep(JOB_WAIT_POLL_INTERVAL_SECONDS)

    job = db.query(TallyRelayJob).filter(TallyRelayJob.id == job_id).first()
    if job and job.status not in ("success", "failed"):
        job.status = "failed"
        job.error = "Timed out waiting for the local bridge agent to respond (is it still running?)"
        job.completed_at = datetime.utcnow()
        db.commit()
    return job
