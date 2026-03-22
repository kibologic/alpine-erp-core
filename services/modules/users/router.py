from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant, verify_internal_token
from core.models import User

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
            "role": u.role,
            "active": u.active,
            "created_at": u.created_at.isoformat(),
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
