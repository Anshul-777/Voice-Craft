import asyncio
import os
import sys
from sqlalchemy import select, text
from app.models.database import engine
from app.models.user import VoiceProfile

async def check():
    try:
        async with engine.begin() as conn:
            # Check table existence first
            try:
                res = await conn.execute(text("SELECT id, name, is_system FROM voice_profiles"))
                rows = res.fetchall()
                print(f"--- VOICES IN DATABASE ({len(rows)}) ---")
                for r in rows:
                    print(f"ID: {r[0]} | Name: {r[1]} | System: {r[2]}")
            except Exception as e:
                print(f"Error querying voice_profiles: {e}")
                
        if not rows:
            print("\n🚨 NO VOICES FOUND. System may need seeding.")
            
    except Exception as e:
        print(f"Database connection error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
