"""
VoiceCraft Platform — TTS Router
Text-to-speech generation with emotion, speed, pitch, language control.
Supports: async job queue + real-time WebSocket streaming.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db
from app.models.generation_job import GenerationJob, JobStatus
from app.models.user import Organization, UserPlan
from app.models.voice_profile import VoiceProfile, VoiceStatus
from app.schemas import TTSRequest, TTSResponse, TTSJobStatus
from app.services.storage import get_storage
from app.utils.auth import CurrentUser, get_current_user, decode_token

settings = get_settings()

router = APIRouter(prefix="/api/tts", tags=["Text-to-Speech"])

PLAN_CHAR_LIMITS = {
    UserPlan.FREE: settings.FREE_TTS_CHARS_PER_MONTH,
    UserPlan.STARTER: settings.STARTER_TTS_CHARS_PER_MONTH,
    UserPlan.PRO: settings.PRO_TTS_CHARS_PER_MONTH,
    UserPlan.ENTERPRISE: settings.ENTERPRISE_TTS_CHARS_PER_MONTH,
}


# ─────────────────────────────────────────────────────────────────
#  Submit TTS job (async)
# ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=TTSResponse, status_code=202)
async def generate_speech(
    body: TTSRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a TTS synthesis job. Returns job_id immediately.
    Poll /tts/jobs/{job_id} or listen on WS /tts/jobs/{job_id}/stream for completion.
    """
    current_user.require_scope("tts:write")

    # Check plan char limit
    org = (await db.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )).scalar_one_or_none()
    if not org:
        raise HTTPException(500, "Organization not found")

    char_limit = PLAN_CHAR_LIMITS.get(org.plan, settings.FREE_TTS_CHARS_PER_MONTH)
    chars_count = len(body.text)

    if org.tts_chars_used_this_month + chars_count > char_limit:
        raise HTTPException(
            402,
            f"Monthly character limit reached ({char_limit:,}). "
            f"Used: {org.tts_chars_used_this_month:,}. "
            "Upgrade your plan for more capacity.",
        )

    # Validate voice profile exists and is ready
    voice_profile = (await db.execute(
        select(VoiceProfile).where(
            VoiceProfile.id == body.voice_profile_id,
            VoiceProfile.organization_id == current_user.org_id,
            VoiceProfile.status == VoiceStatus.READY,
        )
    )).scalar_one_or_none()

    if not voice_profile:
        raise HTTPException(404, "Voice profile not found or not ready. Please complete voice cloning first.")

    # Validate language support
    if body.language not in settings.SUPPORTED_LANGUAGES:
        raise HTTPException(422, f"Unsupported language: {body.language}")

    # Create job
    job = GenerationJob(
        user_id=current_user.user_id,
        organization_id=current_user.org_id,
        voice_profile_id=body.voice_profile_id,
        status=JobStatus.QUEUED,
        text=body.text,
        language=body.language,
        emotion=body.emotion,
        speed=body.speed,
        pitch_shift_semitones=body.pitch_shift_semitones,
        temperature=body.temperature,
        output_format=body.output_format,
        sample_rate=body.sample_rate,
        enable_noise_reduction=body.enable_noise_reduction,
        ssml_enabled=body.ssml_enabled,
        chars_count=chars_count,
    )
    db.add(job)

    # Optimistically update usage
    org.tts_chars_used_this_month += chars_count
    await db.commit()
    await db.refresh(job)

    # Dispatch Celery task
    from app.workers.tasks import synthesize_tts_task
    task = synthesize_tts_task.delay(job.id)
    job.celery_task_id = task.id
    await db.commit()

    # Estimate completion time
    estimated_s = max(5, chars_count / 100)  # ~100 chars/sec

    return TTSResponse(
        job_id=job.id,
        status="queued",
        voice_profile_id=body.voice_profile_id,
        chars_count=chars_count,
        estimated_seconds=estimated_s,
        message=f"Job queued. Estimated completion: {estimated_s:.0f}s",
    )


# ─────────────────────────────────────────────────────────────────
#  Poll job status + download
# ─────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=TTSJobStatus)
async def get_tts_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("tts:read")
    job = await _get_job_or_404(job_id, current_user.org_id, db)

    download_url = None
    if job.status == JobStatus.COMPLETED and job.minio_object_key:
        storage = get_storage()
        download_url = storage.presigned_get_url(
            settings.MINIO_BUCKET_AUDIO,
            job.minio_object_key,
            expires_seconds=3600,
        )

    return TTSJobStatus(
        job_id=job.id,
        status=job.status.value,
        voice_profile_id=job.voice_profile_id,
        duration_seconds=job.duration_seconds,
        file_size_bytes=job.file_size_bytes,
        processing_time_ms=job.processing_time_ms,
        mos_score=job.mos_score,
        download_url=download_url,
        error_message=job.error_message,
        created_at=job.created_at,
    )


@router.get("/jobs", response_model=list[TTSJobStatus])
async def list_tts_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None),
    voice_profile_id: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("tts:read")

    query = select(GenerationJob).where(
        GenerationJob.organization_id == current_user.org_id
    )
    if status_filter:
        try:
            query = query.where(GenerationJob.status == JobStatus(status_filter))
        except ValueError:
            pass
    if voice_profile_id:
        query = query.where(GenerationJob.voice_profile_id == voice_profile_id)

    query = query.order_by(GenerationJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    jobs = (await db.execute(query)).scalars().all()

    storage = get_storage()
    results = []
    for job in jobs:
        url = None
        if job.status == JobStatus.COMPLETED and job.minio_object_key:
            try:
                url = storage.presigned_get_url(settings.MINIO_BUCKET_AUDIO, job.minio_object_key, 3600)
            except Exception:
                pass
        results.append(TTSJobStatus(
            job_id=job.id, status=job.status.value,
            voice_profile_id=job.voice_profile_id,
            duration_seconds=job.duration_seconds,
            file_size_bytes=job.file_size_bytes,
            processing_time_ms=job.processing_time_ms,
            mos_score=job.mos_score, download_url=url,
            error_message=job.error_message, created_at=job.created_at,
        ))
    return results


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_tts_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_job_or_404(job_id, current_user.org_id, db)
    if job.minio_object_key:
        storage = get_storage()
        storage.delete_object(settings.MINIO_BUCKET_AUDIO, job.minio_object_key)
    job.status = JobStatus.CANCELLED
    await db.commit()


# ─────────────────────────────────────────────────────────────────
#  WebSocket: real-time status stream for a job
# ─────────────────────────────────────────────────────────────────

@router.websocket("/jobs/{job_id}/stream")
async def tts_job_stream(websocket: WebSocket, job_id: str, token: str | None = None):
    """
    WebSocket endpoint that streams TTS job progress in real-time.
    Authenticate via query param: ?token=<access_token>
    Sends JSON messages every second until job completes or fails.
    """
    await websocket.accept()

    # Auth via token query param (standard WS pattern)
    if not token:
        await websocket.send_json({"error": "Missing token"})
        await websocket.close(code=4001)
        return

    try:
        payload = decode_token(token)
        org_id = payload.get("org_id")
        if not org_id:
            raise ValueError("Missing org_id")
    except Exception:
        await websocket.send_json({"error": "Invalid token"})
        await websocket.close(code=4001)
        return

    from app.models.database import AsyncSessionLocal
    from app.services.storage import get_storage

    storage = get_storage()
    max_wait_seconds = 300
    elapsed = 0

    try:
        while elapsed < max_wait_seconds:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(GenerationJob).where(
                        GenerationJob.id == job_id,
                        GenerationJob.organization_id == org_id,
                    )
                )
                job = result.scalar_one_or_none()

            if not job:
                await websocket.send_json({"error": "Job not found"})
                break

            event: dict = {
                "job_id": job_id,
                "status": job.status.value,
                "elapsed_seconds": elapsed,
            }

            if job.status == JobStatus.COMPLETED:
                url = None
                if job.minio_object_key:
                    try:
                        url = storage.presigned_get_url(
                            settings.MINIO_BUCKET_AUDIO, job.minio_object_key, 3600
                        )
                    except Exception:
                        pass
                event.update({
                    "download_url": url,
                    "duration_seconds": job.duration_seconds,
                    "processing_time_ms": job.processing_time_ms,
                    "mos_score": job.mos_score,
                })
                await websocket.send_json(event)
                break

            elif job.status == JobStatus.FAILED:
                event["error_message"] = job.error_message
                await websocket.send_json(event)
                break

            await websocket.send_json(event)
            await asyncio.sleep(1.5)
            elapsed += 2

    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()


# ─────────────────────────────────────────────────────────────────
#  WebSocket: streaming TTS (chunked, low-latency)
# ─────────────────────────────────────────────────────────────────

@router.websocket("/stream")
async def tts_stream_realtime(websocket: WebSocket, token: str | None = None):
    """
    Real-time streaming TTS WebSocket.
    Client sends JSON: {voice_profile_id, text, language, speed, emotion}
    Server streams audio chunks as binary frames (PCM/WAV).
    Enables <500ms time-to-first-audio.
    """
    await websocket.accept()

    if not token:
        await websocket.send_json({"error": "Missing token"})
        await websocket.close(code=4001)
        return

    try:
        payload = decode_token(token)
        org_id = payload.get("org_id")
        user_id = payload.get("user_id")
    except Exception:
        await websocket.send_json({"error": "Invalid token"})
        await websocket.close(code=4001)
        return

    from app.services.voice_cloner import get_voice_cloner
    from app.services.audio_processor import AudioProcessor
    from app.models.database import AsyncSessionLocal
    import soundfile as sf
    import io

    processor = AudioProcessor()
    cloner = get_voice_cloner()

    try:
        while True:
            raw = await websocket.receive_text()
            req = json.loads(raw)

            voice_profile_id = req.get("voice_profile_id")
            text = req.get("text", "")
            language = req.get("language", "en")
            speed = float(req.get("speed", 1.0))
            emotion = req.get("emotion", "neutral")

            if not text or not voice_profile_id:
                await websocket.send_json({"error": "voice_profile_id and text required"})
                continue

            # Fetch voice profile
            async with AsyncSessionLocal() as db:
                profile_result = await db.execute(
                    select(VoiceProfile).where(
                        VoiceProfile.id == voice_profile_id,
                        VoiceProfile.organization_id == org_id,
                        VoiceProfile.status == VoiceStatus.READY,
                    )
                )
                profile = profile_result.scalar_one_or_none()

            if not profile or not profile.speaker_embedding:
                await websocket.send_json({"error": "Voice profile not found or not ready"})
                continue

            await websocket.send_json({"event": "synthesis_started", "text_length": len(text)})

            # Split text into chunks for streaming
            chunk_size = 200
            sentences = _split_into_chunks(text, chunk_size)

            for i, chunk_text in enumerate(sentences):
                if not chunk_text.strip():
                    continue
                try:
                    audio, sr = cloner.synthesize_from_embedding(
                        text=chunk_text,
                        embedding_dict=profile.speaker_embedding,
                        language=language,
                        speed=speed,
                    )

                    if emotion != "neutral":
                        audio = processor.apply_emotion_prosody(audio, sr, emotion)

                    # Send audio as WAV bytes
                    buf = io.BytesIO()
                    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
                    buf.seek(0)
                    audio_bytes = buf.read()

                    await websocket.send_bytes(audio_bytes)
                    await websocket.send_json({
                        "event": "chunk_complete",
                        "chunk_index": i,
                        "total_chunks": len(sentences),
                        "duration_seconds": round(len(audio) / sr, 3),
                    })
                except Exception as e:
                    await websocket.send_json({"error": f"Chunk {i} failed: {str(e)}"})

            await websocket.send_json({"event": "synthesis_complete", "total_chunks": len(sentences)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        await websocket.close()


# ─────────────────────────────────────────────────────────────────
#  Capabilities
# ─────────────────────────────────────────────────────────────────

@router.get("/capabilities")
async def get_capabilities():
    """Return supported languages, emotions, formats — no auth required."""
    from app.services.voice_cloner import get_voice_cloner
    cloner = get_voice_cloner()
    return {
        "languages": cloner.supported_languages,
        "emotions": [
            "neutral", "happy", "sad", "angry", "fearful", "disgusted",
            "surprised", "calm", "excited", "whispering", "shouting",
            "narration", "conversational", "newscast", "documentary",
        ],
        "output_formats": ["wav", "mp3", "ogg", "flac"],
        "speed_range": {"min": 0.5, "max": 2.0},
        "pitch_shift_range_semitones": {"min": -12, "max": 12},
        "max_text_length": settings.MAX_TTS_TEXT_LENGTH,
        "model": cloner.get_model_info(),
        "streaming_supported": True,
    }


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

async def _get_job_or_404(job_id: str, org_id: str, db: AsyncSession) -> GenerationJob:
    result = await db.execute(
        select(GenerationJob).where(
            GenerationJob.id == job_id,
            GenerationJob.organization_id == org_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "TTS job not found")
    return job


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text at sentence boundaries for streaming."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) <= max_chars:
            current += (" " if current else "") + s
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks if chunks else [text]
