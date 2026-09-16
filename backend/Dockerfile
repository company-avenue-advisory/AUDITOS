FROM python:3.10-slim

# Install system dependencies (including fitz dependencies if needed)
# libgl1-mesa-glx was a transitional dummy package that just depended on
# libgl1 + libglx-mesa0; Debian removed it in trixie, and python:3.10-slim
# now tracks trixie, so `apt-get install libgl1-mesa-glx` fails with
# "E: Unable to locate package libgl1-mesa-glx". Installing its two former
# dependencies directly preserves the same runtime GL capability.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app
# Belt-and-braces alongside celery_app.py's own sys.path fix: celery's
# import_from_cwd() temporarily adds/removes cwd from sys.path around loading
# the app module, which breaks deferred in-task imports without this.
ENV PYTHONPATH=/app

# Copy requirements
COPY requirements.txt .

# docling and easyocr both pull in torch as a transitive dependency, and
# pip's default PyPI wheel for torch bundles the full CUDA/nvidia toolkit
# (~4-5GB of nvidia-cudnn/cublas/cusparselt/triton etc.) even though this
# image runs on CPU-only hosts with no GPU at all -- confirmed this blew
# past a droplet's disk during a real deploy (no space left on device
# extracting libtorch_cuda.so). Installing the CPU-only wheel FIRST, from
# PyTorch's own CPU index, satisfies requirements.txt's transitive
# torch>=2.2.2 constraint before pip ever considers the CUDA build.
#
# Two details matter here:
#   - "+cpu" is pinned explicitly on the version, not just the index -- without
#     it, pip resolves a same-numbered wheel ambiguously between this index and
#     PyPI's default (CUDA) build.
#   - "--extra-index-url" (adds to PyPI), not "--index-url" (replaces PyPI
#     entirely) -- confirmed the latter breaks a real deploy: torch's own
#     transitive deps (fsspec/sympy/networkx/typing-extensions) can still need
#     PyPI, and one of them (typing-extensions) failed a wheel-metadata check
#     here, fell back to a source build needing flit_core, which doesn't exist
#     on PyTorch's index-only view -- "could not find a version that satisfies
#     the requirement flit_core".
RUN pip install --no-cache-dir torch==2.14.0+cpu torchvision==0.29.0+cpu --extra-index-url https://download.pytorch.org/whl/cpu

# Install dependencies (fastapi/uvicorn/python-multipart already come from
# requirements.txt via the fastapi[standard] extra — no need to reinstall them)
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files (see .dockerignore for what's excluded — notably .env,
# *.db, and dev-only tests/scripts/docs)
COPY . .

# backend/core uses absolute imports like `from backend.core.schema import ...`,
# written assuming the process runs from the repo root with `backend/` as a
# real subpackage. This image instead copies backend/'s contents straight
# into /app, so there's no `backend` package on disk -- those imports raise
# ModuleNotFoundError: No module named 'backend'. Rather than rewrite ~40
# files across two inconsistent import conventions (some bare like
# `services.xxx`, some `backend.core.xxx`), self-link /app as its own
# `backend` child so both resolve.
RUN ln -s /app /app/backend

# Run as a non-root user
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app
USER app

# Expose port 8000
EXPOSE 8000

# Set environment variable defaults
ENV OPENAI_API_BASE=https://api.groq.com/openai/v1
ENV MODEL_NAME=llama-3.3-70b-versatile

# Liveness probe: the API process is up and serving requests. Does not check
# DB/Celery/Redis — see /api/health/workers for task-queue readiness.
# Uses stdlib urllib (no curl/wget) so no extra apt package is needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
