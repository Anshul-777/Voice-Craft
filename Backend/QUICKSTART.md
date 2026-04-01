# VoiceCraft Platform — Quick Start Guide

## Current Status
- ✅ **Backend API running** at `http://127.0.0.1:8000`
- ✅ **MinIO storage** initialized
- ⏳ **PostgreSQL/Redis** (optional in dev mode)
- ⏳ **Frontend UI** (needs to be built)

---

## Option 1: Minimal Setup (Current)

This is what's running right now. You can:
- Test API endpoints
- View Swagger docs
- Register users
- Upload voice samples
- Queue clone/TTS jobs

**To use it:**
```bash
# Backend is already running. Test it:
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/docs   # Open in browser for interactive UI

# Register a test user:
python -c "
import json
import urllib.request

data = json.dumps({
    'email': 'test@example.com',
    'username': 'testuser',
    'password': 'TestPass123!',
    'full_name': 'Test User'
}).encode()

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/auth/register',
    data=data,
    headers={'Content-Type': 'application/json'}
)
try:
    with urllib.request.urlopen(req) as resp:
        print(json.loads(resp.read()))
except Exception as e:
    print(f'Error: {e}')
"
```

**Limitations:**
- Jobs queue but don't process (no Celery workers)
- No database persistence (in-memory only)
- Can't generate audio yet

---

## Option 2: Full Stack (Recommended)

### Prerequisites
- Docker & Docker Compose installed
- 8GB RAM available
- ~5GB disk space

### Start Everything

```bash
cd Voice-King/Backend

# Option A: Fresh start (clean volumes)
docker-compose down -v
docker-compose up -d

# Option B: Graceful restart
docker-compose restart

# Check status
docker-compose ps
```

### Services That Start
```
✅ voicecraft_api         (FastAPI on :8000)
✅ voicecraft_postgres    (PostgreSQL on :5432)
✅ voicecraft_redis       (Redis on :6379)
✅ voicecraft_minio       (MinIO API on :9000, UI on :9001)
✅ voicecraft_celery_clone    (Voice cloning worker)
✅ voicecraft_celery_tts      (TTS synthesis worker)
✅ voicecraft_celery_detect   (Deepfake detection worker)
✅ voicecraft_celery_beat     (Scheduled tasks)
```

### Verify All Services Are Healthy
```bash
# Check API
curl http://localhost:8000/health

# Check MinIO
open http://localhost:9001  # Login: voicecraft_admin / voicecraft_secret_CHANGE_ME

# Check Database
docker-compose exec postgres psql -U voicecraft -d voicecraft -c "SELECT version();"

# Check Redis
docker-compose exec redis redis-cli ping
```

### Now You Can
✅ Clone voices (XTTS-v2)
✅ Fine-tune on audio
✅ Generate speech (17 languages)
✅ Detect deepfakes (real-time)
✅ Stream TTS (WebSocket)
✅ Persistent database storage
✅ Queue async jobs

---

## Option 3: Hybrid (API + Manual Tasks)

Use the running backend + manually run workers:

```bash
# Terminal 1: Backend (already running)
cd Voice-King/Backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Redis (Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 3: PostgreSQL (Docker)
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_DB=voicecraft \
  -e POSTGRES_USER=voicecraft \
  -e POSTGRES_PASSWORD=voicecraft_pass \
  postgres:16-alpine

# Terminal 4: Celery clone worker
cd Voice-King/Backend
celery -A app.workers.celery_app worker --queues=clone,fine_tune --concurrency=1

# Terminal 5: Celery TTS worker
cd Voice-King/Backend
celery -A app.workers.celery_app worker --queues=tts --concurrency=2

# Terminal 6: Celery detection worker
cd Voice-King/Backend
celery -A app.workers.celery_app worker --queues=detect --concurrency=2
```

---

## Testing the API

### 1. Register User
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "username": "demouser",
    "password": "Demo123!@#",
    "full_name": "Demo User"
  }'
```
Response: User object with ID

### 2. Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "Demo123!@#"
  }'
```
Response: `{ "access_token": "...", "refresh_token": "...", "expires_in": 3600 }`

Save the `access_token` as `TOKEN` env var:
```bash
export TOKEN="eyJ0eXAiOiJKV1QiLCJhbGc..."
```

### 3. Create Voice Profile
```bash
curl -X POST http://localhost:8000/api/voices \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Demo Voice",
    "description": "A clear, professional voice",
    "is_public": false,
    "tags": ["demo", "male"]
  }'
```
Response: Profile ID (save as `PROFILE_ID`)

### 4. Upload Voice Sample
```bash
# First, get a WAV file or record one
# Example: Create a 6-second silence WAV (will be rejected, but shows the flow)

curl -X POST http://localhost:8000/api/voices/$PROFILE_ID/samples \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio_file=@path/to/your/voice_sample.wav"
```

### 5. Start Voice Cloning
Once you have ≥6s of audio uploaded:
```bash
curl -X POST http://localhost:8000/api/voices/$PROFILE_ID/clone \
  -H "Authorization: Bearer $TOKEN"
```
Response: Clone job ID (save as `JOB_ID`)

### 6. Check Clone Status
```bash
curl http://localhost:8000/api/voices/clone-jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

### 7. Generate Speech (TTS)
Once voice is ready (`status: ready`):
```bash
curl -X POST http://localhost:8000/api/tts/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "voice_profile_id": "'$PROFILE_ID'",
    "text": "Hello, this is a test of the voice synthesis system.",
    "language": "en",
    "emotion": "neutral",
    "speed": 1.0,
    "output_format": "mp3"
  }'
```

### 8. Detect Deepfake
```bash
curl -X POST http://localhost:8000/api/detect \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio_file=@path/to/audio.wav"
```
Response: `{ "is_deepfake": true/false, "confidence": 0.95, "models": {...} }`

---

## Frontend Setup (TODO)

### Scaffold React App
```bash
cd Voice-King/Frontend/voicecraft-ui
npm create vite@latest . -- --template react
npm install
npm run dev
```

Then open `http://localhost:5173` and build:
- Login page
- Voice profile manager
- Record voice / upload audio
- Clone button (poll status)
- Voice library
- TTS preview
- Deepfake detector
- Settings

---

## Common Issues & Fixes

### Issue: "Database connection refused"
**Fix:** This is OK in dev mode. Either:
- Ignore (keep using in-memory)
- Start PostgreSQL: `docker run -d -p 5432:5432 postgres:16-alpine ...`

### Issue: "Celery worker not responding"
**Fix:** Start a worker:
```bash
cd Voice-King/Backend
celery -A app.workers.celery_app worker --loglevel=debug
```

### Issue: "MinIO bucket not found"
**Fix:** Already created on startup. Check MinIO console at http://localhost:9001

### Issue: "CORS error from frontend"
**Fix:** Already configured in `.env`:
```
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```
Add your frontend URL if different.

### Issue: "Model download stuck"
**Fix:** XTTS-v2 is ~2GB. First time takes 5-10 min. Check logs:
```bash
docker-compose logs -f voicecraft_api
```

---

## Environment Variables

Key settings in `.env`:

```bash
# Device: Use "cpu" unless you have NVIDIA GPU
XTTS_DEVICE=cpu        # or "cuda"
WHISPER_DEVICE=cpu     # or "cuda"

# Storage (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=voicecraft_admin
MINIO_SECRET_KEY=voicecraft_secret_CHANGE_ME

# Database
DATABASE_URL=postgresql+asyncpg://voicecraft:voicecraft_pass@localhost:5432/voicecraft

# Security
SECRET_KEY=<change-this-in-production>
JWT_SECRET=<change-this-in-production>

# Rate limits
RATE_LIMIT_CLONE_PER_DAY=10
RATE_LIMIT_TTS_PER_DAY=500
RATE_LIMIT_DETECT_PER_DAY=1000
```

---

## Performance Tips

### For CPU-Only Systems (No GPU)
- Use smaller models: `WHISPER_MODEL_SIZE=tiny`
- Reduce worker concurrency: `--concurrency=1`
- Expect 2-5x slower voice generation

### For GPU Systems (NVIDIA A100/H100)
- Enable DeepSpeed: `XTTS_USE_DEEPSPEED=true`
- Increase worker concurrency: `--concurrency=4`
- Use batch processing for TTS

### Memory Requirements
- **Minimal:** 4GB (API only, no models)
- **Recommended:** 16GB (API + one worker)
- **Production:** 32GB+ (multiple workers + models cache)

---

## Next Steps

1. **Verify current setup:** `curl http://127.0.0.1:8000/docs`
2. **Start full stack:** `docker-compose up`
3. **Build frontend:** React UI for voice management
4. **Test end-to-end:** Register → Upload voice → Clone → TTS
5. **Deploy:** Use Docker Compose in production or Kubernetes

---

**Questions?** Check the Swagger UI at `/docs` for detailed API docs.
