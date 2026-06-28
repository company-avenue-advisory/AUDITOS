"""
modal_deploy.py
===============
Deploy the FastAPI Invoice Extractor backend as a Modal serverless app.

Usage:
  python -m modal deploy backend/modal_deploy.py        # deploy to Modal cloud
  python -m modal serve  backend/modal_deploy.py        # live-reload dev tunnel

Pre-requisites:
  1. pip install modal
  2. modal token new            (authenticate once)
  3. modal secret create openrouter-secrets OPENROUTER_API_KEY=<your_key>
"""

import modal
import os

# ── Container image ──────────────────────────────────────────────────────────
# Build a Debian-slim image, install dependencies, and copy local backend code.
# modal.Mount is removed in Modal v1.x — use image.add_local_dir() instead.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]",   # includes uvicorn, starlette
        "python-multipart",    # required for FastAPI file uploads
        "pymupdf",             # PDF text + image extraction
        "pandas",
        "openpyxl",
        "openai",              # Groq & Ollama use the OpenAI-compatible SDK
        "pydantic",
        "python-dotenv",
    )
    .add_local_dir(
        # Copy the entire backend/ directory into /root/backend in the container
        os.path.dirname(os.path.abspath(__file__)),
        remote_path="/root/backend",
    )
)

# ── Modal App ─────────────────────────────────────────────────────────────────
app = modal.App("ai-invoice-extractor")

# ── ASGI endpoint ─────────────────────────────────────────────────────────────
# @modal.asgi_app() must be the INNERMOST decorator (closest to the def).
# allow_concurrent_inputs removed in v1.x — use @modal.concurrent() decorator.
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("openrouter-secrets"),
    ],
    timeout=600,    # 10-min timeout for large multi-page PDFs
    cpu=4.0,        # 4 vCPUs — headroom for 50 asyncio threads doing PDF parsing
    memory=2048,    # 2 GB RAM for concurrent pdfplumber + fitz page loads
    # Modal auto-scales containers horizontally when demand exceeds max_inputs.
    # Each container handles 50 concurrent requests; at 100-invoice batches
    # a second container spins up automatically within ~5 s.
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def fastapi_app():
    """Return the FastAPI app to Modal's ASGI server."""
    import sys
    sys.path.insert(0, "/root/backend")
    os.chdir("/root/backend")
    from main import app as web_app  # noqa: PLC0415
    return web_app
