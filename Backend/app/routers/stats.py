"""
VoiceCraft Platform — Stats Router
Provides dashboard analytics and usage metrics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import Organization
from app.models.voice_profile import VoiceProfile
from app.models.generation_job import GenerationJob
from app.utils.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/stats", tags=["Stats"])


@router.get("/dashboard")
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get summarized dashboard statistics for the user's organization."""
    org_id = current_user.org_id
    if not org_id:
        return {"summary": {}, "usage": [], "jobs": []}

    # Get Organization
    org_r = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_r.scalar_one_or_none()

    # Get total voices
    voices_count = await db.scalar(
        select(func.count(VoiceProfile.id)).where(VoiceProfile.organization_id == org_id)
    )

    # Get detection jobs count
    detect_count = await db.scalar(
        select(func.count(GenerationJob.id)).where(
            GenerationJob.organization_id == org_id,
            GenerationJob.job_type == "detection"
        )
    )

    # Get total jobs
    total_jobs = await db.scalar(
        select(func.count(GenerationJob.id)).where(GenerationJob.organization_id == org_id)
    )

    # Recent jobs
    recent_jobs_r = await db.execute(
        select(GenerationJob)
        .where(GenerationJob.organization_id == org_id)
        .order_by(GenerationJob.created_at.desc())
        .limit(5)
    )
    recent_jobs_m = recent_jobs_r.scalars().all()
    
    jobs_out = []
    for j in recent_jobs_m:
        jobs_out.append({
            "id": j.id,
            "type": j.job_type.value,
            "voice": j.task_kwargs.get("text", "File Analysis")[:30] + "..." if isinstance(j.task_kwargs, dict) and "text" in j.task_kwargs else "Job",
            "status": j.status.value,
            "created_at": j.created_at.isoformat(),
            "duration": f"{j.processing_time_ms / 1000:.1f}s" if j.processing_time_ms else None
        })

    # Generate dummy usage data for the chart
    now = datetime.now(timezone.utc)
    usage_data = []
    for i in range(30, -1, -1):
        day = now - timedelta(days=i)
        usage_data.append({
            "day": day.strftime("%b %d"),
            "chars": org.tts_chars_used_this_month // 30 if org else 0,
            "detections": detect_count // 30 if detect_count else 0,
        })

    limit = 10000
    if org and org.plan.value == "enterprise":
        limit = 1000000

    return {
        "summary": {
            "voices": voices_count or 0,
            "ttsChars": org.tts_chars_used_this_month if org else 0,
            "detectJobs": detect_count or 0,
            "deepfakesCaught": 0, # Not tracked per org easily without parsing all results
            "ttsLimit": limit
        },
        "usage": usage_data,
        "jobs": jobs_out
    }
