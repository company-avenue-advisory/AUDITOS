"""
deploy_and_update.py
====================
Deploys the FastAPI backend to Modal, captures the live server URL,
and automatically updates the Next.js frontend .env.local file.

Usage:
  python deploy_and_update.py
"""

import subprocess
import re
import sys
import os
from pathlib import Path

# Reconfigure stdout to handle unicode/emojis properly on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
BACKEND_DEPLOY = ROOT / "backend" / "modal_deploy.py"
FRONTEND_ENV   = ROOT / "frontend" / ".env.local"

def run_deploy():
    """Run modal deploy and return the output."""
    print("🚀 Deploying to Modal cloud…")
    print("=" * 60)

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "modal", "deploy", str(BACKEND_DEPLOY)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(ROOT),
            env=env,
        )
        output = result.stdout + result.stderr
        print(output)
        return output, result.returncode
    except FileNotFoundError:
        print("❌ modal not found. Run: pip install modal")
        sys.exit(1)

def extract_url(output: str) -> str | None:
    """
    Parse the Modal deployment URL from deploy output.
    Modal prints a line like:
      ✓ Created web endpoint https://yugvk--ai-invoice-extractor-fastapi-app.modal.run
    """
    # Primary pattern: Modal ✓ endpoint line
    patterns = [
        r"https://[a-z0-9\-]+\.modal\.run",
        r"View at https://modal\.com/[^\s]+",
    ]
    for pat in patterns:
        match = re.search(pat, output)
        if match:
            url = match.group(0)
            # If it's a "View at" link, skip (that's the dashboard URL)
            if "modal.com/apps" not in url and "modal.com/u/" not in url:
                return url.rstrip("/")
    return None

def update_frontend_env(url: str):
    """Write / update NEXT_PUBLIC_API_URL in frontend/.env.local."""
    lines = []
    found = False

    if FRONTEND_ENV.exists():
        for line in FRONTEND_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("NEXT_PUBLIC_API_URL="):
                lines.append(f"NEXT_PUBLIC_API_URL={url}")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"NEXT_PUBLIC_API_URL={url}")

    FRONTEND_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n✅ Updated {FRONTEND_ENV}")
    print(f"   NEXT_PUBLIC_API_URL={url}")


def update_footer_links(url: str):
    """Also patch the hardcoded localhost link in the footer of page.tsx."""
    page_tsx = ROOT / "frontend" / "src" / "app" / "page.tsx"
    if not page_tsx.exists():
        return

    content = page_tsx.read_text(encoding="utf-8")

    # Replace the localhost:8000 href and visible text
    updated = re.sub(
        r'href="http://localhost:8000/docs"',
        f'href="{url}/docs"',
        content,
    )
    updated = re.sub(
        r'href="http://localhost:8000"',
        f'href="{url}"',
        updated,
    )
    # Replace the link label text "localhost:8000" with the modal domain
    modal_host = re.sub(r"https?://", "", url)
    updated = re.sub(
        r">localhost:8000<",
        f">{modal_host}<",
        updated,
    )

    if updated != content:
        page_tsx.write_text(updated, encoding="utf-8")
        print(f"✅ Updated footer link in {page_tsx.name} → {modal_host}")
    else:
        print("ℹ️  page.tsx footer already up to date (or no localhost:8000 found)")


if __name__ == "__main__":
    output, code = run_deploy()

    if code != 0:
        print(f"\n❌ Deployment failed (exit code {code}).")
        # Still try to parse a partial URL in case output contains one
        url = extract_url(output)
        if url:
            print(f"   Found URL in output anyway: {url}")
        else:
            print("   No URL found. Check the output above for errors.")
            sys.exit(code)
    else:
        url = extract_url(output)
        if not url:
            print("\n⚠️  Deployment succeeded but could not parse the server URL.")
            print("    Please check the output above and set manually:")
            print("    NEXT_PUBLIC_API_URL=<your-modal-url>  in frontend/.env.local")
            sys.exit(0)

    print(f"\n🎉 Deployment complete!")
    print(f"   Server URL: {url}")

    update_frontend_env(url)
    update_footer_links(url)

    print("\n📋 Next steps:")
    print("   1. Restart the frontend dev server: cd frontend && npm run dev")
    print(f"   2. Visit your API docs: {url}/docs")
    print(f"   3. Open the app: http://localhost:3000")
