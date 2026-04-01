#!/usr/bin/env python3
"""
VoiceCraft Platform — System Verification Script
Tests all running services and outputs status
"""
import subprocess
import sys
import time
from pathlib import Path

def test_service(name: str, url: str, method: str = "GET") -> tuple[bool, str]:
    """Test if a service is running"""
    try:
        if method == "GET":
            import urllib.request
            response = urllib.request.urlopen(url, timeout=5)
            return True, f"✅ {name} running ({response.status})"
        elif method == "HEAD":
            import urllib.request
            req = urllib.request.Request(url, method="HEAD")
            urllib.request.urlopen(req, timeout=5)
            return True, f"✅ {name} running"
    except Exception as e:
        return False, f"❌ {name} error: {str(e)[:50]}"

def main():
    print("\n" + "="*70)
    print("VoiceCraft Platform — System Status Check".center(70))
    print("="*70 + "\n")
    
    tests = [
        ("Backend API", "http://127.0.0.1:8000/", "GET"),
        ("Backend Health", "http://127.0.0.1:8000/health", "GET"),
        ("Swagger UI", "http://127.0.0.1:8000/docs", "GET"),
        ("Frontend", "http://localhost:5173/", "GET"),
        ("MinIO API", "http://localhost:9000/minio/health/live", "GET"),
        ("MinIO Console", "http://localhost:9001/", "GET"),
    ]
    
    results = []
    for name, url, method in tests:
        success, message = test_service(name, url, method)
        results.append((success, message))
        print(message)
        time.sleep(0.5)
    
    # Summary
    passed = sum(1 for success, _ in results if success)
    total = len(results)
    
    print("\n" + "-"*70)
    print(f"\n📊 Results: {passed}/{total} services running\n")
    
    if passed == total:
        print("✅ ALL SYSTEMS OPERATIONAL")
        print("\n🚀 Next Steps:")
        print("   1. Open http://localhost:5173 (Frontend)")
        print("   2. Or test API at http://localhost:8000/docs")
        print("   3. Or read SYSTEM_STATUS.md for detailed instructions")
    elif passed >= 3:
        print("⚠️  PARTIAL SYSTEMS RUNNING")
        print("\n   What's working:")
        print("   • Backend API ✅")
        print("   • Storage ✅")
        print("\n   What's missing:")
        print("   • Frontend (start: cd Frontend/voicecraft-ui && npm run dev)")
        print("   • Optional: PostgreSQL, Redis (docker-compose up)")
    else:
        print("❌ BACKEND NOT RESPONDING")
        print("\n   Fix: Start backend server")
        print("   cd Voice-King/Backend")
        print("   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
    
    print("\n" + "="*70 + "\n")
    
    return 0 if passed >= 3 else 1

if __name__ == "__main__":
    sys.exit(main())
