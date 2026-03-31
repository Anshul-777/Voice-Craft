"""
VoiceCraft Platform — Generation Job + Detection Result Models
"""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


# ══════════════════════════════════════════════════════════════════
#  GENERATION JOBS
# ══════════════════════════════════════════════════════════════════

class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmotionStyle(str, enum.Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    DISGUSTED = "disgusted"
    SURPRISED = "surprised"
    CALM = "calm"
    EXCITED = "excited"
    WHISPERING = "whispering"
    SHOUTING = "shouting"
    NARRATION = "narration"
    CONVERSATIONAL = "conversational"
    NEWSCAST = "newscast"
    DOCUMENTARY = "documentary"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    voice_profile_id: Mapped[str] = mapped_column(
        ForeignKey("voice_profiles.id"), nullable=False, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # ── Input ──────────────────────────────────────────────────
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")
    emotion: Mapped[EmotionStyle] = mapped_column(
        Enum(EmotionStyle), default=EmotionStyle.NEUTRAL
    )
    speed: Mapped[float] = mapped_column(Float, default=1.0)    # 0.5 – 2.0
    pitch_shift_semitones: Mapped[float] = mapped_column(Float, default=0.0)  # ±12
    temperature: Mapped[float] = mapped_column(Float, default=0.75)  # XTTS creativity
    output_format: Mapped[str] = mapped_column(String(10), default="mp3")
    sample_rate: Mapped[int] = mapped_column(Integer, default=24000)

    # ── SSML / Advanced Controls ───────────────────────────────
    ssml_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_noise_reduction: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Output ─────────────────────────────────────────────────
    output_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    minio_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chars_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Quality ────────────────────────────────────────────────
    mos_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # Mean Opinion Score 1-5
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    voice_profile: Mapped["VoiceProfile"] = relationship("VoiceProfile")  # type: ignore[name-defined]


class VoiceCloneJob(Base):
    """Tracks the async voice cloning / fine-tuning process."""
    __tablename__ = "voice_clone_jobs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    voice_profile_id: Mapped[str] = mapped_column(
        ForeignKey("voice_profiles.id"), nullable=False, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.QUEUED, nullable=False
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_type: Mapped[str] = mapped_column(
        String(50), default="clone"
    )  # clone | fine_tune | enhance

    total_training_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    num_samples: Mapped[int] = mapped_column(Integer, default=0)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    current_epoch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_epochs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)


# ══════════════════════════════════════════════════════════════════
#  DETECTION RESULTS
# ══════════════════════════════════════════════════════════════════

class DeepfakeDetectionResult(Base):
    __tablename__ = "deepfake_detection_results"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.QUEUED, nullable=False
    )

    # ── Input ──────────────────────────────────────────────────
    input_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    minio_input_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_mode: Mapped[str] = mapped_column(
        String(50), default="full"
    )  # full | fast | realtime

    # ── Verdict ────────────────────────────────────────────────
    is_deepfake: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    deepfake_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    authenticity_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Classification ─────────────────────────────────────────
    synthesis_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # tts|voice_conversion|partial|unknown
    detected_tts_system: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # xtts|elevenlabs|naturalspeech|wavenet|etc

    # ── Per-model scores (JSON) ────────────────────────────────
    model_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {aasist: 0.92, rawnet2: 0.88, prosodic: 0.71, spectral: 0.95, glottal: 0.83}

    # ── Temporal analysis ─────────────────────────────────────
    chunk_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # [{start_ms, end_ms, probability, is_deepfake}, ...]
    flagged_segments: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Feature analysis ──────────────────────────────────────
    prosodic_anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    spectral_artifact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    glottal_inconsistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    environmental_noise_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Speaker diarization ───────────────────────────────────
    speaker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_speaker_results: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Provenance / Legal ────────────────────────────────────
    audio_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chain_of_custody_log: Mapped[list | None] = mapped_column(JSON, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
