import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import AsyncSessionLocal
from app.models.user import Organization, UserPlan, User, UserRole
from app.utils.auth import hash_password

async def seed_master_account():
    async with AsyncSessionLocal() as session:
        # Create Master Org
        org = Organization(
            name="VoiceCraft Master",
            slug="voicecraft-master",
            plan=UserPlan.ENTERPRISE
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)

        # Create Master User
        admin = User(
            email="admin@voicecraft.ai",
            username="voicecraft_master",
            hashed_password=hash_password("admin123"),
            full_name="Master Admin",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
            organization_id=org.id
        )
        session.add(admin)
        await session.commit()
        print(f"✅ Successfully created master account!")
        print(f"Email: admin@voicecraft.ai")
        print(f"Password: admin123")

if __name__ == "__main__":
    asyncio.run(seed_master_account())
