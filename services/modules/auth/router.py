import uuid
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import AuthToken, User, UserTenant

router = APIRouter(prefix="/auth", tags=["auth"])


def _now() -> datetime:
    return datetime.utcnow()


def _new_expiry() -> datetime:
    return _now() + timedelta(hours=24)


async def _issue_token(session: AsyncSession, user_id: str) -> tuple[str, datetime]:
    token = str(uuid.uuid4())
    expires_at = _new_expiry()
    session.add(AuthToken(user_id=user_id, token=token, expires_at=expires_at))
    await session.commit()
    return token, expires_at


async def _get_tenants(session: AsyncSession, user_id: str) -> list[dict]:
    result = await session.execute(
        select(UserTenant).where(UserTenant.user_id == user_id)
    )
    return [
        {"tenant_id": ut.tenant_id, "role": ut.role}
        for ut in result.scalars().all()
    ]


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    token: str


@router.post("/login")
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(User).where(User.email == data.email, User.active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.checkpw(data.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    tenants = await _get_tenants(session, user.id)
    if not tenants:
        raise HTTPException(status_code=403, detail="User has no organisation membership")

    token, expires_at = await _issue_token(session, user.id)

    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "role": user.role},
        "tenants": tenants,
        "expiresAt": expires_at.isoformat() + "Z",
    }


@router.post("/refresh")
async def refresh(
    data: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(AuthToken).where(AuthToken.token == data.token)
    )
    auth_token = result.scalar_one_or_none()

    if not auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    if _now() > auth_token.expires_at:
        await session.delete(auth_token)
        await session.commit()
        raise HTTPException(status_code=401, detail="Token expired")

    user_id = auth_token.user_id
    await session.delete(auth_token)
    await session.flush()

    token, expires_at = await _issue_token(session, user_id)

    return {
        "token": token,
        "expiresAt": expires_at.isoformat() + "Z",
    }


@router.get("/me")
async def me(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")

    result = await session.execute(
        select(AuthToken).where(AuthToken.token == token)
    )
    auth_token = result.scalar_one_or_none()

    if not auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    if _now() > auth_token.expires_at:
        await session.delete(auth_token)
        await session.commit()
        raise HTTPException(status_code=401, detail="Token expired")

    user_result = await session.execute(
        select(User).where(User.id == auth_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    tenants = await _get_tenants(session, user.id)

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "tenants": tenants,
    }
