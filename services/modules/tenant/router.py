from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_internal_token
from core.auth_deps import get_current_user
from core.db import get_session
from core.models import JoinRequest, Tenant, User, UserTenant

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


# ── Tenant search ────────────────────────────────────────────────────────────

@router.get("/search")
async def search_tenants(
    q: str = Query(..., description="Search query"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Tenant).where(
            Tenant.name.ilike(f"%{q}%"),
            Tenant.active == True,
        ).limit(20)
    )
    tenants = result.scalars().all()

    output = []
    for t in tenants:
        member_count_result = await session.execute(
            select(func.count(UserTenant.id)).where(UserTenant.tenant_id == t.id)
        )
        member_count = member_count_result.scalar() or 0
        output.append({"id": t.id, "name": t.name, "member_count": member_count})

    return output


# ── Join requests ─────────────────────────────────────────────────────────────

class JoinRequestBody(BaseModel):
    tenant_id: str


@router.post("/join-request")
async def create_join_request(
    body: JoinRequestBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["user_id"]

    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == body.tenant_id, Tenant.active == True)
    )
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Organisation not found")

    # Check not already member
    existing_member = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == body.tenant_id,
        )
    )
    if existing_member.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already a member of this organisation")

    # Check no pending request
    existing_request = await session.execute(
        select(JoinRequest).where(
            JoinRequest.user_id == user_id,
            JoinRequest.tenant_id == body.tenant_id,
            JoinRequest.status == "pending",
        )
    )
    if existing_request.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A pending join request already exists")

    join_req = JoinRequest(
        user_id=user_id,
        tenant_id=body.tenant_id,
        status="pending",
    )
    session.add(join_req)
    await session.commit()

    return {"message": "Join request sent"}


@router.get("/join-requests")
async def list_join_requests(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["user_id"]

    # Get tenants where current user is admin
    admin_tenants_result = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.role == "admin",
        )
    )
    admin_tenant_ids = [ut.tenant_id for ut in admin_tenants_result.scalars().all()]

    if not admin_tenant_ids:
        return []

    requests_result = await session.execute(
        select(JoinRequest).where(
            JoinRequest.tenant_id.in_(admin_tenant_ids),
            JoinRequest.status == "pending",
        )
    )
    join_requests = requests_result.scalars().all()

    output = []
    for jr in join_requests:
        user_result = await session.execute(
            select(User).where(User.id == jr.user_id)
        )
        user = user_result.scalar_one_or_none()
        output.append({
            "id": jr.id,
            "tenant_id": jr.tenant_id,
            "status": jr.status,
            "requested_at": jr.requested_at.isoformat() if jr.requested_at else None,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
            } if user else None,
        })

    return output


@router.post("/join-requests/{request_id}/approve")
async def approve_join_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["user_id"]

    jr_result = await session.execute(
        select(JoinRequest).where(JoinRequest.id == request_id)
    )
    jr = jr_result.scalar_one_or_none()
    if not jr:
        raise HTTPException(status_code=404, detail="Join request not found")

    # Verify current user is admin of that tenant
    admin_check = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == jr.tenant_id,
            UserTenant.role == "admin",
        )
    )
    if not admin_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorised to approve for this organisation")

    # Add user to user_tenants
    new_membership = UserTenant(
        user_id=jr.user_id,
        tenant_id=jr.tenant_id,
        role="cashier",
    )
    session.add(new_membership)

    jr.status = "approved"
    jr.reviewed_at = datetime.utcnow()
    jr.reviewed_by = user_id
    await session.commit()

    return {"message": "User approved"}


@router.post("/join-requests/{request_id}/reject")
async def reject_join_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user["user_id"]

    jr_result = await session.execute(
        select(JoinRequest).where(JoinRequest.id == request_id)
    )
    jr = jr_result.scalar_one_or_none()
    if not jr:
        raise HTTPException(status_code=404, detail="Join request not found")

    # Verify current user is admin of that tenant
    admin_check = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == jr.tenant_id,
            UserTenant.role == "admin",
        )
    )
    if not admin_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorised to reject for this organisation")

    jr.status = "rejected"
    jr.reviewed_at = datetime.utcnow()
    jr.reviewed_by = user_id
    await session.commit()

    return {"message": "User rejected"}
