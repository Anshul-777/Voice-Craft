"""
VoiceCraft Platform — Voice Clone Router
Handles voice profile CRUD, audio upload, clone job management.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db
from app.models.generation_job import JobStatus, VoiceCloneJob
from app.models.user import Organization, UserPlan
from app.models.voice_profile import TrainingSample, VoiceProfile, VoiceStatus
from app.schemas import (
    AudioQualityReport,
    CloneJobStatus,
    UploadSampleResponse,
    VoiceCreateRequest,
    VoiceProfileListResponse,
    VoiceProfileResponse,
    VoiceUpdateRequest,
    UsageStatsResponse,
)
from app.services.audio_processor import AudioProcessor
from app.services.storage import get_storage, StorageService
from app.utils.auth import CurrentUser, get_current_user

settings = get_settings()

router = APIRouter(prefix="/api/voices", tags=["Voice Cloning"])

PLAN_PROFILE_LIMITS = {
    UserPlan.FREE: settings.FREE_VOICE_PROFILES_MAX,
    UserPlan.STARTER: settings.STARTER_VOICE_PROFILES_MAX,
    UserPlan.PRO: settings.PRO_VOICE_PROFILES_MAX,
    UserPlan.ENTERPRISE: settings.ENTERPRISE_VOICE_PROFILES_MAX,
}


# ─────────────────────────────────────────────────────────────────
#  Create voice profile
# ─────────────────────────────────────────────────────────────────

@router.post("", response_model=VoiceProfileResponse, status_code=201)
async def create_voice_profile(
    body: VoiceCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("clone:write")

    # Check plan limits
    org_result = await db.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(500, "Organization not found")

    limit = PLAN_PROFILE_LIMITS.get(org.plan, 2)
    count_result = await db.execute(
        select(func.count(VoiceProfile.id)).where(
            VoiceProfile.organization_id == current_user.org_id,
            VoiceProfile.status != VoiceStatus.ARCHIVED,
        )
    )
    current_count = count_result.scalar_one()
    if current_count >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Voice profile limit reached ({limit}). Upgrade your plan.",
        )

    profile = VoiceProfile(
        name=body.name,
        description=body.description,
        organization_id=current_user.org_id,
        owner_id=current_user.user_id,
        tags=body.tags,
        is_public=body.is_public,
        status=VoiceStatus.PENDING,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


# ─────────────────────────────────────────────────────────────────
#  List voice profiles
# ─────────────────────────────────────────────────────────────────

@router.get("", response_model=VoiceProfileListResponse)
async def list_voice_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("clone:read")

    query = select(VoiceProfile).where(
        VoiceProfile.organization_id == current_user.org_id,
        VoiceProfile.status != VoiceStatus.ARCHIVED,
    )
    if status_filter:
        try:
            query = query.where(VoiceProfile.status == VoiceStatus(status_filter))
        except ValueError:
            pass

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = query.offset((page - 1) * page_size).limit(page_size).order_by(
        VoiceProfile.created_at.desc()
    )
    profiles = (await db.execute(query)).scalars().all()

    storage = get_storage()
    result_profiles = []
    for p in profiles:
        p_dict = VoiceProfileResponse.model_validate(p)
        if p.preview_audio_path:
            try:
                p_dict.preview_audio_url = storage.presigned_get_url(
                    settings.MINIO_BUCKET_VOICES, p.preview_audio_path, expires_seconds=3600
                )
            except Exception:
                p_dict.preview_audio_url = None
        result_profiles.append(p_dict)

    return VoiceProfileListResponse(
        voices=result_profiles, total=total, page=page, page_size=page_size
    )


# ─────────────────────────────────────────────────────────────────
#  Get single voice profile
# ─────────────────────────────────────────────────────────────────

@router.get("/{profile_id}", response_model=VoiceProfileResponse)
async def get_voice_profile(
    profile_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("clone:read")
    profile = await _get_profile_or_404(profile_id, current_user.org_id, db)

    response = VoiceProfileResponse.model_validate(profile)
    if profile.preview_audio_path:
        try:
            storage = get_storage()
            response.preview_audio_url = storage.presigned_get_url(
                settings.MINIO_BUCKET_VOICES, profile.preview_audio_path, expires_seconds=3600
            )
        except Exception:
            pass
    return response


@router.patch("/{profile_id}", response_model=VoiceProfileResponse)
async def update_voice_profile(
    profile_id: str,
    body: VoiceUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("clone:write")
    profile = await _get_profile_or_404(profile_id, current_user.org_id, db)

    if body.name is not None:
        profile.name = body.name
    if body.description is not None:
        profile.description = body.description
    if body.tags is not None:
        profile.tags = body.tags
    if body.is_public is not None:
        profile.is_public = body.is_public

    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_voice_profile(
    profile_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("clone:write")
    profile = await _get_profile_or_404(profile_id, current_user.org_id, db)
    profile.status = VoiceStatus.ARCHIVED
    await db.commit()


# ─────────────────────────────────────────────────────────────────
#  Upload training audio samples
# ─────────────────────────────────────────────────────────────────

@router.post("/{profile_id}/samples", response_model=UploadSampleResponse, status_code=201)
async def upload_training_sample(
    profile_id: str,
    audio_file: UploadFile = File(..., description="Audio file (wav/mp3/ogg/flac, max 100MB)"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a voice training sample. Upload multiple samples (total 1–5 min)
    for zero-shot cloning, or more for fine-tuning.
    Accepted formats: wav, mp3, ogg, flac, m4a, aac.
    """
    current_user.require_scope("clone:write")
    profile = await _get_profile_or_404(profile_id, current_user.org_id, db)

    if profile.status == VoiceStatus.PROCESSING:
        raise HTTPException(409, "Voice profile is currently being processed")

    # Validate file size
    content = await audio_file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large. Max: {settings.MAX_UPLOAD_SIZE_MB}MB")

    # Validate file extension
    suffix = Path(audio_file.filename or "audio.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}:
        raise HTTPException(415, f"Unsupported audio format: {suffix}")

    storage = get_storage()
    processor = AudioProcessor()

    # Write to temp file for analysis
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Analyze audio quality
        audio, sr = processor.load_audio(tmp_path)
        info = processor.analyze(tmp_path, audio, sr)

        quality_report = AudioQualityReport(
            duration_seconds=info.duration_seconds,
            snr_db=info.snr_db,
            speech_ratio=info.speech_ratio,
            is_acceptable=info.is_acceptable_quality,
            quality_flags=info.quality_flags,
            mean_fundamental_frequency=info.mean_f0,
            rms_db=info.rms_db,
            recommendation=_get_quality_recommendation(info),
        )

        if not info.is_speech_present:
            raise HTTPException(422, "No speech detected in uploaded audio. Please upload a recording with clear speech.")

        if info.duration_seconds < settings.MIN_CLONE_AUDIO_SECONDS:
            raise HTTPException(
                422,
                f"Audio too short ({info.duration_seconds:.1f}s). Minimum: {settings.MIN_CLONE_AUDIO_SECONDS}s"
            )

        # Upload to MinIO
        sample_id = str(uuid.uuid4())
        object_key = StorageService.training_sample_key(
            current_user.org_id, profile_id, sample_id, ext=suffix.lstrip(".")
        )
        storage.upload_bytes(
            settings.MINIO_BUCKET_VOICES, object_key, content,
            content_type=audio_file.content_type or "audio/wav",
            metadata={
                "voice_profile_id": profile_id,
                "duration": str(info.duration_seconds),
                "snr_db": str(info.snr_db),
            },
        )

        # Save to DB
        sample = TrainingSample(
            id=sample_id,
            voice_profile_id=profile_id,
            file_path=object_key,
            minio_object_key=object_key,
            duration_seconds=info.duration_seconds,
            sample_rate=sr,
            channels=1,
            file_size_bytes=len(content),
            snr_db=info.snr_db,
        )
        db.add(sample)

        # Update profile totals
        profile.total_training_seconds += info.duration_seconds
        profile.reference_audio_count += 1
        await db.commit()
        await db.refresh(profile)

        total_dur = profile.total_training_seconds
        is_ready = (
            total_dur >= settings.MIN_CLONE_AUDIO_SECONDS
            and info.is_speech_present
        )

        return UploadSampleResponse(
            sample_id=sample_id,
            voice_profile_id=profile_id,
            duration_seconds=info.duration_seconds,
            quality_report=quality_report,
            total_training_seconds=total_dur,
            is_ready_for_cloning=is_ready,
            message=(
                f"Sample uploaded ({info.duration_seconds:.1f}s). "
                f"Total: {total_dur:.1f}s. "
                + ("Ready to clone!" if is_ready else f"Upload more audio ({max(0, settings.MIN_CLONE_AUDIO_SECONDS - total_dur):.1f}s more needed).")
            ),
        )

    finally:
        tmp_path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────
#  Start cloning job
# ─────────────────────────────────────────────────────────────────

@router.post("/{profile_id}/clone", response_model=CloneJobStatus, status_code=202)
async def start_clone_job(
    profile_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start zero-shot voice cloning. Requires ≥6s of uploaded audio.
    Processing happens async — poll /clone-jobs/{job_id} for status.
    """
    current_user.require_scope("clone:write")
    profile = await _get_profile_or_404(profile_id, current_user.org_id, db)

    if profile.total_training_seconds < settings.MIN_CLONE_AUDIO_SECONDS:
        raise HTTPException(
            422,
            f"Not enough audio. Need {settings.MIN_CLONE_AUDIO_SECONDS}s, have {profile.total_training_seconds:.1f}s",
        )

    if profile.status in (VoiceStatus.PROCESSING, VoiceStatus.FINE_TUNING):
        raise HTTPException(409, "Clone job already running")

    # Create clone job
    clone_job = VoiceCloneJob(
        user_id=current_user.user_id,
        organization_id=current_user.org_id,
        voice_profile_id=profile_id,
        status=JobStatus.QUEUED,
        job_type="clone",
        total_training_seconds=profile.total_training_seconds,
    )
    db.add(clone_job)
    profile.status = VoiceStatus.PROCESSING
    await db.commit()
    await db.refresh(clone_job)

    # Dispatch Celery task
    from app.workers.tasks import clone_voice_task
    task = clone_voice_task.delay(profile_id, clone_job.id)
    clone_job.celery_task_id = task.id
    await db.commit()

    return CloneJobStatus(
        job_id=clone_job.id,
        voice_profile_id=profile_id,
        status=clone_job.status.value,
        progress_pct=0,
        current_epoch=None,
        total_epochs=None,
        job_type="clone",
        quality_score=None,
        error_message=None,
        created_at=clone_job.created_at,
    )


@router.post("/{profile_id}/fine-tune", response_model=CloneJobStatus, status_code=202)
async def start_fine_tune_job(
    profile_id: str,
    num_epochs: int = Query(5, ge=1, le=20),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fine-tune XTTS-v2 on your voice samples for maximum quality.
    Requires ≥60s of audio. Processing takes 10–60 min depending on GPU.
    """
    current_user.require_scope("clone:write")
    profile = await _get_profile_or_404(profile_id, current_user.org_id, db)

    if profile.total_training_seconds < settings.FINE_TUNE_MIN_SECONDS:
        raise HTTPException(
            422,
            f"Fine-tuning requires ≥{settings.FINE_TUNE_MIN_SECONDS}s of audio. "
            f"You have {profile.total_training_seconds:.1f}s. Upload more samples.",
        )

    # Plan check: fine-tuning requires Pro+
    org_result = await db.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )
    org = org_result.scalar_one_or_none()
    if org and org.plan in (UserPlan.FREE, UserPlan.STARTER):
        raise HTTPException(
            402,
            "Fine-tuning requires Pro or Enterprise plan. "
            "Zero-shot cloning is available on Starter.",
        )

    clone_job = VoiceCloneJob(
        user_id=current_user.user_id,
        organization_id=current_user.org_id,
        voice_profile_id=profile_id,
        status=JobStatus.QUEUED,
        job_type="fine_tune",
        total_training_seconds=profile.total_training_seconds,
        total_epochs=num_epochs,
    )
    db.add(clone_job)
    profile.status = VoiceStatus.FINE_TUNING
    await db.commit()
    await db.refresh(clone_job)

    from app.workers.tasks import fine_tune_task
    task = fine_tune_task.delay(profile_id, clone_job.id, num_epochs)
    clone_job.celery_task_id = task.id
    await db.commit()

    return CloneJobStatus(
        job_id=clone_job.id,
        voice_profile_id=profile_id,
        status="queued",
        progress_pct=0,
        current_epoch=0,
        total_epochs=num_epochs,
        job_type="fine_tune",
        quality_score=None,
        error_message=None,
        created_at=clone_job.created_at,
    )


@router.get("/clone-jobs/{job_id}", response_model=CloneJobStatus)
async def get_clone_job_status(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("clone:read")
    result = await db.execute(
        select(VoiceCloneJob).where(
            VoiceCloneJob.id == job_id,
            VoiceCloneJob.organization_id == current_user.org_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Clone job not found")

    return CloneJobStatus(
        job_id=job.id,
        voice_profile_id=job.voice_profile_id,
        status=job.status.value,
        progress_pct=job.progress_pct,
        current_epoch=job.current_epoch,
        total_epochs=job.total_epochs,
        job_type=job.job_type,
        quality_score=job.quality_score,
        error_message=job.error_message,
        created_at=job.created_at,
    )


# ─────────────────────────────────────────────────────────────────
#  Voice Library (community / system voices)
# ─────────────────────────────────────────────────────────────────

@router.get("/library/public", response_model=VoiceProfileListResponse)
async def list_public_voices(
    language: str | None = Query(None),
    gender: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Browse community-shared and system voice profiles."""
    query = select(VoiceProfile).where(
        VoiceProfile.is_public == True,
        VoiceProfile.status == VoiceStatus.READY,
    )
    if language:
        query = query.where(VoiceProfile.detected_language == language)
    if gender:
        query = query.where(VoiceProfile.detected_gender == gender)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    query = query.offset((page - 1) * page_size).limit(page_size)
    profiles = (await db.execute(query)).scalars().all()

    return VoiceProfileListResponse(
        voices=[VoiceProfileResponse.model_validate(p) for p in profiles],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/library/{profile_id}/clone-to-my-workspace", response_model=VoiceProfileResponse, status_code=201)
async def clone_public_voice_to_workspace(
    profile_id: str,
    name: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Copy a public/community voice profile into your own workspace.
    Copies the speaker embedding — no reprocessing needed.
    """
    current_user.require_scope("clone:write")
    source_result = await db.execute(
        select(VoiceProfile).where(
            VoiceProfile.id == profile_id,
            VoiceProfile.is_public == True,
            VoiceProfile.status == VoiceStatus.READY,
        )
    )
    source = source_result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Public voice profile not found")

    new_profile = VoiceProfile(
        name=name,
        description=f"Cloned from: {source.name}",
        organization_id=current_user.org_id,
        owner_id=current_user.user_id,
        status=VoiceStatus.READY,
        detected_language=source.detected_language,
        detected_gender=source.detected_gender,
        detected_age=source.detected_age,
        mean_fundamental_frequency=source.mean_fundamental_frequency,
        speaker_embedding=source.speaker_embedding,
        reference_audio_path=source.reference_audio_path,
        preview_audio_path=source.preview_audio_path,
        clone_quality_score=source.clone_quality_score,
        total_training_seconds=source.total_training_seconds,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)
    return new_profile


# ─────────────────────────────────────────────────────────────────
#  Usage stats
# ─────────────────────────────────────────────────────────────────

@router.get("/usage/stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.generation_job import GenerationJob, DeepfakeDetectionResult
    org_result = await db.execute(
        select(Organization).where(Organization.id == current_user.org_id)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(500, "Organization not found")

    plan_limits = {
        UserPlan.FREE: settings.FREE_TTS_CHARS_PER_MONTH,
        UserPlan.STARTER: settings.STARTER_TTS_CHARS_PER_MONTH,
        UserPlan.PRO: settings.PRO_TTS_CHARS_PER_MONTH,
        UserPlan.ENTERPRISE: settings.ENTERPRISE_TTS_CHARS_PER_MONTH,
    }
    chars_limit = plan_limits.get(org.plan, settings.FREE_TTS_CHARS_PER_MONTH)

    voice_count = (await db.execute(
        select(func.count(VoiceProfile.id)).where(
            VoiceProfile.organization_id == org.id,
            VoiceProfile.status != VoiceStatus.ARCHIVED,
        )
    )).scalar_one()

    gen_count = (await db.execute(
        select(func.count(GenerationJob.id)).where(
            GenerationJob.organization_id == org.id
        )
    )).scalar_one()

    detect_count = (await db.execute(
        select(func.count(DeepfakeDetectionResult.id)).where(
            DeepfakeDetectionResult.organization_id == org.id
        )
    )).scalar_one()

    return UsageStatsResponse(
        organization_id=org.id,
        plan=org.plan.value,
        tts_chars_used_this_month=org.tts_chars_used_this_month,
        tts_chars_limit=chars_limit,
        tts_chars_remaining=max(0, chars_limit - org.tts_chars_used_this_month),
        voice_profiles_count=voice_count,
        voice_profiles_limit=PLAN_PROFILE_LIMITS.get(org.plan, 2),
        generation_jobs_total=gen_count,
        detection_jobs_total=detect_count,
        reset_date=org.tts_chars_reset_date,
    )


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

async def _get_profile_or_404(
    profile_id: str, org_id: str, db: AsyncSession
) -> VoiceProfile:
    result = await db.execute(
        select(VoiceProfile).where(
            VoiceProfile.id == profile_id,
            VoiceProfile.organization_id == org_id,
            VoiceProfile.status != VoiceStatus.ARCHIVED,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Voice profile not found")
    return profile


def _get_quality_recommendation(info) -> str:
    if info.snr_db >= 25 and info.speech_ratio >= 0.7:
        return "Excellent quality — ideal for voice cloning."
    elif info.snr_db >= 15 and info.speech_ratio >= 0.5:
        return "Good quality. Results will be strong."
    elif info.snr_db >= 10:
        return "Acceptable. Use noise reduction or record in quieter environment for better results."
    else:
        return "Low quality detected. Record in a quiet room, close to microphone, for best results."
