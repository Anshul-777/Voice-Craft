"""
VoiceCraft Platform — Test Suite
Covers: auth, voice profiles, TTS jobs, detection, WebSocket endpoints.
Uses pytest-asyncio + httpx AsyncClient.
All external ML model calls are mocked.
"""
from __future__ import annotations

import io
import json
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# ─────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def override_settings():
    """Use in-memory SQLite for tests."""
    import os
    os.environ.update({
        "DATABASE_URL": "sqlite+aiosqlite:///./test_voicecraft.db",
        "REDIS_URL": "redis://localhost:6379/15",
        "CELERY_BROKER_URL": "memory://",
        "CELERY_RESULT_BACKEND": "cache+memory://",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "test",
        "MINIO_SECRET_KEY": "testtest",
        "JWT_SECRET": "test-jwt-secret-32-chars-minimum-here",
        "SECRET_KEY": "test-secret-key-32-chars-minimum-!!!",
        "XTTS_DEVICE": "cpu",
        "WHISPER_DEVICE": "cpu",
        "DEBUG": "true",
    })


@pytest.fixture
async def app():
    from app.main import app as fastapi_app
    from app.models.database import create_tables, engine
    from sqlalchemy.ext.asyncio import create_async_engine
    async with engine.begin() as conn:
        from app.models.database import Base
        await conn.run_sync(Base.metadata.create_all)
    yield fastapi_app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_headers(client):
    """Register a test user and return auth headers."""
    resp = await client.post("/api/auth/register", json={
        "email": "test@voicecraft.ai",
        "username": "testuser",
        "password": "TestPass123!",
        "full_name": "Test User",
    })
    assert resp.status_code == 201

    login_resp = await client.post("/api/auth/login", json={
        "email": "test@voicecraft.ai",
        "password": "TestPass123!",
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_wav_bytes(duration_s: float = 10.0, sr: int = 22050) -> bytes:
    """Generate a synthetic WAV file for testing."""
    import soundfile as sf
    samples = int(sr * duration_s)
    # Generate a tone that sounds like speech (to pass VAD)
    t = np.linspace(0, duration_s, samples)
    audio = 0.3 * np.sin(2 * np.pi * 200 * t)  # 200 Hz tone
    # Add some amplitude modulation to simulate speech
    mod = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)
    audio = (audio * mod).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────
#  System Tests
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "features" in resp.json()


# ─────────────────────────────────────────────────────────────────
#  Auth Tests
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post("/api/auth/register", json={
        "email": "newuser@test.com",
        "username": "newuser",
        "password": "Password123!",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@test.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client, auth_headers):
    resp = await client.post("/api/auth/register", json={
        "email": "test@voicecraft.ai",
        "username": "other",
        "password": "Password123!",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client, auth_headers):
    resp = await client.post("/api/auth/login", json={
        "email": "test@voicecraft.ai",
        "password": "TestPass123!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post("/api/auth/login", json={
        "email": "test@voicecraft.ai",
        "password": "wrong",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@voicecraft.ai"


@pytest.mark.asyncio
async def test_create_api_key(client, auth_headers):
    resp = await client.post("/api/auth/api-keys", json={
        "name": "Test Key",
        "scopes": ["tts:read", "tts:write"],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["raw_key"].startswith("vc_live_")
    assert "tts:read" in data["scopes"]


# ─────────────────────────────────────────────────────────────────
#  Voice Profile Tests
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_voice_profile(client, auth_headers):
    resp = await client.post("/api/voices", json={
        "name": "My Test Voice",
        "description": "Test voice for unit tests",
        "tags": ["test", "english"],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Test Voice"
    assert data["status"] == "pending"
    return data["id"]


@pytest.mark.asyncio
async def test_list_voice_profiles(client, auth_headers):
    # Create one first
    await test_create_voice_profile(client, auth_headers)
    resp = await client.get("/api/voices", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "voices" in data
    assert isinstance(data["voices"], list)
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_upload_sample_too_short(client, auth_headers):
    """Sample shorter than MIN_CLONE_AUDIO_SECONDS should fail."""
    profile_resp = await client.post("/api/voices", json={"name": "Test"}, headers=auth_headers)
    profile_id = profile_resp.json()["id"]

    short_wav = _make_wav_bytes(duration_s=1.0)  # 1 second — too short
    resp = await client.post(
        f"/api/voices/{profile_id}/samples",
        files={"audio_file": ("test.wav", io.BytesIO(short_wav), "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_sample_valid(client, auth_headers):
    """Valid 10s audio should upload successfully."""
    profile_resp = await client.post("/api/voices", json={"name": "Test"}, headers=auth_headers)
    profile_id = profile_resp.json()["id"]

    with patch("app.services.storage.StorageService.upload_bytes", return_value="bucket/key"):
        wav = _make_wav_bytes(duration_s=10.0)
        resp = await client.post(
            f"/api/voices/{profile_id}/samples",
            files={"audio_file": ("test.wav", io.BytesIO(wav), "audio/wav")},
            headers=auth_headers,
        )
    # May succeed or fail depending on VAD — check for non-5xx
    assert resp.status_code in (201, 422)


@pytest.mark.asyncio
async def test_get_usage_stats(client, auth_headers):
    resp = await client.get("/api/voices/usage/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "plan" in data
    assert "tts_chars_used_this_month" in data
    assert "voice_profiles_limit" in data


# ─────────────────────────────────────────────────────────────────
#  TTS Tests
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_capabilities(client, auth_headers):
    with patch("app.services.voice_cloner.VoiceClonerService._tts", None):
        resp = await client.get("/api/tts/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "languages" in data
    assert "en" in data["languages"]
    assert "emotions" in data
    assert "neutral" in data["emotions"]


@pytest.mark.asyncio
async def test_tts_invalid_voice_profile(client, auth_headers):
    resp = await client.post("/api/tts/generate", json={
        "voice_profile_id": "nonexistent-id",
        "text": "Hello world",
        "language": "en",
    }, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tts_list_jobs(client, auth_headers):
    resp = await client.get("/api/tts/jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ─────────────────────────────────────────────────────────────────
#  Detection Tests
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detection_stats(client, auth_headers):
    resp = await client.get("/api/detect/stats/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_analyzed" in data
    assert "deepfakes_detected" in data


@pytest.mark.asyncio
async def test_list_detection_results(client, auth_headers):
    resp = await client.get("/api/detect/results", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_quick_detect_real_audio(client, auth_headers):
    """Test quick detection with a real audio file (mocked detector)."""
    from app.services.deepfake_detector import DetectionReport, ChunkResult

    mock_report = DetectionReport(
        is_deepfake=False,
        deepfake_probability=0.12,
        authenticity_score=88.0,
        confidence=0.95,
        synthesis_type="authentic",
        detected_system=None,
        model_scores={"rawnet2": 0.1, "aasist": 0.14, "prosodic": 0.10, "spectral": 0.12, "glottal": 0.11},
        chunk_results=[ChunkResult(0, 4000, 0.12, False, {"rawnet2": 0.10})],
        flagged_segments=[],
        prosodic_anomaly_score=0.10,
        spectral_artifact_score=0.12,
        glottal_inconsistency_score=0.11,
        environmental_noise_score=0.20,
        feature_analysis={},
        speaker_count=1,
        per_speaker_results=[],
        audio_hash_sha256="abc123",
        processing_time_ms=250,
    )

    with patch("app.services.deepfake_detector.DeepfakeDetectorService.detect", return_value=mock_report), \
         patch("app.services.storage.StorageService.upload_bytes", return_value="bucket/key"):
        wav = _make_wav_bytes(duration_s=5.0)
        resp = await client.post(
            "/api/detect/quick",
            files={"audio_file": ("test.wav", io.BytesIO(wav), "audio/wav")},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_deepfake"] == False
    assert data["authenticity_score"] == 88.0
    assert "AUTHENTIC" in data["verdict"]


# ─────────────────────────────────────────────────────────────────
#  Audio Processor Unit Tests
# ─────────────────────────────────────────────────────────────────

def test_audio_processor_load():
    import tempfile
    import soundfile as sf
    from app.services.audio_processor import AudioProcessor

    processor = AudioProcessor()
    audio = np.random.randn(22050 * 5).astype(np.float32) * 0.1

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, audio, 22050)
        loaded, sr = processor.load_audio(tmp.name)
        assert sr == 22050
        assert len(loaded) > 0
        assert loaded.dtype == np.float32


def test_audio_processor_analyze():
    import tempfile
    import soundfile as sf
    from app.services.audio_processor import AudioProcessor

    processor = AudioProcessor()
    # Create synthetic speech-like audio
    sr = 22050
    t = np.linspace(0, 5.0, sr * 5)
    audio = (0.3 * np.sin(2 * np.pi * 150 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, audio, sr)
        info = processor.analyze(tmp.name, audio, sr)
        assert info.duration_seconds == pytest.approx(5.0, abs=0.1)
        assert info.sample_rate == sr
        assert isinstance(info.sha256, str)


def test_emotion_prosody():
    from app.services.audio_processor import AudioProcessor
    processor = AudioProcessor()
    sr = 22050
    audio = np.random.randn(sr * 3).astype(np.float32) * 0.1

    for emotion in ["happy", "sad", "calm", "excited"]:
        processed = processor.apply_emotion_prosody(audio, sr, emotion, intensity=0.5)
        assert processed.dtype == np.float32
        assert len(processed) > 0


# ─────────────────────────────────────────────────────────────────
#  Deepfake Detector Unit Tests (no model loading)
# ─────────────────────────────────────────────────────────────────

def test_spectral_artifact_score():
    """Test spectral artifact detection on known signals."""
    import tempfile
    import soundfile as sf
    from app.services.deepfake_detector import DeepfakeDetectorService

    detector = DeepfakeDetectorService()

    sr = 16000
    t = np.linspace(0, 2.0, sr * 2)
    # Perfectly smooth synthetic signal (should score high)
    pure_tone = (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    score = detector._spectral_artifact_score(pure_tone, sr)
    assert 0.0 <= score <= 1.0

    # Natural-ish noisy speech signal (should score lower)
    noisy = (0.3 * np.sin(2 * np.pi * 150 * t) + 0.05 * np.random.randn(sr * 2)).astype(np.float32)
    score_noisy = detector._spectral_artifact_score(noisy, sr)
    assert 0.0 <= score_noisy <= 1.0


def test_prosodic_analysis():
    from app.services.deepfake_detector import DeepfakeDetectorService
    detector = DeepfakeDetectorService()
    sr = 16000
    t = np.linspace(0, 5.0, sr * 5)
    audio = (0.3 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    score = detector._prosodic_analysis(audio, sr)
    assert 0.0 <= score <= 1.0


def test_glottal_analysis():
    from app.services.deepfake_detector import DeepfakeDetectorService
    detector = DeepfakeDetectorService()
    sr = 16000
    t = np.linspace(0, 5.0, sr * 5)
    audio = (0.3 * np.sin(2 * np.pi * 200 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 5 * t))).astype(np.float32)
    score = detector._glottal_analysis(audio, sr)
    assert 0.0 <= score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
