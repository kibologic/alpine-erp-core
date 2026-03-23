from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_internal_token
from core.db import get_session
from core.models import Tenant

router = APIRouter(prefix="/tenant", tags=["tenant"])

# Tier → plan mapping (Tenant.tier is the source of truth)
_TIER_TO_PLAN = {
    "free": "free",
    "pro": "pro",
    "enterprise": "enterprise",
}

# Default capabilities per plan
_PLAN_CAPABILITIES = {
    "free": ["pos", "inventory", "users", "dashboard"],
    "pro": ["pos", "inventory", "users", "dashboard"],
    "enterprise": ["pos", "inventory", "users", "dashboard"],
}


@router.get("/{tenant_id}/config", dependencies=[Depends(verify_internal_token)])
async def get_tenant_config(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    plan = _TIER_TO_PLAN.get(tenant.tier, "free")

    return {
        "id": tenant.id,
        "name": tenant.name,
        "plan": plan,
        "capabilities": _PLAN_CAPABILITIES.get(plan, _PLAN_CAPABILITIES["free"]),
        "config": {
            "currency": "USD",
            "locale": "en",
            "timezone": "UTC",
        },
        "active": tenant.active,
    }
