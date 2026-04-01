#!/usr/bin/env python3
"""
Quick API test to verify backend is working
"""
import httpx
import json
from pathlib import Path

BASE_URL = "http://localhost:8000"

def test_health():
    print("\n✓ Testing /health endpoint...")
    resp = httpx.get(f"{BASE_URL}/health")
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {json.dumps(resp.json(), indent=2)}")
    return resp.status_code == 200

def test_root():
    print("\n✓ Testing / endpoint...")
    resp = httpx.get(f"{BASE_URL}/")
    print(f"  Status: {resp.status_code}")
    data = resp.json()
    print(f"  Name: {data.get('name')}")
    print(f"  Version: {data.get('version')}")
    print(f"  Features: {len(data.get('features', []))} listed")
    return resp.status_code == 200

def test_docs():
    print("\n✓ Testing /docs (Swagger UI)...")
    resp = httpx.get(f"{BASE_URL}/docs")
    print(f"  Status: {resp.status_code}")
    return resp.status_code == 200

def test_openapi():
    print("\n✓ Testing /openapi.json (OpenAPI schema)...")
    resp = httpx.get(f"{BASE_URL}/openapi.json")
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        schema = resp.json()
        print(f"  Paths: {len(schema.get('paths', {}))} endpoints")
        print(f"  Components: {len(schema.get('components', {}).get('schemas', {}))} schemas")
    return resp.status_code == 200

def test_register():
    print("\n✓ Testing /api/auth/register endpoint...")
    payload = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "TestPassword123!",
        "full_name": "Test User",
        "organization_name": "Test Org"
    }
    resp = httpx.post(f"{BASE_URL}/api/auth/register", json=payload)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 201:
        print(f"  User created: {resp.json().get('username')}")
    else:
        print(f"  Response: {resp.json()}")
    return resp.status_code == 201

if __name__ == "__main__":
    print("=" * 60)
    print("VoiceCraft Platform — Backend API Test")
    print("=" * 60)
    
    tests = [
        test_root,
        test_health,
        test_openapi,
        test_docs,
        test_register,
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed")
    print("=" * 60)
