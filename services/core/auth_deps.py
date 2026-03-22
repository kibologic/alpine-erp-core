from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import AuthToken, User, UserTenant


async def get_current_user_optional(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> dict | None:
    """
    Same as get_current_user but returns None instead of raising 401.
    Use on endpoints that work without auth but should record the user when present.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(authorization=authorization, session=session)
    except HTTPException:
        return None


async def get_current_user(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Validates Bearer token from Authorization header.
    Returns { user_id, email, role, tenant_memberships[] }.
    Raises HTTP 401 if missing, invalid, or expired.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")

    result = await session.execute(
        select(AuthToken).where(AuthToken.token == token)
    )
    auth_token = result.scalar_one_or_none()

    if not auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    if datetime.utcnow() > auth_token.expires_at:
        await session.delete(auth_token)
        await session.commit()
        raise HTTPException(status_code=401, detail="Token expired")

    user_result = await session.execute(
        select(User).where(User.id == auth_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    tenants_result = await session.execute(
        select(UserTenant).where(UserTenant.user_id == user.id)
    )
    tenant_memberships = [
        {"tenant_id": ut.tenant_id, "role": ut.role}
        for ut in tenants_result.scalars().all()
    ]

    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_memberships": tenant_memberships,
    }
