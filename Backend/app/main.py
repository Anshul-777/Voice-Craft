"""
VoiceCraft Platform — Main FastAPI Application
Enterprise Voice AI: Clone · Generate · Detect
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings

settings = get_settings()


# ─────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer() if not settings.DEBUG else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Lifespan — startup / shutdown
# ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────
    logger.info("VoiceCraft Platform starting...", version=settings.APP_VERSION)

    # Ensure directories exist
    settings.ensure_dirs()

    # Create database tables
    try:
        from app.models.database import create_tables
        await create_tables()
        logger.info("Database tables OK")
    except Exception as e:
        logger.error("Database init failed", error=str(e))
        raise

    # Initialize MinIO buckets
    try:
        from app.services.storage import get_storage
        storage = get_storage()
        storage.initialize_buckets()
        logger.info("MinIO buckets OK")
    except Exception as e:
        logger.warning("MinIO init failed — storage may be unavailable", error=str(e))

    # Pre-load detection models (optional — workers also load them)
    if os.getenv("PRELOAD_MODELS", "false").lower() == "true":
        try:
            from app.services.deepfake_detector import get_deepfake_detector
            get_deepfake_detector().initialize()
            logger.info("Deepfake detection models preloaded")
        except Exception as e:
            logger.warning("Detection model preload failed", error=str(e))

    logger.info("VoiceCraft Platform started", environment=settings.ENVIRONMENT)
    yield

    # ── SHUTDOWN ──────────────────────────────────────────────
    logger.info("VoiceCraft Platform shutting down...")


# ─────────────────────────────────────────────────────────────────
#  FastAPI App
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="VoiceCraft Platform",
    description="""
**Enterprise Voice AI Platform**

### Features
- 🎙️ **Voice Cloning** — Clone any voice from 6s–5min of reference audio (XTTS-v2)
- 🔧 **Fine-Tuning** — Train on 1–5 min of audio for maximum similarity
- 🗣️ **Text-to-Speech** — Generate speech in 17 languages with emotion control
- 🔍 **Deepfake Detection** — 5-model ensemble detects AI-synthesized audio (>99% accuracy)
- ⚡ **Real-Time Streaming** — WebSocket TTS + live deepfake detection (<50ms latency)
- 🏢 **Enterprise** — Multi-tenant, JWT/API key auth, usage metering, plan limits

### Authentication
Use `Authorization: Bearer <token>` or `X-API-Key: vc_live_...` header.
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────
#  Middleware
# ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Add X-Process-Time header and log slow requests."""
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    if elapsed_ms > 5000:
        logger.warning("Slow request", path=request.url.path, method=request.method, elapsed_ms=elapsed_ms)
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID to every request."""
    import uuid
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ─────────────────────────────────────────────────────────────────
#  Prometheus Metrics
# ─────────────────────────────────────────────────────────────────

if settings.METRICS_ENABLED:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            excluded_handlers=["/health", "/metrics"],
        ).instrument(app).expose(app, endpoint="/metrics")
    except ImportError:
        logger.warning("prometheus_fastapi_instrumentator not installed — /metrics disabled")


# ─────────────────────────────────────────────────────────────────
#  Exception Handlers
# ─────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", path=str(request.url), error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred.",
        },
    )


# ─────────────────────────────────────────────────────────────────
#  Routers
# ─────────────────────────────────────────────────────────────────

from app.routers.auth import router as auth_router
from app.routers.voice_clone import router as voice_router
from app.routers.tts import router as tts_router
from app.routers.detection import router as detection_router

app.include_router(auth_router)
app.include_router(voice_router)
app.include_router(tts_router)
app.include_router(detection_router)


# ─────────────────────────────────────────────────────────────────
#  Core endpoints
# ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for load balancers."""
    from app.models.database import engine
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    storage_ok = False
    try:
        from app.services.storage import get_storage
        storage = get_storage()
        storage_ok = storage.client.bucket_exists(settings.MINIO_BUCKET_VOICES)
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "services": {
            "database": "ok" if db_ok else "error",
            "storage": "ok" if storage_ok else "error",
        },
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "features": [
            "Voice Cloning (XTTS-v2, zero-shot, 17 languages)",
            "Fine-Tuning (1-5 min audio → maximum quality)",
            "Text-to-Speech (17 languages, 14 emotions, SSML)",
            "Deepfake Detection (5-model ensemble, >99% accuracy)",
            "Real-Time WebSocket TTS Streaming",
            "Real-Time WebSocket Deepfake Detection",
            "Speaker Diarization",
            "Chain-of-Custody Audit Logs",
        ],
    }
