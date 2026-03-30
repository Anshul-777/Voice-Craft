# ═══════════════════════════════════════════════════════════════
# VoiceCraft Platform — Multi-Stage Dockerfile
# Stage 1: builder (deps) | Stage 2: api | Stage 3: worker
# ═══════════════════════════════════════════════════════════════

FROM python:3.12-slim AS builder

# System deps for audio processing and ML
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    git \
    curl \
    libgomp1 \
    portaudio19-dev \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install/pkgs -r requirements.txt

# ── API Stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS api

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    espeak-ng \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /install/pkgs /usr/local
COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create required directories
RUN mkdir -p /app/models_cache /app/voice_profiles /tmp/voicecraft_audio

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--loop", "uvloop", "--http", "httptools"]

# ── Worker Stage ──────────────────────────────────────────────
FROM api AS worker

ENV C_FORCE_ROOT=1

# Workers just run Celery (command overridden in docker-compose)
CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info"]
