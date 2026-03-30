"""
VoiceCraft Platform — Deepfake Detection Router
Batch file upload + WebSocket real-time stream analysis.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db
from app.models.generation_job import DeepfakeDetectionResult, JobStatus
from app.schemas import DetectionMode, DetectionRequest, DetectionResultResponse
from app.services.storage import get_storage
from app.utils.auth import CurrentUser, decode_token, get_current_user

settings = get_settings()

router = APIRouter(prefix="/api/detect", tags=["Deepfake Detection"])


# ─────────────────────────────────────────────────────────────────
#  Submit detection job (batch file)
# ─────────────────────────────────────────────────────────────────

@router.post("/submit", response_model=DetectionResultResponse, status_code=202)
async def submit_detection(
    audio_file: UploadFile = File(..., description="Audio file to analyze (wav/mp3/ogg/flac, max 100MB)"),
    analysis_mode: DetectionMode = Form(DetectionMode.FULL),
    speaker_diarization: bool = Form(True),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an audio file for deepfake detection.
    Returns result_id immediately; analysis runs asynchronously.
    Poll /detect/results/{result_id} for completion.
    """
    current_user.require_scope("detect:read")

    content = await audio_file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large. Max: {settings.MAX_UPLOAD_SIZE_MB}MB")

    suffix = Path(audio_file.filename or "audio.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}:
        raise HTTPException(415, f"Unsupported format: {suffix}")

    storage = get_storage()
    result_id = str(uuid.uuid4())

    # Upload raw audio to MinIO
    input_key = f"orgs/{current_user.org_id}/detections/{result_id}/input{suffix}"
    storage.upload_bytes(
        settings.MINIO_BUCKET_UPLOADS, input_key, content,
        content_type=audio_file.content_type or "audio/wav",
    )

    # Create DB record
    detection = DeepfakeDetectionResult(
        id=result_id,
        user_id=current_user.user_id,
        organization_id=current_user.org_id,
        status=JobStatus.QUEUED,
        minio_input_key=input_key,
        analysis_mode=analysis_mode.value,
    )
    db.add(detection)
    await db.commit()

    # Dispatch Celery task
    from app.workers.tasks import detect_deepfake_task
    task = detect_deepfake_task.delay(result_id)
    detection.celery_task_id = task.id
    await db.commit()

    return _build_response(detection)


# ─────────────────────────────────────────────────────────────────
#  Poll result
# ─────────────────────────────────────────────────────────────────

@router.get("/results/{result_id}", response_model=DetectionResultResponse)
async def get_detection_result(
    result_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("detect:read")
    detection = await _get_result_or_404(result_id, current_user.org_id, db)
    return _build_response(detection)


@router.get("/results", response_model=list[DetectionResultResponse])
async def list_detection_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.require_scope("detect:read")

    query = select(DeepfakeDetectionResult).where(
        DeepfakeDetectionResult.organization_id == current_user.org_id
    )
    if status_filter:
        try:
            query = query.where(DeepfakeDetectionResult.status == JobStatus(status_filter))
        except ValueError:
            pass

    query = query.order_by(DeepfakeDetectionResult.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)

    results = (await db.execute(query)).scalars().all()
    return [_build_response(r) for r in results]


@router.delete("/results/{result_id}", status_code=204)
async def delete_detection_result(
    result_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    detection = await _get_result_or_404(result_id, current_user.org_id, db)
    if detection.minio_input_key:
        storage = get_storage()
        storage.delete_object(settings.MINIO_BUCKET_UPLOADS, detection.minio_input_key)
    await db.delete(detection)
    await db.commit()


# ─────────────────────────────────────────────────────────────────
#  Fast synchronous detection (for short clips < 30s)
# ─────────────────────────────────────────────────────────────────

@router.post("/quick", response_model=DetectionResultResponse)
async def quick_detect(
    audio_file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronous deepfake detection for files <30s. Returns result immediately.
    Runs in-process (no Celery queue). Best for integration and low-latency use cases.
    """
    current_user.require_scope("detect:read")

    content = await audio_file.read()
    if len(content) > 30 * 1024 * 1024:  # 30MB limit for quick mode
        raise HTTPException(413, "Quick detect max 30MB. Use /detect/submit for larger files.")

    suffix = Path(audio_file.filename or "audio.wav").suffix.lower()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from app.services.deepfake_detector import get_deepfake_detector
        detector = get_deepfake_detector()

        # Estimate duration
        from app.services.audio_processor import AudioProcessor
        processor = AudioProcessor()
        info = processor.analyze(tmp_path)
        if info.duration_seconds > 30:
            raise HTTPException(422, "Audio >30s — use /detect/submit for async processing")

        report = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: detector.detect(tmp_path, mode="full", speaker_diarization=True),
        )

        result_id = str(uuid.uuid4())
        storage = get_storage()
        input_key = f"orgs/{current_user.org_id}/detections/{result_id}/input{suffix}"
        storage.upload_bytes(settings.MINIO_BUCKET_UPLOADS, input_key, content)

        detection = DeepfakeDetectionResult(
            id=result_id,
            user_id=current_user.user_id,
            organization_id=current_user.org_id,
            status=JobStatus.COMPLETED,
            minio_input_key=input_key,
            analysis_mode="full",
            audio_duration_seconds=info.duration_seconds,
            is_deepfake=report.is_deepfake,
            deepfake_probability=report.deepfake_probability,
            authenticity_score=report.authenticity_score,
            confidence=report.confidence,
            synthesis_type=report.synthesis_type,
            detected_tts_system=report.detected_system,
            model_scores=report.model_scores,
            chunk_results=[
                {
                    "start_ms": c.start_ms, "end_ms": c.end_ms,
                    "deepfake_probability": c.deepfake_probability,
                    "is_deepfake": c.is_deepfake, "model_scores": c.model_scores,
                }
                for c in report.chunk_results
            ],
            flagged_segments=report.flagged_segments,
            prosodic_anomaly_score=report.prosodic_anomaly_score,
            spectral_artifact_score=report.spectral_artifact_score,
            glottal_inconsistency_score=report.glottal_inconsistency_score,
            environmental_noise_score=report.environmental_noise_score,
            feature_analysis=report.feature_analysis,
            speaker_count=report.speaker_count,
            per_speaker_results=report.per_speaker_results,
            audio_hash_sha256=report.audio_hash_sha256,
            processing_time_ms=report.processing_time_ms,
        )
        db.add(detection)
        await db.commit()
        await db.refresh(detection)
        return _build_response(detection)

    finally:
        tmp_path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────
#  Real-time WebSocket stream detection
# ─────────────────────────────────────────────────────────────────

@router.websocket("/stream")
async def realtime_detection_stream(websocket: WebSocket, token: str | None = None):
    """
    Real-time audio stream deepfake detection via WebSocket.

    Protocol:
    1. Client sends text: {"sample_rate": 16000} to initialize
    2. Client sends binary: raw PCM chunks (int16, mono, 16kHz)
    3. Server responds after each chunk with detection verdict JSON
    4. Client sends text: "end" to finish session

    Latency: <50ms per chunk on CPU, <20ms on GPU.
    Perfect for call-center integration, live voice authentication.
    """
    await websocket.accept()

    if not token:
        await websocket.send_json({"error": "Missing token"})
        await websocket.close(code=4001)
        return

    try:
        payload = decode_token(token)
        org_id = payload.get("org_id")
    except Exception:
        await websocket.send_json({"error": "Invalid token"})
        await websocket.close(code=4001)
        return

    from app.services.deepfake_detector import get_deepfake_detector, RealtimeStreamAnalyzer
    import time

    detector = get_deepfake_detector()
    analyzer: RealtimeStreamAnalyzer | None = None
    sample_rate = 16000

    await websocket.send_json({
        "event": "connected",
        "message": "Send {sample_rate: 16000} to initialize, then send PCM binary chunks."
    })

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive":
                # Text message = control
                if "text" in message and message["text"]:
                    text = message["text"]
                    if text == "end":
                        await websocket.send_json({"event": "session_ended"})
                        break

                    try:
                        ctrl = json.loads(text)
                        if "sample_rate" in ctrl:
                            sample_rate = int(ctrl["sample_rate"])
                            if sample_rate not in (8000, 16000, 22050, 44100, 48000):
                                sample_rate = 16000
                            analyzer = RealtimeStreamAnalyzer(detector, sample_rate)
                            await websocket.send_json({
                                "event": "initialized",
                                "sample_rate": sample_rate,
                                "message": "Send PCM binary chunks now.",
                            })
                    except json.JSONDecodeError:
                        pass

                # Binary message = audio chunk
                elif "bytes" in message and message["bytes"]:
                    if analyzer is None:
                        analyzer = RealtimeStreamAnalyzer(detector, sample_rate)

                    t0 = time.perf_counter()
                    result = analyzer.feed_chunk(message["bytes"])
                    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                    result["event"] = "chunk_analyzed"
                    result["timestamp_ms"] = int(time.time() * 1000)
                    await websocket.send_json(result)

            elif message["type"] == "websocket.disconnect":
                break

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
#  Detection statistics
# ─────────────────────────────────────────────────────────────────

@router.get("/stats/summary")
async def detection_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated detection statistics for the organization."""
    current_user.require_scope("detect:read")

    total = (await db.execute(
        select(func.count(DeepfakeDetectionResult.id)).where(
            DeepfakeDetectionResult.organization_id == current_user.org_id,
            DeepfakeDetectionResult.status == JobStatus.COMPLETED,
        )
    )).scalar_one()

    deepfakes_found = (await db.execute(
        select(func.count(DeepfakeDetectionResult.id)).where(
            DeepfakeDetectionResult.organization_id == current_user.org_id,
            DeepfakeDetectionResult.is_deepfake == True,
        )
    )).scalar_one()

    return {
        "total_analyzed": total,
        "deepfakes_detected": deepfakes_found,
        "authentic_audio": total - deepfakes_found,
        "deepfake_rate_pct": round(deepfakes_found / total * 100, 2) if total > 0 else 0.0,
        "organization_id": current_user.org_id,
    }


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

async def _get_result_or_404(result_id: str, org_id: str, db: AsyncSession) -> DeepfakeDetectionResult:
    r = (await db.execute(
        select(DeepfakeDetectionResult).where(
            DeepfakeDetectionResult.id == result_id,
            DeepfakeDetectionResult.organization_id == org_id,
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Detection result not found")
    return r


def _build_response(r: DeepfakeDetectionResult) -> DetectionResultResponse:
    from app.services.deepfake_detector import DetectionReport
    verdict = None
    if r.deepfake_probability is not None:
        p = r.deepfake_probability
        if p >= 0.85:
            verdict = "HIGH CONFIDENCE DEEPFAKE"
        elif p >= 0.65:
            verdict = "LIKELY DEEPFAKE"
        elif p >= 0.45:
            verdict = "UNCERTAIN — MANUAL REVIEW RECOMMENDED"
        elif p >= 0.25:
            verdict = "LIKELY AUTHENTIC"
        else:
            verdict = "HIGH CONFIDENCE AUTHENTIC"

    return DetectionResultResponse(
        result_id=r.id,
        status=r.status.value,
        is_deepfake=r.is_deepfake,
        verdict=verdict,
        deepfake_probability=r.deepfake_probability,
        authenticity_score=r.authenticity_score,
        confidence=r.confidence,
        synthesis_type=r.synthesis_type,
        detected_system=r.detected_tts_system,
        model_scores=r.model_scores,
        prosodic_anomaly_score=r.prosodic_anomaly_score,
        spectral_artifact_score=r.spectral_artifact_score,
        glottal_inconsistency_score=r.glottal_inconsistency_score,
        environmental_noise_score=r.environmental_noise_score,
        chunk_results=r.chunk_results,
        flagged_segments=r.flagged_segments,
        speaker_count=r.speaker_count,
        per_speaker_results=r.per_speaker_results,
        audio_hash_sha256=r.audio_hash_sha256,
        audio_duration_seconds=r.audio_duration_seconds,
        processing_time_ms=r.processing_time_ms,
        error_message=r.error_message,
        created_at=r.created_at,
    )
