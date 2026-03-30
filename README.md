# VoiceCraft Platform

**Enterprise Voice AI: Clone · Generate · Detect**  
Beyond ElevenLabs — fully open-source, self-hosted, no per-character fees.

---

## Features

| Capability | Details |
|---|---|
| 🎙️ Voice Cloning | Zero-shot from **6 seconds** of audio. XTTS-v2 (Apache 2.0) |
| 🔧 Fine-Tuning | Train on **1–5 min** for maximum similarity |
| 🗣️ Text-to-Speech | 17 languages, 14 emotions, SSML, pitch/speed control |
| 🔍 Deepfake Detection | 5-model ensemble: AASIST + RawNet2 + Prosodic + Spectral + Glottal |
| ⚡ Real-Time Streaming | WebSocket TTS (<500ms first audio) + Live detection (<50ms/chunk) |
| 🗓️ Speaker Diarization | Per-speaker deepfake scoring |
| ⚖️ Legal Provenance | SHA256 hash + chain-of-custody audit log for evidence |
| 🏢 Enterprise | Multi-tenant, JWT + API key auth, plan limits, Prometheus metrics |

---

## Quick Start

### 1. Clone & Configure
```bash
git clone https://github.com/your-org/voicecraft-platform
cd voicecraft-platform
cp .env.example .env
# Edit .env — change JWT_SECRET, SECRET_KEY, MINIO_SECRET_KEY
```

### 2. Download Models (one-time)
```bash
pip install TTS openai-whisper transformers speechbrain
python scripts/download_models.py
# Downloads ~3GB: XTTS-v2, Whisper, AASIST, SpeechBrain
```

### 3. Start Platform
```bash
docker-compose up --build
```

Platform will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001

### 4. GPU Acceleration (Recommended)
Edit `docker-compose.yml` — uncomment `deploy.resources.reservations.devices` sections.
Set `XTTS_DEVICE=cuda` and `WHISPER_DEVICE=cuda` in `.env`.
Expect 10–20x speedup on TTS and 5x on detection.

---

## API Usage Examples

### Register & Get Token
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@co.com","username":"you","password":"SecurePass1!"}'

curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@co.com","password":"SecurePass1!"}'
# → {"access_token": "eyJ...", "refresh_token": "..."}
```

### Clone a Voice
```bash
# 1. Create profile
curl -X POST http://localhost:8000/api/voices \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"My Voice"}'

# 2. Upload 10s+ audio sample
curl -X POST http://localhost:8000/api/voices/$PROFILE_ID/samples \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio_file=@my_voice.mp3"

# 3. Start cloning
curl -X POST http://localhost:8000/api/voices/$PROFILE_ID/clone \
  -H "Authorization: Bearer $TOKEN"
```

### Generate Speech
```bash
# Submit job
curl -X POST http://localhost:8000/api/tts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "voice_profile_id": "$PROFILE_ID",
    "text": "Hello! This is my cloned voice speaking.",
    "language": "en",
    "emotion": "happy",
    "speed": 1.05,
    "output_format": "mp3"
  }'

# Poll until complete, then download
curl http://localhost:8000/api/tts/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

### Detect Deepfakes
```bash
# Quick (synchronous, <30s audio)
curl -X POST http://localhost:8000/api/detect/quick \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio_file=@suspicious_audio.mp3"

# Batch (async, any length)
curl -X POST http://localhost:8000/api/detect/submit \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio_file=@long_audio.wav" \
  -F "analysis_mode=full" \
  -F "speaker_diarization=true"
```

### WebSocket Streaming TTS
```javascript
const ws = new WebSocket(`ws://localhost:8000/api/tts/stream?token=${token}`);
ws.onopen = () => ws.send(JSON.stringify({
  voice_profile_id: profileId,
  text: "Stream this text as audio in real time.",
  language: "en", emotion: "neutral"
}));
ws.onmessage = (msg) => {
  if (msg.data instanceof Blob) {
    // Play audio chunk
    const url = URL.createObjectURL(msg.data);
    new Audio(url).play();
  } else {
    console.log(JSON.parse(msg.data));
  }
};
```

### WebSocket Real-Time Detection
```javascript
const ws = new WebSocket(`ws://localhost:8000/api/detect/stream?token=${token}`);
ws.onopen = () => ws.send(JSON.stringify({ sample_rate: 16000 }));
// Then send raw PCM int16 binary chunks from microphone
ws.onmessage = (msg) => {
  const data = JSON.parse(msg.data);
  if (data.alert) console.warn("⚠️ DEEPFAKE ALERT!", data);
};
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Nginx (80/443)                      │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│           FastAPI (uvicorn, 2 workers)                   │
│  /api/auth  /api/voices  /api/tts  /api/detect           │
│  WebSocket: /api/tts/stream  /api/detect/stream          │
└──┬──────────────────────────────────────────────────┬───┘
   │                                                  │
┌──▼──────────┐  ┌──────────────────────────────┐  ┌─▼────┐
│  PostgreSQL  │  │   Redis (broker + cache)     │  │MinIO │
│  (sessions, │  │                              │  │(obj  │
│  profiles,  │  └──────────────────────────────┘  │store)│
│  jobs, logs)│          │                          └──────┘
└─────────────┘   ┌──────▼──────────────────────┐
                  │      Celery Workers           │
                  │  clone | tts | detect | beat  │
                  │                               │
                  │  ┌─────────┐  ┌───────────┐  │
                  │  │XTTS-v2  │  │ Detection │  │
                  │  │(cloning)│  │ Ensemble  │  │
                  │  └─────────┘  └───────────┘  │
                  └───────────────────────────────┘
```

---

## Detection Model Architecture

```
Audio Input
    │
    ├─► RawNet2 (40%)    ─── Raw waveform CNN + GRU
    ├─► AASIST (40%)     ─── Graph attention network  
    ├─► Prosodic (15%)   ─── F0 trajectory + pause analysis
    ├─► Spectral (10%)   ─── Mel-spectrogram vocoder artifacts
    └─► Glottal (10%)    ─── Cepstral + shimmer analysis
             │
             └─► Weighted Ensemble → Verdict + Confidence
```

---

## Plans & Pricing

| Plan | Voices | TTS Chars/Month | Fine-Tuning | Price |
|------|--------|-----------------|-------------|-------|
| Free | 2 | 10,000 | ❌ | $0 |
| Starter | 10 | 100,000 | ❌ | $29/mo |
| Pro | 50 | 1,000,000 | ✅ | $99/mo |
| Enterprise | Unlimited | Unlimited | ✅ | Custom |

---

## Running Tests

```bash
pip install pytest pytest-asyncio httpx aiosqlite soundfile
pytest tests/ -v --tb=short
```

---

## Stack

All components are **free, open-source, self-hostable**:

- **FastAPI** — Python web framework (MIT)
- **XTTS-v2** — Coqui voice cloning model (Apache 2.0)
- **Whisper** — OpenAI speech recognition (MIT)
- **AASIST** — Graph attention anti-spoofing (research, free)
- **SpeechBrain** — Speaker verification (Apache 2.0)
- **PostgreSQL** — Database (PostgreSQL License)
- **Redis** — Cache + message broker (BSD)
- **MinIO** — S3-compatible object storage (AGPLv3)
- **Celery** — Distributed task queue (BSD)
- **Nginx** — Reverse proxy (BSD)

*Built by Anshul Rathod · Project #42 of 75 — VoiceGuard / VoiceCraft*
