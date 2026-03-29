from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import AuthToken, User, UserTenant, CustomRole, RoleAtom


async def _resolve_token(token: str, session: AsyncSession) -> User:
    """Validate token and return the associated User. Raises 401 on failure."""
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

    return user


async def _check_tenant(user: User, tenant_id: str, session: AsyncSession) -> str:
    """Verify user belongs to tenant. Returns the user's role in that tenant."""
    result = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user.id,
            UserTenant.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="User does not belong to this organisation")
    return membership.role


async def _get_all_tenants(user: User, session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(UserTenant).where(UserTenant.user_id == user.id)
    )
    return [
        {"tenant_id": ut.tenant_id, "role": ut.role}
        for ut in result.scalars().all()
    ]


async def get_current_user(
    authorization: str | None = Header(None),
    tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Validates Bearer token. If X-Tenant-ID header is present, also verifies
    the user belongs to that tenant. Raises 401/403 on failure.
    Returns { user_id, email, role, tenant_memberships[], tenant_role (if tenant checked) }.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user = await _resolve_token(authorization.removeprefix("Bearer "), session)
    tenants = await _get_all_tenants(user, session)

    result: dict = {
        "user_id": user.id,
        "email": user.email,
        "tenant_memberships": tenants,
    }

    if tenant_id:
        tenant_role = await _check_tenant(user, tenant_id, session)
        result["tenant_role"] = tenant_role
        result["tenant_id"] = tenant_id

    return result


async def get_current_user_optional(
    authorization: str | None = Header(None),
    tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    session: AsyncSession = Depends(get_session),
) -> dict | None:
    """
    Same as get_current_user but returns None instead of raising on any failure.
    Use on endpoints that work without auth but should record the user when present.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return await get_current_user(
            authorization=authorization,
            tenant_id=tenant_id,
            session=session,
        )
    except HTTPException:
        return None

def require_atom(atom_name: str):
    async def atom_dependency(
        current_user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_session)
    ) -> dict:
        user_id = current_user["user_id"]
        result = await session.execute(
            select(RoleAtom)
            .join(CustomRole, RoleAtom.role_id == CustomRole.id)
            .join(User, User.custom_role_id == CustomRole.id)
            .where(User.id == user_id, RoleAtom.atom == atom_name)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail=f"Missing permission: {atom_name}")
        return current_user
    return atom_dependency
