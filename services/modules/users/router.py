from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant, verify_internal_token
from core.models import User

VALID_ROLES = {"admin", "manager", "cashier"}

_ROLE_MAP = {
    "admin": {
        "roleId": "role_admin",
        "atoms": [
            "pos.sell", "pos.refund", "pos.open_session", "pos.close_session",
            "inventory.view", "inventory.adjust", "inventory.manage",
            "users.view", "users.manage", "settings.view", "settings.manage",
        ],
    },
    "manager": {
        "roleId": "role_manager",
        "atoms": [
            "pos.sell", "pos.refund", "pos.open_session", "pos.close_session",
            "inventory.view", "inventory.adjust",
            "users.view", "settings.view",
        ],
    },
    "cashier": {
        "roleId": "role_cashier",
        "atoms": ["pos.sell", "pos.open_session", "inventory.view"],
    },
}

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("")
async def list_users(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "active": u.active,
            "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.get("/{user_id}/role", dependencies=[Depends(verify_internal_token)])
async def get_user_role(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mapping = _ROLE_MAP.get(user.role, {"roleId": "role_viewer", "atoms": ["inventory.view"]})
    return mapping


def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "active": u.active,
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


class InviteRequest(BaseModel):
    email: str
    role: str
    full_name: str | None = None
    name: str | None = None  # legacy alias — ignored in favour of full_name


class RoleUpdateRequest(BaseModel):
    role: str


@router.post("/invite", dependencies=[Depends(verify_internal_token)])
async def invite_user(
    data: InviteRequest,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of: {sorted(VALID_ROLES)}")

    existing = await session.execute(
        select(User).where(User.email == data.email, User.tenant_id == tenant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(tenant_id=tenant_id, email=data.email, role=data.role, active=True, full_name=data.full_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_dict(user)


@router.patch("/{user_id}/role", dependencies=[Depends(verify_internal_token)])
async def update_user_role(
    user_id: str,
    data: RoleUpdateRequest,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of: {sorted(VALID_ROLES)}")

    result = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = data.role
    await session.commit()
    await session.refresh(user)
    return _user_dict(user)
