"""
VoiceCraft Platform — Configuration
All settings loaded from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────
    APP_NAME: str = "VoiceCraft Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION-USE-SECRETS-MANAGER"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET: str = "CHANGE-ME-JWT-SECRET-AT-LEAST-32-CHARS-LONG"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://voicecraft:voicecraft_pass@localhost:5432/voicecraft"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── MinIO / S3-Compatible Object Storage ─────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "voicecraft_admin"
    MINIO_SECRET_KEY: str = "voicecraft_secret_change_me"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_VOICES: str = "voice-profiles"
    MINIO_BUCKET_AUDIO: str = "generated-audio"
    MINIO_BUCKET_UPLOADS: str = "raw-uploads"
    MINIO_BUCKET_MODELS: str = "custom-models"

    # ── Model Storage Paths ───────────────────────────────────
    MODELS_DIR: Path = Path("/app/models_cache")
    VOICE_PROFILES_DIR: Path = Path("/app/voice_profiles")
    TEMP_AUDIO_DIR: Path = Path("/tmp/voicecraft_audio")

    # ── XTTS-v2 Voice Cloning ─────────────────────────────────
    XTTS_MODEL_NAME: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    XTTS_DEVICE: str = "cuda"          # "cpu" if no GPU
    XTTS_USE_DEEPSPEED: bool = False    # Enable if A100/H100 available
    XTTS_ENABLE_TEXT_SPLITTING: bool = True
    MIN_CLONE_AUDIO_SECONDS: float = 6.0
    MAX_CLONE_AUDIO_SECONDS: float = 300.0  # 5 minutes max for quality
    FINE_TUNE_MIN_SECONDS: float = 60.0     # Fine-tuning starts at 1 min
    MAX_TTS_TEXT_LENGTH: int = 5000

    # ── Deepfake Detection ────────────────────────────────────
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.70
    DETECTION_CHUNK_MS: int = 4000           # 4-second analysis windows
    DETECTION_OVERLAP_MS: int = 500          # 0.5s overlap between windows
    AASIST_MODEL_PATH: str = "models_cache/aasist"
    RAWNET2_MODEL_PATH: str = "models_cache/rawnet2"
    DETECTION_ENSEMBLE_WEIGHTS: dict = {
        "aasist": 0.40,
        "rawnet2": 0.25,
        "prosodic": 0.15,
        "spectral": 0.10,
        "glottal": 0.10,
    }

    # ── SpeechBrain Speaker Verification ─────────────────────
    SPEAKER_VERIFICATION_MODEL: str = "speechbrain/spkrec-ecapa-voxceleb"
    SPEAKER_SIMILARITY_THRESHOLD: float = 0.75

    # ── Whisper Transcription ─────────────────────────────────
    WHISPER_MODEL_SIZE: str = "base"    # tiny/base/small/medium/large-v3
    WHISPER_DEVICE: str = "cuda"

    # ── Rate Limits ───────────────────────────────────────────
    RATE_LIMIT_CLONE_PER_DAY: int = 10
    RATE_LIMIT_TTS_PER_DAY: int = 500
    RATE_LIMIT_DETECT_PER_DAY: int = 1000

    # ── Plan Limits ───────────────────────────────────────────
    FREE_VOICE_PROFILES_MAX: int = 2
    STARTER_VOICE_PROFILES_MAX: int = 10
    PRO_VOICE_PROFILES_MAX: int = 50
    ENTERPRISE_VOICE_PROFILES_MAX: int = 9999

    FREE_TTS_CHARS_PER_MONTH: int = 10_000
    STARTER_TTS_CHARS_PER_MONTH: int = 100_000
    PRO_TTS_CHARS_PER_MONTH: int = 1_000_000
    ENTERPRISE_TTS_CHARS_PER_MONTH: int = 999_999_999

    # ── Audio Output Formats ──────────────────────────────────
    SUPPORTED_OUTPUT_FORMATS: list[str] = ["wav", "mp3", "ogg", "flac"]
    DEFAULT_OUTPUT_FORMAT: str = "mp3"
    DEFAULT_SAMPLE_RATE: int = 24000
    DEFAULT_BIT_RATE: str = "192k"

    # ── Supported TTS Languages ───────────────────────────────
    SUPPORTED_LANGUAGES: list[str] = [
        "en", "es", "fr", "de", "it", "pt", "pl", "tr",
        "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi",
    ]

    # ── Audio Quality / Noise Reduction ──────────────────────
    ENABLE_NOISE_REDUCTION: bool = True
    ENABLE_NORMALIZATION: bool = True
    TARGET_LUFS: float = -23.0       # EBU R128 broadcast standard
    MAX_UPLOAD_SIZE_MB: int = 100

    # ── Celery Task Timeouts ──────────────────────────────────
    CLONE_TASK_TIMEOUT_SECONDS: int = 600
    TTS_TASK_TIMEOUT_SECONDS: int = 120
    DETECT_TASK_TIMEOUT_SECONDS: int = 300
    FINE_TUNE_TASK_TIMEOUT_SECONDS: int = 3600

    # ── Prometheus ────────────────────────────────────────────
    METRICS_ENABLED: bool = True

    @property
    def is_gpu_available(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def ensure_dirs(self) -> None:
        for d in [self.MODELS_DIR, self.VOICE_PROFILES_DIR, self.TEMP_AUDIO_DIR]:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
