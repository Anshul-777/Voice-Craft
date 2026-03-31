import asyncio
from sqlalchemy import text
from app.models.database import engine

async def check():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT id, name FROM voice_profiles"))
        rows = res.fetchall()
        print(f"VOICES IN DB: {rows}")

if __name__ == "__main__":
    asyncio.run(check())
