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

# Copy requirements
COPY requirements.txt .

# Install dependencies (fastapi/uvicorn/python-multipart already come from
# requirements.txt via the fastapi[standard] extra — no need to reinstall them)
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files (see .dockerignore for what's excluded — notably .env,
# *.db, and dev-only tests/scripts/docs)
COPY . .

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
