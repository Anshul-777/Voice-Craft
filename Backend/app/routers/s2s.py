"""
VoiceCraft Platform — Speech-to-Speech (S2S) Deepfake Router
Upload an audio file -> Transcribe (Whisper) -> Synthesize in Target Voice (XTTS).
"""
from __future__ import annotations

import os
import tempfile
import whisper
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db
from app.models.generation_job import GenerationJob, JobStatus
from app.models.user import Organization
from app.models.voice_profile import VoiceProfile, VoiceStatus
from app.utils.auth import CurrentUser, get_current_user
from app.schemas import TTSResponse

settings = get_settings()

router = APIRouter(prefix="/api/s2s", tags=["Speech-to-Speech Deepfake"])

@router.post("/generate", response_model=TTSResponse, status_code=202)
async def generate_speech_to_speech(
    source_audio: UploadFile = File(...),
    voice_profile_id: str = Form(...),
    emotion: str = Form("neutral"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a Speech-to-Speech generation job.
    1. Transcribes incoming audio using local Whisper.
    2. Builds a TTS generation job for the target Voice Identity.
    """
    current_user.require_scope("tts:write")

    # 1. Transcribe the audio
    try:
        # Save uploaded file temporarily
        suffix = os.path.splitext(source_audio.filename or ".wav")[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await source_audio.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Load whisper and transcribe
        model = whisper.load_model(settings.WHISPER_MODEL_SIZE)
        result = model.transcribe(tmp_path)
        transcribed_text = result["text"].strip()
        
        # Cleanup temp file
        os.remove(tmp_path)
        
        if not transcribed_text:
            raise ValueError("No speech detected in the audio file.")

    except Exception as e:
        raise HTTPException(422, f"Audio analysis failed: {str(e)}")

    # 2. Emulate a standard TTS request using the transcribed text
    org = (await db.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )).scalar_one_or_none()
    
    if not org:
        raise HTTPException(500, "Organization not found")

    # If it's a system template, we bypass the VoiceProfile check or allow it
    is_system_voice = voice_profile_id.startswith("sys-")
    
    if not is_system_voice:
        voice_profile = (await db.execute(
            select(VoiceProfile).where(
                VoiceProfile.id == voice_profile_id,
                VoiceProfile.organization_id == current_user.org_id,
                VoiceProfile.status == VoiceStatus.READY,
            )
        )).scalar_one_or_none()

        if not voice_profile:
            raise HTTPException(404, "Voice profile not found or not ready.")

    chars_count = len(transcribed_text)
    
    job = GenerationJob(
        user_id=current_user.user_id,
        organization_id=current_user.org_id,
        voice_profile_id=voice_profile_id,
        status=JobStatus.QUEUED,
        text=transcribed_text,
        language="en",
        emotion=emotion,
        speed=1.0,
        pitch_shift_semitones=0,
        temperature=0.7,
        output_format="wav",
        sample_rate=24000,
        enable_noise_reduction=True,
        ssml_enabled=False,
        chars_count=chars_count,
    )
    db.add(job)

    org.tts_chars_used_this_month += chars_count
    await db.commit()
    await db.refresh(job)

    # Dispatch to Celery
    from app.workers.tasks import synthesize_tts_task
    task = synthesize_tts_task.delay(job.id)
    job.celery_task_id = task.id
    await db.commit()

    return TTSResponse(
        job_id=job.id,
        status="queued",
        voice_profile_id=voice_profile_id,
        chars_count=chars_count,
        estimated_seconds=max(5, chars_count / 100),
        message=f"Deepfake speech conversion queued. Script: '{transcribed_text[:50]}...'",
    )
