import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Header
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import AuthToken, JoinRequest, PasswordResetToken, Tenant, User, UserTenant

_JWT_SECRET = os.getenv("JWT_SECRET", "alpine_dev_jwt_secret_2026")
_JWT_ALGORITHM = "HS256"

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

    user.last_login = datetime.utcnow()
    await session.commit()

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

    memberships_result = await session.execute(
        select(UserTenant, Tenant)
        .join(Tenant, UserTenant.tenant_id == Tenant.id)
        .where(UserTenant.user_id == user.id)
    )
    memberships = memberships_result.all()

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "organisations": [
            {
                "tenant_id": str(ut.tenant_id),
                "name": t.name,
                "industry": t.industry,
                "country": t.country,
                "role": ut.role,
            }
            for ut, t in memberships
        ],
    }


class UpdateMeBody(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/me")
async def update_me(
    body: UpdateMeBody,
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")
    token_result = await session.execute(
        select(AuthToken).where(AuthToken.token == token)
    )
    auth_token = token_result.scalar_one_or_none()
    if not auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    if _now() > auth_token.expires_at:
        raise HTTPException(status_code=401, detail="Token expired")

    user_result = await session.execute(
        select(User).where(User.id == auth_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.phone is not None:
        user.phone = body.phone

    await session.commit()
    await session.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
    }


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    body: ChangePasswordBody,
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")
    token_result = await session.execute(
        select(AuthToken).where(AuthToken.token == token)
    )
    auth_token = token_result.scalar_one_or_none()
    if not auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    if _now() > auth_token.expires_at:
        raise HTTPException(status_code=401, detail="Token expired")

    user_result = await session.execute(
        select(User).where(User.id == auth_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.password_hash or not bcrypt.checkpw(
        body.current_password.encode(), user.password_hash.encode()
    ):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = bcrypt.hashpw(
        body.new_password.encode(), bcrypt.gensalt()
    ).decode()
    await session.commit()
    return {"message": "Password changed successfully"}


# ── Mobile JWT endpoints ────────────────────────────────────────────────────

class MobileLoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: str


class MobileRefreshRequest(BaseModel):
    refresh_token: str


def _issue_jwt(user_id: str, tenant_id: str, role: str, expires_in: int) -> str:
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


@router.post("/mobile/login")
async def mobile_login(
    data: MobileLoginRequest,
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

    ut_result = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user.id,
            UserTenant.tenant_id == data.tenant_id,
        )
    )
    membership = ut_result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="User is not a member of this organisation")

    access_token = _issue_jwt(user.id, data.tenant_id, membership.role, 3600)
    refresh_token = _issue_jwt(user.id, data.tenant_id, membership.role, 86400)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 3600,
    }


@router.post("/mobile/refresh")
async def mobile_refresh(data: MobileRefreshRequest):
    try:
        payload = jwt.decode(data.refresh_token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    access_token = _issue_jwt(
        payload["user_id"], payload["tenant_id"], payload["role"], 3600
    )

    return {
        "access_token": access_token,
        "expires_in": 3600,
    }


# ── Signup ──────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


class SignupRequest(BaseModel):
    full_name: str
    email: str
    password: str
    org_action: str  # "create" or "join"
    org_name: Optional[str] = None
    org_id: Optional[str] = None


@router.post("/signup")
async def signup(
    data: SignupRequest,
    session: AsyncSession = Depends(get_session),
):
    # Check email not already taken
    existing = await session.execute(
        select(User).where(User.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()

    if data.org_action == "create":
        if not data.org_name:
            raise HTTPException(status_code=400, detail="org_name required when org_action is 'create'")

        # Create tenant
        slug = _slugify(data.org_name)
        # Ensure slug uniqueness
        base_slug = slug
        suffix = 0
        while True:
            existing_tenant = await session.execute(
                select(Tenant).where(Tenant.slug == slug)
            )
            if not existing_tenant.scalar_one_or_none():
                break
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        tenant = Tenant(
            name=data.org_name,
            slug=slug,
            tier="free",
            active=True,
        )
        session.add(tenant)
        await session.flush()

        user = User(
            tenant_id=tenant.id,
            email=data.email,
            password_hash=password_hash,
            full_name=data.full_name,
            role="admin",
            active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        user_tenant = UserTenant(
            user_id=user.id,
            tenant_id=tenant.id,
            role="admin",
        )
        session.add(user_tenant)
        await session.flush()

        token, expires_at = await _issue_token(session, user.id)

        return {
            "token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name,
            },
            "tenants": [{"tenant_id": tenant.id, "role": "admin"}],
            "expiresAt": expires_at.isoformat() + "Z",
        }

    elif data.org_action == "join":
        if not data.org_id:
            raise HTTPException(status_code=400, detail="org_id required when org_action is 'join'")

        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == data.org_id, Tenant.active == True)
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Organisation not found")

        # Need a placeholder tenant_id for the user — use the target tenant
        user = User(
            tenant_id=tenant.id,
            email=data.email,
            password_hash=password_hash,
            full_name=data.full_name,
            role="cashier",
            active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        # Check not already member
        existing_membership = await session.execute(
            select(UserTenant).where(
                UserTenant.user_id == user.id,
                UserTenant.tenant_id == tenant.id,
            )
        )
        if existing_membership.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Already a member of this organisation")

        join_request = JoinRequest(
            user_id=user.id,
            tenant_id=tenant.id,
            status="pending",
        )
        session.add(join_request)
        await session.commit()

        return {"message": "Join request sent — awaiting admin approval"}

    else:
        raise HTTPException(status_code=400, detail="org_action must be 'create' or 'join'")


# ── Forgot / Reset Password ──────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    user_result = await session.execute(
        select(User).where(User.email == data.email)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        # Return 200 to avoid email enumeration
        return {"message": "If this email exists, a reset token has been issued"}

    token = str(uuid.uuid4())
    expires_at = _now() + timedelta(hours=1)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
        used=False,
    )
    session.add(reset_token)
    await session.commit()

    return {
        "reset_token": token,
        "message": "Use this token to reset your password",
    }


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    token_result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == data.token)
    )
    reset_token = token_result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    if reset_token.used:
        raise HTTPException(status_code=400, detail="Reset token already used")

    if _now() > reset_token.expires_at.replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Reset token expired")

    user_result = await session.execute(
        select(User).where(User.id == reset_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
    reset_token.used = True
    await session.commit()

    return {"message": "Password reset successful"}
