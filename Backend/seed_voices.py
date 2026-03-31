import asyncio
from sqlalchemy import text
from app.models.database import engine

async def seed():
    print("🚀 Final seeding attempt...")
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT id, organization_id FROM users LIMIT 1"))
        user = res.fetchone()
        if not user:
            print("❌ No users found.")
            return
        
        uid, oid = user
        profiles = [
            ("sys-rachel", "Rachel (System)", "Professional female voice."),
            ("sys-josh", "Josh (System)", "Deep male voice."),
            ("sys-antigravity", "Antigravity (AI)", "Robotic intelligence.")
        ]
        
        for vid, name, desc in profiles:
            await conn.execute(text("""
                INSERT INTO voice_profiles (id, owner_id, organization_id, name, description, is_system, status, is_public)
                VALUES (:id, :owner, :org, :name, :desc, true, 'ready', true)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = 'ready'
            """), {"id": vid, "owner": uid, "org": oid, "name": name, "desc": desc})
            print(f"✅ Seeded: {name}")

if __name__ == "__main__":
    asyncio.run(seed())
