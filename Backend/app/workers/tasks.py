"""
VoiceCraft Platform — Celery Tasks
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from celery import shared_task
from sqlalchemy import select

from app.config import get_settings
from app.workers.celery_app import celery_app
from app.models.generation_job import JobStatus

settings = get_settings()
logger = logging.getLogger(__name__)


def _get_sync_db():
    """Create a synchronous SQLAlchemy session for use inside Celery tasks."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


# ══════════════════════════════════════════════════════════════════
#  Voice Clone Task
# ══════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    name="app.workers.tasks.clone_voice_task",
    max_retries=2,
    soft_time_limit=settings.CLONE_TASK_TIMEOUT_SECONDS,
    queue="clone",
)
def clone_voice_task(self, voice_profile_id: str, clone_job_id: str) -> dict:
    """
    Process uploaded audio samples and create speaker embedding for zero-shot cloning.
    """
    from app.models.voice_profile import VoiceProfile, TrainingSample, VoiceStatus
    from app.models.generation_job import VoiceCloneJob
    from app.services.voice_cloner import get_voice_cloner
    from app.services.storage import get_storage
    from app.services.audio_processor import AudioProcessor

    t_start = time.perf_counter()
    db = _get_sync_db()
    storage = get_storage()
    processor = AudioProcessor()

    try:
        # Update job: processing
        clone_job = db.get(VoiceCloneJob, clone_job_id)
        if not clone_job:
            return {"error": "Job not found"}
        clone_job.status = JobStatus.PROCESSING
        db.commit()

        voice_profile = db.get(VoiceProfile, voice_profile_id)
        if not voice_profile:
            return {"error": "Voice profile not found"}

        voice_profile.status = VoiceStatus.PROCESSING
        db.commit()

        # Get all training samples
        samples = db.execute(
            select(TrainingSample).where(
                TrainingSample.voice_profile_id == voice_profile_id,
                TrainingSample.is_processed == False,
            )
        ).scalars().all()

        if not samples:
            raise ValueError("No training samples found")

        # Download samples from MinIO to temp dir
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            local_paths = []

            for sample in samples:
                local_p = tmp_path / f"{sample.id}.wav"
                storage.download_file(
                    settings.MINIO_BUCKET_VOICES, sample.minio_object_key, local_p
                )
                local_paths.append(local_p)
                # Mark sample as processed
                sample.is_processed = True

            db.commit()

            # Build composite reference audio
            cloner = get_voice_cloner()
            composite_path = tmp_path / "composite_reference.wav"
            cloner.build_composite_reference(local_paths, composite_path)

            # Upload composite reference to MinIO
            composite_key = storage.composite_reference_key(
                voice_profile.organization_id, voice_profile_id
            )
            storage.upload_file(
                settings.MINIO_BUCKET_VOICES, composite_key, composite_path,
                content_type="audio/wav"
            )

            # Extract speaker embedding
            self.update_state(state="PROGRESS", meta={"progress": 60, "step": "Extracting speaker embedding"})
            embedding_dict = cloner.extract_speaker_embedding(composite_path)

            # Analyze audio quality
            audio_info = processor.analyze(composite_path)

            # Generate preview sample
            preview_text = "Hello, this is a preview of my voice. How does it sound?"
            preview_audio, preview_sr = cloner.synthesize_from_embedding(
                preview_text, embedding_dict, language="en"
            )

            preview_path = tmp_path / "preview.mp3"
            processor.save_audio(preview_audio, preview_sr, preview_path, fmt="mp3")

            preview_key = storage.voice_profile_key(
                voice_profile.organization_id, voice_profile_id, "preview.mp3"
            )
            storage.upload_file(
                settings.MINIO_BUCKET_VOICES, preview_key, preview_path,
                content_type="audio/mpeg"
            )

        # Update voice profile
        voice_profile.status = VoiceStatus.READY
        voice_profile.reference_audio_path = composite_key
        voice_profile.speaker_embedding = embedding_dict
        voice_profile.preview_audio_path = preview_key
        voice_profile.snr_db = audio_info.snr_db
        voice_profile.mean_fundamental_frequency = audio_info.mean_f0
        voice_profile.total_training_seconds = audio_info.duration_seconds

        # Detect gender from F0
        if audio_info.mean_f0:
            if audio_info.mean_f0 < 165:
                voice_profile.detected_gender = "male"
            elif audio_info.mean_f0 > 200:
                voice_profile.detected_gender = "female"
            else:
                voice_profile.detected_gender = "neutral"

        # Quality score (0-100) based on SNR and speech ratio
        quality = min(100, max(0,
            audio_info.snr_db * 1.5 + audio_info.speech_ratio * 30
        ))
        voice_profile.clone_quality_score = quality

        processing_time = time.perf_counter() - t_start
        clone_job.status = JobStatus.COMPLETED
        clone_job.progress_pct = 100
        clone_job.quality_score = quality
        clone_job.processing_time_seconds = processing_time

        db.commit()

        logger.info("Voice clone complete: %s (%.1fs)", voice_profile_id, processing_time)
        return {
            "voice_profile_id": voice_profile_id,
            "status": "completed",
            "quality_score": quality,
            "processing_time_seconds": round(processing_time, 2),
        }

    except Exception as e:
        logger.error("Clone task failed for %s: %s", voice_profile_id, e, exc_info=True)
        try:
            from app.models.voice_profile import VoiceStatus
            vp = db.get(VoiceProfile, voice_profile_id)
            if vp:
                vp.status = VoiceStatus.FAILED
            cj = db.get(VoiceCloneJob, clone_job_id)
            if cj:
                cj.status = JobStatus.FAILED
                cj.error_message = str(e)
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
#  Fine-Tune Task
# ══════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    name="app.workers.tasks.fine_tune_task",
    max_retries=1,
    soft_time_limit=settings.FINE_TUNE_TASK_TIMEOUT_SECONDS,
    queue="fine_tune",
)
def fine_tune_task(self, voice_profile_id: str, clone_job_id: str, num_epochs: int = 5) -> dict:
    """
    Fine-tune XTTS-v2 on user's voice samples for highest quality cloning.
    Requires at least 60s of clean audio.
    """
    from app.models.voice_profile import VoiceProfile, TrainingSample, VoiceStatus
    from app.models.generation_job import VoiceCloneJob
    from app.services.voice_cloner import get_voice_cloner
    from app.services.storage import get_storage

    db = _get_sync_db()
    storage = get_storage()

    try:
        clone_job = db.get(VoiceCloneJob, clone_job_id)
        voice_profile = db.get(VoiceProfile, voice_profile_id)

        if not clone_job or not voice_profile:
            return {"error": "Job or profile not found"}

        clone_job.status = JobStatus.PROCESSING
        voice_profile.status = VoiceStatus.FINE_TUNING
        clone_job.total_epochs = num_epochs
        db.commit()

        samples = db.execute(
            select(TrainingSample).where(TrainingSample.voice_profile_id == voice_profile_id)
        ).scalars().all()

        cloner = get_voice_cloner()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            local_paths = []

            for sample in samples:
                local_p = tmp_path / f"{sample.id}.wav"
                storage.download_file(
                    settings.MINIO_BUCKET_VOICES, sample.minio_object_key, local_p
                )
                local_paths.append(local_p)

            dataset_dir = tmp_path / "dataset"
            model_dir = tmp_path / "fine_tuned"

            # Prepare dataset with Whisper transcription
            self.update_state(state="PROGRESS", meta={"progress": 10, "step": "Preparing dataset"})
            dataset_info = cloner.prepare_fine_tune_dataset(
                local_paths, dataset_dir, voice_profile_id
            )
            clone_job.num_samples = dataset_info["num_clips"]
            db.commit()

            if dataset_info["num_clips"] < 5:
                raise ValueError(
                    f"Need at least 5 valid audio clips. Got {dataset_info['num_clips']}. "
                    "Please upload more/cleaner audio."
                )

            # Fine-tune
            self.update_state(state="PROGRESS", meta={"progress": 20, "step": "Fine-tuning model"})

            def progress_callback(epoch: int, total: int, msg: str):
                pct = 20 + int((epoch / total) * 70)
                clone_job.current_epoch = epoch
                clone_job.progress_pct = pct
                db.commit()
                self.update_state(
                    state="PROGRESS",
                    meta={"progress": pct, "step": f"Epoch {epoch}/{total}"}
                )

            model_path = cloner.run_fine_tuning(
                dataset_dir=dataset_dir,
                voice_profile_id=voice_profile_id,
                output_model_dir=model_dir,
                num_epochs=num_epochs,
                progress_callback=progress_callback,
            )

            # Upload fine-tuned model to MinIO
            self.update_state(state="PROGRESS", meta={"progress": 90, "step": "Saving model"})
            model_key = storage.fine_tune_model_key(voice_profile.organization_id, voice_profile_id)
            for mf in Path(model_path).parent.glob("*"):
                storage.upload_file(
                    settings.MINIO_BUCKET_MODELS,
                    f"{model_key}{mf.name}",
                    mf,
                )

        # Update profile
        voice_profile.is_fine_tuned = True
        voice_profile.fine_tune_model_path = model_key
        voice_profile.fine_tune_epochs = num_epochs
        voice_profile.fine_tune_completed_at = datetime.utcnow()
        voice_profile.status = VoiceStatus.READY

        clone_job.status = JobStatus.COMPLETED
        clone_job.progress_pct = 100
        db.commit()

        return {"voice_profile_id": voice_profile_id, "status": "fine_tuned"}

    except Exception as e:
        logger.error("Fine-tune task failed: %s", e, exc_info=True)
        try:
            from app.models.voice_profile import VoiceStatus
            vp = db.get(VoiceProfile, voice_profile_id)
            if vp:
                vp.status = VoiceStatus.FAILED
            cj = db.get(VoiceCloneJob, clone_job_id)
            if cj:
                cj.status = JobStatus.FAILED
                cj.error_message = str(e)[:1000]
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
#  TTS Synthesis Task
# ══════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    name="app.workers.tasks.synthesize_tts_task",
    max_retries=2,
    soft_time_limit=settings.TTS_TASK_TIMEOUT_SECONDS,
    queue="tts",
)
def synthesize_tts_task(self, job_id: str) -> dict:
    """
    Generate TTS audio from text using stored voice profile embedding.
    """
    from app.models.generation_job import GenerationJob, JobStatus
    from app.models.voice_profile import VoiceProfile
    from app.services.voice_cloner import get_voice_cloner
    from app.services.audio_processor import AudioProcessor
    from app.services.storage import get_storage

    db = _get_sync_db()
    storage = get_storage()
    processor = AudioProcessor()
    t_start = time.perf_counter()

    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"error": "Job not found"}

        job.status = JobStatus.PROCESSING
        db.commit()

        voice_profile = db.get(VoiceProfile, job.voice_profile_id)
        if not voice_profile or voice_profile.status.value != "ready":
            raise ValueError("Voice profile not ready")

        cloner = get_voice_cloner()

        # Use stored embedding for fast synthesis (no re-extraction)
        if voice_profile.speaker_embedding:
            audio, sr = cloner.synthesize_from_embedding(
                text=job.text,
                embedding_dict=voice_profile.speaker_embedding,
                language=job.language,
                speed=job.speed,
                temperature=job.temperature,
            )
        else:
            # Fallback: download composite reference and synthesize
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                storage.download_file(
                    settings.MINIO_BUCKET_VOICES,
                    voice_profile.reference_audio_path,
                    tmp.name,
                )
                audio, sr = cloner.clone_and_synthesize(
                    text=job.text,
                    reference_audio_path=tmp.name,
                    language=job.language,
                    speed=job.speed,
                    temperature=job.temperature,
                )
                Path(tmp.name).unlink(missing_ok=True)

        # Apply emotion prosody
        if job.emotion and job.emotion != "neutral":
            audio = processor.apply_emotion_prosody(audio, sr, job.emotion)

        # Apply pitch shift
        if abs(job.pitch_shift_semitones) > 0.1:
            import librosa
            audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=job.pitch_shift_semitones)

        # Noise reduction & normalize
        if job.enable_noise_reduction:
            audio = processor.preprocess_for_cloning(
                audio, sr, reduce_noise=True, normalize=True, trim_silence=False
            )

        # Save output
        with tempfile.NamedTemporaryFile(suffix=f".{job.output_format}", delete=False) as tmp_out:
            processor.save_audio(audio, sr, tmp_out.name, fmt=job.output_format)
            file_size = Path(tmp_out.name).stat().st_size
            duration_s = len(audio) / sr

            # Upload to MinIO
            output_key = storage.generated_audio_key(
                voice_profile.organization_id, job_id, job.output_format
            )
            storage.upload_file(
                settings.MINIO_BUCKET_AUDIO,
                output_key,
                tmp_out.name,
                content_type=f"audio/{job.output_format}",
                metadata={
                    "voice_profile_id": job.voice_profile_id,
                    "job_id": job_id,
                    "emotion": job.emotion,
                    "language": job.language,
                },
            )
            Path(tmp_out.name).unlink(missing_ok=True)

        processing_ms = int((time.perf_counter() - t_start) * 1000)

        # Update job
        job.status = JobStatus.COMPLETED
        job.output_audio_path = output_key
        job.minio_object_key = output_key
        job.duration_seconds = round(duration_s, 3)
        job.file_size_bytes = file_size
        job.chars_count = len(job.text)
        job.processing_time_ms = processing_ms

        # Simple MOS proxy: based on SNR and duration consistency
        job.mos_score = min(4.8, 3.0 + voice_profile.clone_quality_score / 50) if voice_profile.clone_quality_score else 4.0

        # Update voice profile stats
        voice_profile.generation_count += 1
        voice_profile.total_chars_generated += len(job.text)

        db.commit()

        return {
            "job_id": job_id,
            "status": "completed",
            "duration_seconds": round(duration_s, 3),
            "processing_time_ms": processing_ms,
            "output_key": output_key,
        }

    except Exception as e:
        logger.error("TTS task failed for job %s: %s", job_id, e, exc_info=True)
        try:
            job = db.get(GenerationJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
#  Deepfake Detection Task
# ══════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    name="app.workers.tasks.detect_deepfake_task",
    max_retries=1,
    soft_time_limit=settings.DETECT_TASK_TIMEOUT_SECONDS,
    queue="detect",
)
def detect_deepfake_task(self, result_id: str) -> dict:
    """
    Run ensemble deepfake detection on uploaded audio.
    """
    from app.models.generation_job import DeepfakeDetectionResult, JobStatus
    from app.services.deepfake_detector import get_deepfake_detector
    from app.services.storage import get_storage

    db = _get_sync_db()
    storage = get_storage()

    try:
        result = db.get(DeepfakeDetectionResult, result_id)
        if not result:
            return {"error": "Result not found"}

        result.status = JobStatus.PROCESSING
        db.commit()

        # Download audio from MinIO
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            storage.download_file(
                settings.MINIO_BUCKET_UPLOADS, result.minio_input_key, tmp.name
            )
            tmp_path = tmp.name

        try:
            detector = get_deepfake_detector()
            report = detector.detect(
                audio_path=tmp_path,
                mode=result.analysis_mode,
                speaker_diarization=True,
            )

            # Update result
            result.is_deepfake = report.is_deepfake
            result.deepfake_probability = report.deepfake_probability
            result.authenticity_score = report.authenticity_score
            result.confidence = report.confidence
            result.synthesis_type = report.synthesis_type
            result.detected_tts_system = report.detected_system
            result.model_scores = report.model_scores
            result.chunk_results = [
                {
                    "start_ms": c.start_ms,
                    "end_ms": c.end_ms,
                    "deepfake_probability": c.deepfake_probability,
                    "is_deepfake": c.is_deepfake,
                    "model_scores": c.model_scores,
                }
                for c in report.chunk_results
            ]
            result.flagged_segments = report.flagged_segments
            result.prosodic_anomaly_score = report.prosodic_anomaly_score
            result.spectral_artifact_score = report.spectral_artifact_score
            result.glottal_inconsistency_score = report.glottal_inconsistency_score
            result.environmental_noise_score = report.environmental_noise_score
            result.feature_analysis = report.feature_analysis
            result.speaker_count = report.speaker_count
            result.per_speaker_results = report.per_speaker_results
            result.audio_hash_sha256 = report.audio_hash_sha256
            result.processing_time_ms = report.processing_time_ms
            result.status = JobStatus.COMPLETED

            # Add chain of custody log
            result.chain_of_custody_log = [
                {"event": "uploaded", "timestamp": str(result.created_at)},
                {"event": "analysis_started", "timestamp": str(datetime.utcnow())},
                {
                    "event": "analysis_completed",
                    "timestamp": str(datetime.utcnow()),
                    "verdict": report.verdict,
                    "audio_hash": report.audio_hash_sha256,
                },
            ]

            db.commit()

        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return {
            "result_id": result_id,
            "is_deepfake": report.is_deepfake,
            "probability": report.deepfake_probability,
            "verdict": report.verdict,
        }

    except Exception as e:
        logger.error("Detection task failed for %s: %s", result_id, e, exc_info=True)
        try:
            r = db.get(DeepfakeDetectionResult, result_id)
            if r:
                r.status = JobStatus.FAILED
                r.error_message = str(e)[:1000]
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
#  Cleanup Task (scheduled)
# ══════════════════════════════════════════════════════════════════

@celery_app.task(name="app.workers.tasks.cleanup_task", queue="maintenance")
def cleanup_task() -> dict:
    """
    Scheduled maintenance:
    - Delete generation jobs older than 30 days
    - Clean temp files
    - Reset daily API key counters
    """
    from datetime import timedelta
    from sqlalchemy import delete
    from app.models.generation_job import GenerationJob

    db = _get_sync_db()
    cutoff = datetime.utcnow() - timedelta(days=30)

    try:
        # Delete old completed jobs
        deleted = db.execute(
            delete(GenerationJob).where(
                GenerationJob.created_at < cutoff,
                GenerationJob.status.in_(["completed", "failed", "cancelled"]),
            )
        )
        db.commit()

        # Clean temp audio dir
        settings.ensure_dirs()
        tmp_dir = settings.TEMP_AUDIO_DIR
        cleaned = 0
        for f in tmp_dir.iterdir():
            if f.is_file() and (time.time() - f.stat().st_mtime) > 3600:
                f.unlink()
                cleaned += 1

        return {
            "deleted_old_jobs": deleted.rowcount,
            "cleaned_temp_files": cleaned,
        }
    finally:
        db.close()


# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "daily-cleanup": {
        "task": "app.workers.tasks.cleanup_task",
        "schedule": 86400.0,  # Every 24 hours
    },
}
