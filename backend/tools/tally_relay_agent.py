"""
tally_relay_agent.py — Tally local bridge agent (client half of the relay).

Runs on the accountant's own machine, on the same LAN as TallyPrime. Solves
the problem that a cloud-hosted AuditOS backend can't reach into a firm's
private network: this agent makes only OUTBOUND connections to the backend
(poll for jobs, post results back) and talks to Tally over localhost/LAN
itself — same shape as how Zoom/ngrok/TeamViewer relays work. No inbound
firewall rule, no IP to type into anything.

Zero third-party dependencies (stdlib only, matching services/tally_connector.py's
own zero-dependency design) — this file plus tally_connector.py are the whole
distribution. Copy both onto the accountant's machine and run this one.

Setup (once):
    python tally_relay_agent.py --pair 123456 --backend-url https://auditos-backend.onrender.com

    123456 is the 6-digit pairing code generated in the AuditOS UI (Push to
    Tally -> Set up local agent). Saves the resulting agent token to a local
    config file (tally_relay_agent_config.json, next to this script/exe) —
    never re-enter the code again after this.

Run (every time after that):
    python tally_relay_agent.py

    Starts the poll loop. Leave this running in the background, or register
    it to launch automatically at login (Windows only, no admin rights
    needed — this writes a user-level Run registry key, not a full Windows
    Service, since accountant machines can't be assumed to have admin):

        python tally_relay_agent.py --install-startup
        python tally_relay_agent.py --uninstall-startup

Packaging into a standalone .exe (no Python install needed on the
accountant's machine): see tools/build_tally_relay_agent_exe.ps1. This file
is written to work identically frozen or not — see IS_FROZEN below.
"""

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Running frozen (PyInstaller --onefile) vs. as a plain script changes where
# "next to this program" actually is: frozen, __file__ points into a
# temporary extraction directory (sys._MEIPASS) that's wiped after the
# process exits, so persistent state (config, startup registration) must
# anchor on sys.executable's directory instead. Unfrozen, __file__ is fine.
IS_FROZEN = getattr(sys, "frozen", False)
PROGRAM_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent

if not IS_FROZEN:
    # Import tally_connector.py whether this script sits inside the repo
    # (backend/tools/, sibling of backend/services/) or was copied standalone
    # onto an accountant's machine next to a copy of tally_connector.py.
    # Frozen builds bundle tally_connector.py directly (see the build
    # script), so no path juggling is needed there.
    sys.path.insert(0, str(PROGRAM_DIR))
    sys.path.insert(0, str(PROGRAM_DIR.parent / "services"))
try:
    from tally_connector import TallyConfig, TallyConnectionError, TallyConnector
except ImportError:
    from services.tally_connector import TallyConfig, TallyConnectionError, TallyConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tally_relay_agent")

CONFIG_PATH = PROGRAM_DIR / "tally_relay_agent_config.json"
STARTUP_REGISTRY_NAME = "AuditOSTallyRelayAgent"
POLL_INTERVAL_SECONDS = 5
BACKOFF_ON_ERROR_SECONDS = 15
REQUEST_TIMEOUT_SECONDS = 20


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    logger.info(f"Saved config to {CONFIG_PATH}")


def _post_json(url: str, body: dict, headers: Optional[dict] = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach backend at {url}: {e}") from e


def pair(backend_url: str, code: str, agent_name: Optional[str]) -> None:
    logger.info(f"Pairing with {backend_url} using code {code} ...")
    result = _post_json(f"{backend_url}/api/tally/relay/pair", {"code": code, "agent_name": agent_name})
    _save_config({
        "backend_url": backend_url,
        "agent_id": result["agent_id"],
        "token": result["token"],
        "tally_host": "localhost",
        "tally_port": 9000,
    })
    logger.info(f"Paired successfully. Agent ID: {result['agent_id']}")
    logger.info("Run this script again with no arguments to start relaying jobs.")


def _execute_push_voucher_job(payload: dict, tally_host: str, tally_port: int) -> dict:
    row = payload["row"]
    voucher_type = payload["voucher_type"]
    company = payload["company"]

    connector = TallyConnector(TallyConfig(host=tally_host, port=tally_port, company=company))
    try:
        result = connector.push_voucher(row, voucher_type=voucher_type)
    except TallyConnectionError as e:
        return {"success": False, "error": str(e)}
    return {"success": result.success, "error": result.error, "created": result.created}


def run_poll_loop(cfg: dict) -> None:
    backend_url = cfg["backend_url"]
    headers = {"X-Agent-Id": cfg["agent_id"], "X-Agent-Token": cfg["token"]}
    tally_host = cfg.get("tally_host", "localhost")
    tally_port = cfg.get("tally_port", 9000)

    logger.info(f"Starting relay: backend={backend_url}  local Tally={tally_host}:{tally_port}")
    logger.info(f"Polling every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.")

    while True:
        try:
            poll_result = _post_json(f"{backend_url}/api/tally/relay/poll", {}, headers)
            job = poll_result.get("job")
            if not job:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            logger.info(f"Claimed job {job['id']} ({job['job_type']})")
            if job["job_type"] == "push_voucher":
                outcome = _execute_push_voucher_job(job["payload"], tally_host, tally_port)
            else:
                outcome = {"success": False, "error": f"Unknown job_type: {job['job_type']}"}

            _post_json(
                f"{backend_url}/api/tally/relay/result",
                {
                    "job_id": job["id"],
                    "success": outcome["success"],
                    "result": outcome,
                    "error": outcome.get("error"),
                },
                headers,
            )
            logger.info(f"Reported job {job['id']}: {'success' if outcome['success'] else 'failed - ' + str(outcome.get('error'))}")

        except RuntimeError as e:
            logger.warning(f"Relay error, retrying in {BACKOFF_ON_ERROR_SECONDS}s: {e}")
            time.sleep(BACKOFF_ON_ERROR_SECONDS)
        except KeyboardInterrupt:
            logger.info("Stopped.")
            return
        except Exception as e:
            # Anything unexpected (a bad job payload, a transient OS error,
            # etc.) must not kill an unattended background process — log and
            # keep polling rather than exiting silently. Startup-registered
            # agents have no one watching the terminal to notice a crash.
            logger.error(f"Unexpected error in poll loop, continuing: {e}")
            time.sleep(BACKOFF_ON_ERROR_SECONDS)


def _startup_command() -> str:
    """The command line written to the Run registry key. Frozen: just the
    exe. Unfrozen: prefer pythonw.exe (no console window popping up at every
    login) over python.exe if it's sitting next to the interpreter in use."""
    if IS_FROZEN:
        return f'"{sys.executable}"'

    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    interpreter = str(pythonw) if pythonw.exists() else str(python_exe)
    return f'"{interpreter}" "{Path(__file__).resolve()}"'


def install_startup() -> None:
    """Registers this agent to launch automatically at Windows login via a
    per-user Run key — deliberately not a full Windows Service, since
    accountant machines can't be assumed to have admin rights and a Service
    install would need them. Idempotent (overwrites any existing entry)."""
    if sys.platform != "win32":
        raise RuntimeError("--install-startup is Windows-only")
    if not _load_config():
        raise RuntimeError(f"Pair first (--pair CODE --backend-url URL) before installing startup — no config at {CONFIG_PATH}")

    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, STARTUP_REGISTRY_NAME, 0, winreg.REG_SZ, _startup_command())
    finally:
        winreg.CloseKey(key)
    logger.info(f"Installed: will launch automatically at login (registry value {STARTUP_REGISTRY_NAME!r}).")


def uninstall_startup() -> None:
    if sys.platform != "win32":
        raise RuntimeError("--uninstall-startup is Windows-only")

    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        try:
            winreg.DeleteValue(key, STARTUP_REGISTRY_NAME)
            logger.info("Removed from startup.")
        except FileNotFoundError:
            logger.info("Was not registered for startup — nothing to remove.")
    finally:
        winreg.CloseKey(key)


def main() -> None:
    parser = argparse.ArgumentParser(description="AuditOS Tally local bridge agent")
    parser.add_argument("--pair", metavar="CODE", help="6-digit pairing code from the AuditOS UI")
    parser.add_argument("--backend-url", help="AuditOS backend URL (required with --pair)")
    parser.add_argument("--name", help="Optional label for this agent, e.g. 'Reception PC'")
    parser.add_argument("--tally-host", default=None, help="Override the local Tally host (default: localhost)")
    parser.add_argument("--tally-port", type=int, default=None, help="Override the local Tally port (default: 9000)")
    parser.add_argument("--install-startup", action="store_true", help="Launch automatically at Windows login (no admin needed)")
    parser.add_argument("--uninstall-startup", action="store_true", help="Undo --install-startup")
    args = parser.parse_args()

    if args.pair:
        if not args.backend_url:
            parser.error("--backend-url is required with --pair")
        try:
            pair(args.backend_url, args.pair, args.name)
        except RuntimeError as e:
            # A raw traceback here is bad UX for a non-technical accountant
            # running the packaged .exe — caught live: an unreachable/wrong
            # backend URL surfaced as "Failed to execute script" with a full
            # Python stack, no indication what actually went wrong.
            parser.error(str(e))
        return

    if args.install_startup:
        try:
            install_startup()
        except RuntimeError as e:
            parser.error(str(e))
        return

    if args.uninstall_startup:
        try:
            uninstall_startup()
        except RuntimeError as e:
            parser.error(str(e))
        return

    cfg = _load_config()
    if not cfg:
        parser.error(
            f"No saved config found at {CONFIG_PATH}. "
            f"Run with --pair CODE --backend-url URL first (get the code from the AuditOS UI)."
        )

    if args.tally_host:
        cfg["tally_host"] = args.tally_host
    if args.tally_port:
        cfg["tally_port"] = args.tally_port

    run_poll_loop(cfg)


if __name__ == "__main__":
    main()
