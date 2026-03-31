import asyncio
from sqlalchemy import text
from app.models.database import engine

async def debug():
    async with engine.connect() as conn:
        print("--- USERS ---")
        res = await conn.execute(text("SELECT id, email, organization_id FROM users"))
        users = res.fetchall()
        for u in users:
            print(u)
        
        print("\n--- ORGANIZATIONS ---")
        res = await conn.execute(text("SELECT id, name FROM organizations"))
        orgs = res.fetchall()
        for o in orgs:
            print(o)

        print("\n--- VOICES ---")
        res = await conn.execute(text("SELECT id, name, status, is_system FROM voice_profiles"))
        voices = res.fetchall()
        for v in voices:
            print(v)

if __name__ == "__main__":
    asyncio.run(debug())
