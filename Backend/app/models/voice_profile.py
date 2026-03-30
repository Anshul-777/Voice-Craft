"""
VoiceCraft Platform — Voice Profile Models
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class VoiceStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FINE_TUNING = "fine_tuning"
    FAILED = "failed"
    ARCHIVED = "archived"


class VoiceGender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class VoiceAge(str, enum.Enum):
    YOUNG = "young"
    MIDDLE_AGED = "middle_aged"
    SENIOR = "senior"
    UNKNOWN = "unknown"


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[VoiceStatus] = mapped_column(
        Enum(VoiceStatus), default=VoiceStatus.PENDING, nullable=False, index=True
    )

    # ── Audio source ───────────────────────────────────────────
    reference_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reference_audio_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_audio_count: Mapped[int] = mapped_column(Integer, default=0)
    total_training_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Voice characteristics (auto-detected) ──────────────────
    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    detected_gender: Mapped[VoiceGender] = mapped_column(
        Enum(VoiceGender), default=VoiceGender.UNKNOWN
    )
    detected_age: Mapped[VoiceAge] = mapped_column(
        Enum(VoiceAge), default=VoiceAge.UNKNOWN
    )
    mean_fundamental_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaking_rate_wpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    snr_db: Mapped[float | None] = mapped_column(Float, nullable=True)  # signal-to-noise ratio

    # ── Fine-tuning ────────────────────────────────────────────
    is_fine_tuned: Mapped[bool] = mapped_column(Boolean, default=False)
    fine_tune_model_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fine_tune_epochs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fine_tune_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # ── Speaker embedding (stored as JSON float list) ──────────
    speaker_embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Quality scores ─────────────────────────────────────────
    clone_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_to_original: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Metadata / Tags ────────────────────────────────────────
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)  # share in community
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # pre-built system voices
    preview_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Usage stats ────────────────────────────────────────────
    generation_count: Mapped[int] = mapped_column(Integer, default=0)
    total_chars_generated: Mapped[int] = mapped_column(Integer, default=0)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="voice_profiles")  # type: ignore[name-defined]
    training_samples: Mapped[list["TrainingSample"]] = relationship(
        "TrainingSample", back_populates="voice_profile", cascade="all, delete-orphan"
    )


class TrainingSample(Base):
    __tablename__ = "training_samples"

    voice_profile_id: Mapped[str] = mapped_column(
        ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    minio_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, default=1)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    snr_db: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    transcription: Mapped[str | None] = mapped_column(Text, nullable=True)

    voice_profile: Mapped["VoiceProfile"] = relationship(
        "VoiceProfile", back_populates="training_samples"
    )
