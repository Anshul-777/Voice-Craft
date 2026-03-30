"""
VoiceCraft Platform — Auth Utilities
JWT-based authentication with RBAC and API key support.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db
from app.models.user import ApiKey, User, UserRole

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ─────────────────────────────────────────────────────────────────
#  Password utilities
# ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─────────────────────────────────────────────────────────────────
#  JWT
# ─────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    user_id: str,
    org_id: str | None,
    role: str,
    extra: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "user_id": user_id,
        "org_id": org_id,
        "role": role,
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "iat": now, "exp": expire, "type": "refresh"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────────────────────────────────
#  API Key generation
# ─────────────────────────────────────────────────────────────────

def generate_api_key(prefix: str = "vc_live") -> tuple[str, str, str]:
    """
    Returns (raw_key, key_hash, key_prefix).
    raw_key is shown to user once and never stored.
    key_hash is stored in DB.
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{prefix}_{random_part}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:16]
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────
#  FastAPI dependency — current user
# ─────────────────────────────────────────────────────────────────

class CurrentUser:
    def __init__(
        self,
        user: User,
        token_payload: dict | None = None,
        via_api_key: bool = False,
        api_key_scopes: list[str] | None = None,
    ):
        self.user = user
        self.token_payload = token_payload or {}
        self.via_api_key = via_api_key
        self.api_key_scopes = api_key_scopes or []

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def org_id(self) -> str | None:
        return self.user.organization_id

    @property
    def role(self) -> UserRole:
        return self.user.role

    def has_scope(self, scope: str) -> bool:
        if not self.via_api_key:
            return True  # JWT users have all scopes
        return scope in self.api_key_scopes

    def require_scope(self, scope: str) -> None:
        if not self.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key missing scope: {scope}",
            )

    def require_role(self, *roles: UserRole) -> None:
        if self.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {[r.value for r in roles]}",
            )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    FastAPI dependency. Accepts either:
    - Bearer JWT token (Authorization: Bearer <token>)
    - API key (X-API-Key: vc_live_...)
    """
    # Try API key first
    if api_key:
        return await _authenticate_api_key(api_key, db)

    # Fall back to JWT
    if credentials:
        return await _authenticate_jwt(credentials.credentials, db)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _authenticate_jwt(token: str, db: AsyncSession) -> CurrentUser:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return CurrentUser(user=user, token_payload=payload)


async def _authenticate_api_key(raw_key: str, db: AsyncSession) -> CurrentUser:
    key_hash = hash_api_key(raw_key)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    api_key_obj = result.scalar_one_or_none()
    if not api_key_obj:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=401, detail="API key expired")

    user_result = await db.execute(
        select(User).where(User.id == api_key_obj.user_id, User.is_active == True)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Associated user not found")

    # Update usage
    api_key_obj.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    api_key_obj.requests_today += 1
    api_key_obj.requests_total += 1

    scopes = [s.strip() for s in api_key_obj.scopes.split(",")]
    return CurrentUser(user=user, via_api_key=True, api_key_scopes=scopes)


# ─────────────────────────────────────────────────────────────────
#  Optional auth (for public endpoints)
# ─────────────────────────────────────────────────────────────────

async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    try:
        return await get_current_user(credentials, api_key, db)
    except HTTPException:
        return None
