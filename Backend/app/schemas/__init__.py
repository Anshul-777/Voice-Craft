"""
VoiceCraft Platform — Pydantic v2 Schemas
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ══════════════════════════════════════════════════════════════════
#  User / Auth Schemas
# ══════════════════════════════════════════════════════════════════

class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")]
    password: Annotated[str, Field(min_length=8)]
    full_name: str | None = None
    organization_name: str | None = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    username: str
    full_name: str | None
    role: str
    organization_id: str | None
    is_verified: bool
    created_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    scopes: list[str] = [
        "clone:read", "clone:write", "tts:read", "tts:write", "detect:read"
    ]
    expires_days: int | None = None


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: str
    created_at: datetime
    expires_at: datetime | None
    raw_key: str | None = None  # only shown on creation


# ══════════════════════════════════════════════════════════════════
#  Voice Profile Schemas
# ══════════════════════════════════════════════════════════════════

class VoiceCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: str | None = None
    tags: list[str] = []
    is_public: bool = False


class VoiceUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_public: bool | None = None


class AudioQualityReport(BaseModel):
    duration_seconds: float
    snr_db: float
    speech_ratio: float
    is_acceptable: bool
    quality_flags: list[str]
    mean_fundamental_frequency: float | None
    rms_db: float
    recommendation: str


class VoiceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    status: str
    organization_id: str
    owner_id: str
    detected_language: str | None
    detected_gender: str
    detected_age: str
    mean_fundamental_frequency: float | None
    speaking_rate_wpm: float | None
    snr_db: float | None
    is_fine_tuned: bool
    clone_quality_score: float | None
    similarity_to_original: float | None
    total_training_seconds: float
    reference_audio_count: int
    tags: list | None
    is_public: bool
    generation_count: int
    preview_audio_url: str | None = None
    created_at: datetime
    updated_at: datetime


class VoiceProfileListResponse(BaseModel):
    voices: list[VoiceProfileResponse]
    total: int
    page: int
    page_size: int


class UploadSampleResponse(BaseModel):
    sample_id: str
    voice_profile_id: str
    duration_seconds: float
    quality_report: AudioQualityReport
    total_training_seconds: float
    is_ready_for_cloning: bool
    message: str


class CloneJobStatus(BaseModel):
    job_id: str
    voice_profile_id: str
    status: str
    progress_pct: int
    current_epoch: int | None
    total_epochs: int | None
    job_type: str
    quality_score: float | None
    error_message: str | None
    created_at: datetime


# ══════════════════════════════════════════════════════════════════
#  TTS Generation Schemas
# ══════════════════════════════════════════════════════════════════

class TTSRequest(BaseModel):
    voice_profile_id: str
    text: Annotated[str, Field(min_length=1, max_length=5000)]
    language: str = "en"
    emotion: str = "neutral"
    speed: Annotated[float, Field(ge=0.5, le=2.0)] = 1.0
    pitch_shift_semitones: Annotated[float, Field(ge=-12.0, le=12.0)] = 0.0
    temperature: Annotated[float, Field(ge=0.1, le=1.0)] = 0.75
    output_format: str = "mp3"
    sample_rate: int = 24000
    enable_noise_reduction: bool = True
    ssml_enabled: bool = False

    @field_validator("emotion")
    @classmethod
    def validate_emotion(cls, v: str) -> str:
        valid = {
            "neutral", "happy", "sad", "angry", "fearful", "disgusted",
            "surprised", "calm", "excited", "whispering", "shouting",
            "narration", "conversational", "newscast", "documentary",
        }
        if v not in valid:
            raise ValueError(f"Invalid emotion. Must be one of: {valid}")
        return v

    @field_validator("output_format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        valid = {"wav", "mp3", "ogg", "flac"}
        if v not in valid:
            raise ValueError(f"Must be one of {valid}")
        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        valid = {
            "en", "es", "fr", "de", "it", "pt", "pl", "tr",
            "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi",
        }
        if v not in valid:
            raise ValueError(f"Unsupported language. Supported: {valid}")
        return v


class TTSResponse(BaseModel):
    job_id: str
    status: str
    voice_profile_id: str
    chars_count: int
    estimated_seconds: float
    message: str


class TTSJobStatus(BaseModel):
    job_id: str
    status: str
    voice_profile_id: str
    duration_seconds: float | None
    file_size_bytes: int | None
    processing_time_ms: int | None
    mos_score: float | None
    download_url: str | None
    error_message: str | None
    created_at: datetime


class TTSStreamRequest(BaseModel):
    """For streaming TTS via WebSocket."""
    voice_profile_id: str
    text: str
    language: str = "en"
    speed: float = 1.0
    emotion: str = "neutral"
    chunk_size_chars: int = 200  # stream in chunks for low latency


# ══════════════════════════════════════════════════════════════════
#  Detection Schemas
# ══════════════════════════════════════════════════════════════════

class DetectionMode(str, enum.Enum):
    FULL = "full"
    FAST = "fast"
    REALTIME = "realtime"


class DetectionRequest(BaseModel):
    analysis_mode: DetectionMode = DetectionMode.FULL
    speaker_diarization: bool = True
    generate_report: bool = True


class ChunkResultSchema(BaseModel):
    start_ms: int
    end_ms: int
    deepfake_probability: float
    is_deepfake: bool
    model_scores: dict[str, float]


class DetectionResultResponse(BaseModel):
    result_id: str
    status: str

    # Verdict
    is_deepfake: bool | None
    verdict: str | None
    deepfake_probability: float | None
    authenticity_score: float | None
    confidence: float | None
    synthesis_type: str | None
    detected_system: str | None

    # Scores
    model_scores: dict[str, float] | None
    prosodic_anomaly_score: float | None
    spectral_artifact_score: float | None
    glottal_inconsistency_score: float | None
    environmental_noise_score: float | None

    # Temporal
    chunk_results: list[dict] | None
    flagged_segments: list[dict] | None

    # Speaker
    speaker_count: int | None
    per_speaker_results: list[dict] | None

    # Provenance
    audio_hash_sha256: str | None
    audio_duration_seconds: float | None
    processing_time_ms: int | None

    error_message: str | None
    created_at: datetime


class RealtimeDetectionEvent(BaseModel):
    """Streamed over WebSocket during real-time detection."""
    chunk_index: int
    rolling_deepfake_probability: float
    rolling_authenticity_score: float
    is_deepfake: bool
    alert: bool
    timestamp_ms: int


# ══════════════════════════════════════════════════════════════════
#  Voice Library (community voices)
# ══════════════════════════════════════════════════════════════════

class VoiceLibraryFilter(BaseModel):
    language: str | None = None
    gender: str | None = None
    tags: list[str] | None = None
    page: int = 1
    page_size: int = 20


class UsageStatsResponse(BaseModel):
    """Per-organization usage statistics."""
    organization_id: str
    plan: str
    tts_chars_used_this_month: int
    tts_chars_limit: int
    tts_chars_remaining: int
    voice_profiles_count: int
    voice_profiles_limit: int
    generation_jobs_total: int
    detection_jobs_total: int
    reset_date: datetime | None
