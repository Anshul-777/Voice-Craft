"""
Seed master admin account with Enterprise plan + unlimited tokens.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.models.database import AsyncSessionLocal, create_tables
from app.models.user import User, Organization, UserPlan, UserRole
from app.utils.auth import hash_password
from sqlalchemy import select


async def seed():
    await create_tables()
    
    async with AsyncSessionLocal() as db:
        # Check if master already exists
        result = await db.execute(select(User).where(User.email == "master@voicecraft.ai"))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Master account already exists: id={existing.id}")
            # Update org to enterprise
            org_r = await db.execute(select(Organization).where(Organization.id == existing.organization_id))
            org = org_r.scalar_one_or_none()
            if org:
                org.plan = UserPlan.ENTERPRISE
                org.tts_chars_used_this_month = 0
                await db.commit()
                print(f"  Organization updated to ENTERPRISE plan")
            return

        # Create organization
        org = Organization(
            name="VoiceCraft Master",
            slug="voicecraft-master",
            plan=UserPlan.ENTERPRISE,
            tts_chars_used_this_month=0,
            is_active=True,
        )
        db.add(org)
        await db.flush()

        # Create master user
        user = User(
            email="master@voicecraft.ai",
            username="master",
            hashed_password=hash_password("Master@123"),
            full_name="VoiceCraft Master Admin",
            role=UserRole.OWNER,
            organization_id=org.id,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        print(f"✅ Master account created!")
        print(f"   Email:    master@voicecraft.ai")
        print(f"   Password: Master@123")
        print(f"   Plan:     ENTERPRISE (unlimited)")
        print(f"   User ID:  {user.id}")
        print(f"   Org ID:   {org.id}")


if __name__ == "__main__":
    asyncio.run(seed())
