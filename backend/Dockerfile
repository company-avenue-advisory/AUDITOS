FROM python:3.10-slim

# Install system dependencies (including fitz dependencies if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi python-multipart pydantic-settings

# Copy backend files
COPY . .

# Expose port 8000
EXPOSE 8000

# Set environment variable defaults
ENV OPENAI_API_BASE=https://api.groq.com/openai/v1
ENV MODEL_NAME=llama-3.3-70b-versatile

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
