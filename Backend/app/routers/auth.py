"""
VoiceCraft Platform — Auth Router
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import Organization, User, ApiKey, UserPlan, UserRole
from app.schemas import (
    UserRegisterRequest, UserLoginRequest, TokenResponse,
    UserResponse, ApiKeyCreateRequest, ApiKeyResponse,
)
from app.utils.auth import (
    create_access_token, create_refresh_token, decode_token,
    generate_api_key, get_current_user, hash_password, verify_password,
    CurrentUser,
)
from app.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    existing_un = await db.execute(select(User).where(User.username == body.username))
    if existing_un.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username taken")

    # Create organization
    from slugify import slugify
    org_name = body.organization_name or f"{body.username}'s Workspace"
    org_slug = slugify(org_name)

    # Ensure slug uniqueness
    existing_slug = await db.execute(select(Organization).where(Organization.slug == org_slug))
    if existing_slug.scalar_one_or_none():
        org_slug = f"{org_slug}-{body.username}"

    org = Organization(name=org_name, slug=org_slug, plan=UserPlan.FREE)
    db.add(org)
    await db.flush()

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.OWNER,
        organization_id=org.id,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(
            user.email, user.id, user.organization_id, user.role.value
        ),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(
            user.email, user.id, user.organization_id, user.role.value
        ),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user.user


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    raw_key, key_hash, key_prefix = generate_api_key()

    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = expires_at + timedelta(days=body.expires_days)

    api_key = ApiKey(
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=current_user.user_id,
        organization_id=current_user.org_id,
        scopes=",".join(body.scopes),
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    response = ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        raw_key=raw_key,  # only returned once
    )
    return response


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.organization_id == current_user.org_id,
            ApiKey.is_active == True,
        )
    )
    keys = result.scalars().all()
    return [ApiKeyResponse(
        id=k.id, name=k.name, key_prefix=k.key_prefix,
        scopes=k.scopes, created_at=k.created_at, expires_at=k.expires_at,
    ) for k in keys]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == current_user.org_id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(404, "API key not found")
    key.is_active = False
    await db.commit()
