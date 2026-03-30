"""
VoiceCraft Platform — Celery Workers
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from celery import Celery
from celery.signals import worker_ready

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  Celery App Configuration
# ─────────────────────────────────────────────────────────────────

celery_app = Celery(
    "voicecraft",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # Process one task at a time (ML models are heavy)
    task_routes={
        "app.workers.tasks.clone_voice_task": {"queue": "clone"},
        "app.workers.tasks.fine_tune_task": {"queue": "fine_tune"},
        "app.workers.tasks.synthesize_tts_task": {"queue": "tts"},
        "app.workers.tasks.detect_deepfake_task": {"queue": "detect"},
        "app.workers.tasks.cleanup_task": {"queue": "maintenance"},
    },
    task_time_limit={
        "clone": settings.CLONE_TASK_TIMEOUT_SECONDS,
        "fine_tune": settings.FINE_TUNE_TASK_TIMEOUT_SECONDS,
        "tts": settings.TTS_TASK_TIMEOUT_SECONDS,
        "detect": settings.DETECT_TASK_TIMEOUT_SECONDS,
    },
    broker_connection_retry_on_startup=True,
    result_expires=86400 * 7,  # keep results 7 days
)


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Pre-load ML models when worker starts (avoid cold-start latency on tasks)."""
    logger.info("Celery worker ready — pre-loading ML models...")
    try:
        from app.services.voice_cloner import get_voice_cloner
        get_voice_cloner().initialize()
        logger.info("XTTS-v2 loaded.")
    except Exception as e:
        logger.warning("XTTS-v2 pre-load failed: %s", e)

    try:
        from app.services.deepfake_detector import get_deepfake_detector
        get_deepfake_detector().initialize()
        logger.info("Detection models loaded.")
    except Exception as e:
        logger.warning("Detection pre-load failed: %s", e)
