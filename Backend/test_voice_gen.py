import requests
import time
import sys

BASE_URL = "http://localhost:8000"

print("Starting E2E ML Generation Test...")

print("\n1. Logging into system...")
# Register/Login
auth_data = {
    "email": "autotest@voicecraft.dev",
    "password": "TestPass123!",
    "username": "autotester"
}
try:
    reg_res = requests.post(f"{BASE_URL}/api/auth/register", json=auth_data)
except Exception:
    pass # Might already exist

login_res = requests.post(
    f"{BASE_URL}/api/auth/login",
    json={"email": "autotest@voicecraft.dev", "password": "TestPass123!"}
)
if login_res.status_code != 200:
    print(f"Failed to login: {login_res.text}")
    sys.exit(1)

token = login_res.json()["access_token"]
print("✅ Login successful. Token acquired.")

headers = {"Authorization": f"Bearer {token}"}

print("\n2. Fetching available system voices...")
voices_res = requests.get(f"{BASE_URL}/api/voices", headers=headers)
voices = voices_res.json()
if not voices:
    print("❌ No voices returned from DB!")
    sys.exit(1)

# Pick first suitable voice
target_voice_id = voices[0]["id"]
print(f"✅ Picked voice ID: {target_voice_id}")

print("\n3. Dispatching TTS generation task to Celery Docker Worker...")
req_data = {
    "text": "Hello, this is a live test of the Celery Docker worker pipeline running successfully.",
    "voice_id": target_voice_id
}
gen_res = requests.post(f"{BASE_URL}/api/tts/generate", json=req_data, headers=headers)
if gen_res.status_code != 202:
    print(f"❌ Failed to queue job: {gen_res.text}")
    sys.exit(1)

job_id = gen_res.json()["job_id"]
print(f"✅ Job {job_id} successfully queued in Redis.")

print("\n4. Polling Worker Status...")
for i in range(20):
    time.sleep(2)
    status_res = requests.get(f"{BASE_URL}/api/tts/jobs/{job_id}", headers=headers)
    status = status_res.json()
    print(f"   Status check {i+1}: {status['status']}")
    
    if status['status'] == "completed":
        print(f"\n🎉 SUCCESS! Audio generated: {status['audio_url']}")
        sys.exit(0)
    elif status['status'] == "failed":
        print(f"\n❌ WORKER CRASHED: {status.get('error')}")
        sys.exit(1)

print("\n⚠️ TIMEOUT: Worker took too long or is not picking up the queue.")
sys.exit(1)
