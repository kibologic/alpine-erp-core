from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_internal_token
from core.auth_deps import get_current_user, require_atom
from core.db import get_session
from core.models import JoinRequest, Tenant, User, UserTenant, CustomRole, OrgInvite


class TenantUpdateBody(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None

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
        "industry": tenant.industry,
        "country": tenant.country,
        "config": {
            "currency": "USD",
            "locale": "en",
            "timezone": "UTC",
        },
        "active": tenant.active,
    }


# ── Update tenant ─────────────────────────────────────────────────────────────

@router.patch("/{tid}")
async def update_tenant(
    tid: str,
    body: TenantUpdateBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Verify caller belongs to this tenant and is admin
    tenant_role = current_user.get("tenant_role")
    if tenant_role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update organisation details")

    # Verify caller is operating on their own tenant
    caller_tenants = [m["tenant_id"] for m in current_user.get("tenant_memberships", [])]
    if tid not in caller_tenants:
        raise HTTPException(status_code=403, detail="Cannot update another organisation")

    result = await session.execute(
        select(Tenant).where(Tenant.id == tid)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Organisation not found")

    if body.name is not None:
        tenant.name = body.name
    if body.industry is not None:
        tenant.industry = body.industry
    if body.country is not None:
        tenant.country = body.country

    await session.commit()
    await session.refresh(tenant)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "industry": tenant.industry,
        "country": tenant.country,
        "tier": tenant.tier,
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


class ApproveRequestBody(BaseModel):
    role_id: str


@router.post("/join-requests/{request_id}/approve")
async def approve_join_request(
    request_id: str,
    body: ApproveRequestBody,
    current_user: dict = Depends(require_atom("users.manage")),
    session: AsyncSession = Depends(get_session),
):
    # Get join request
    jr_result = await session.execute(
        select(JoinRequest).where(JoinRequest.id == request_id)
    )
    jr = jr_result.scalar_one_or_none()
    if not jr:
        raise HTTPException(status_code=404, detail="Join request not found")

    # Validate role belongs to this tenant
    role_result = await session.execute(
        select(CustomRole)
        .where(
            CustomRole.id == body.role_id,
            CustomRole.tenant_id == current_user["tenant_id"]
        )
    )
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Assign role to user
    user_result = await session.execute(
        select(User).where(User.id == jr.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.custom_role_id = role.id
    user.account_status = "active"

    # Add to user_tenants
    import uuid
    new_membership = UserTenant(
        id=str(uuid.uuid4()),
        user_id=user.id,
        tenant_id=current_user["tenant_id"],
        role=role.id,
    )
    session.add(new_membership)

    jr.status = "approved"
    jr.role_id = role.id
    jr.reviewed_at = datetime.utcnow()
    jr.reviewed_by = current_user["user_id"]

    await session.commit()
    return {"message": "User approved and role assigned"}


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


# ── Invites ───────────────────────────────────────────────────────────────────

class InviteByEmailBody(BaseModel):
    email: str
    role_id: str


@router.post("/invite-by-email")
async def invite_by_email(
    body: InviteByEmailBody,
    current_user: dict = Depends(require_atom("users.manage")),
    session: AsyncSession = Depends(get_session),
):
    from datetime import timedelta
    import uuid
    tenant_id = current_user["tenant_id"]

    # Check if already a member
    existing = await session.execute(
        select(User)
        .join(UserTenant, UserTenant.user_id == User.id)
        .where(
            User.email == body.email,
            UserTenant.tenant_id == tenant_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already a member")

    # Check for existing pending invite
    existing_invite = await session.execute(
        select(OrgInvite).where(
            OrgInvite.email == body.email,
            OrgInvite.tenant_id == tenant_id,
            OrgInvite.status == "pending"
        )
    )
    if existing_invite.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Pending invite already exists for this email")

    # Create invite
    invite = OrgInvite(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        invited_by=current_user["user_id"],
        email=body.email,
        role_id=body.role_id,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    session.add(invite)

    # If user already exists on platform — link them
    user_result = await session.execute(
        select(User).where(User.email == body.email)
    )
    existing_user = user_result.scalar_one_or_none()
    if existing_user:
        invite.user_id = existing_user.id

    await session.commit()
    return {
        "message": f"Invite sent to {body.email}",
        "user_exists": existing_user is not None
    }


@router.post("/invite/{invite_id}/accept")
async def accept_invite(
    invite_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    import uuid
    result = await session.execute(
        select(OrgInvite).where(OrgInvite.id == invite_id)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.email != current_user["email"]:
        raise HTTPException(status_code=403, detail="This invite is not for you")

    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invite already used")

    if invite.expires_at.replace(tzinfo=None) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invite has expired")

    # Assign role and activate
    user_result = await session.execute(
        select(User).where(User.id == current_user["user_id"])
    )
    user = user_result.scalar_one_or_none()
    user.custom_role_id = invite.role_id
    user.account_status = "active"

    session.add(UserTenant(
        id=str(uuid.uuid4()),
        user_id=user.id,
        tenant_id=invite.tenant_id,
        role=invite.role_id
    ))

    invite.status = "accepted"
    invite.user_id = user.id
    await session.commit()

    return {"message": "Invite accepted. You can now access the organisation."}


@router.post("/invite/{invite_id}/decline")
async def decline_invite(
    invite_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(OrgInvite).where(OrgInvite.id == invite_id)
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.email != current_user["email"]:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    invite.status = "declined"
    await session.commit()
    return {"message": "Invite declined"}


@router.get("/invites")
async def list_invites(
    current_user: dict = Depends(require_atom("users.manage")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(OrgInvite, CustomRole)
        .join(CustomRole, OrgInvite.role_id == CustomRole.id)
        .where(
            OrgInvite.tenant_id == current_user["tenant_id"],
            OrgInvite.status == "pending"
        )
        .order_by(OrgInvite.created_at.desc())
    )
    return [
        {
            "id": oi.id,
            "email": oi.email,
            "role_name": cr.name,
            "created_at": oi.created_at.isoformat() if oi.created_at else None,
            "expires_at": oi.expires_at.isoformat() if oi.expires_at else None,
            "user_exists": oi.user_id is not None
        }
        for oi, cr in result.all()
    ]
