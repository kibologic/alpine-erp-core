import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory token store: { token_str: { "user_id": str, "expires_at": datetime } }
# TODO: move to DB
_token_store: dict[str, dict] = {}


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    token: str


def _new_token(user_id: str) -> tuple[str, datetime]:
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=24)
    _token_store[token] = {"user_id": user_id, "expires_at": expires_at}
    return token, expires_at


@router.post("/login")
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(User).where(User.email == data.email, User.active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # NOTE: User table has no password_hash column yet.
    # Password verification is bypassed in dev — any password accepted for a valid email.
    # Add password_hash to the users migration before enabling real verification.

    token, expires_at = _new_token(user.id)

    return {
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
        },
        "expiresAt": expires_at.isoformat() + "Z",
    }


@router.post("/refresh")
async def refresh(data: RefreshRequest):
    entry = _token_store.get(data.token)

    if not entry:
        raise HTTPException(status_code=401, detail="Invalid token")

    if datetime.utcnow() > entry["expires_at"]:
        del _token_store[data.token]
        raise HTTPException(status_code=401, detail="Token expired")

    # Invalidate old token, issue new one
    user_id = entry["user_id"]
    del _token_store[data.token]

    token, expires_at = _new_token(user_id)

    return {
        "token": token,
        "expiresAt": expires_at.isoformat() + "Z",
    }
