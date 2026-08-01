FROM python:3.10-slim

# Install system dependencies (including fitz dependencies if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
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

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi python-multipart pydantic-settings

# Copy backend files
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

# Expose port 8000
EXPOSE 8000

# Set environment variable defaults
ENV OPENAI_API_BASE=https://api.groq.com/openai/v1
ENV MODEL_NAME=llama-3.3-70b-versatile

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
