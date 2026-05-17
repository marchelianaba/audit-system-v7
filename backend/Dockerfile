# Backend Audit AI v7 — FastAPI + Claude Agent SDK
FROM python:3.12-slim

# System deps untuk pdfplumber, python-docx, dan pdftotext (poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app/ ./app/

# Copy V6 scripts ke /v6 (di-bake ke image agar mandiri)
# Saat dev lokal, ini di-override oleh bind mount di docker-compose.yml
COPY v6_scripts/ /v6/scripts/
COPY v6_skills/ /v6/skills/
COPY v6_templates/ /v6/templates/
COPY v6_checklists/ /v6/checklists/

# Data directory untuk penugasan
RUN mkdir -p /data
ENV APP_DATA_DIR=/data
ENV APP_V6_PATH=/v6
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
