import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant, verify_internal_token
from core.auth_deps import get_current_user
from core.models import CustomRole, RoleAtom, User
from core.atoms import ALL_ATOMS, SUPER_USER_ATOMS

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

router = APIRouter(tags=["Users"])


async def _check_atom(atom: str, user_id: str, session: AsyncSession):
    result = await session.execute(
        select(RoleAtom)
        .join(CustomRole, RoleAtom.role_id == CustomRole.id)
        .join(User, User.custom_role_id == CustomRole.id)
        .where(User.id == user_id, RoleAtom.atom == atom)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail=f"Missing permission: {atom}")


@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(User, CustomRole)
        .outerjoin(CustomRole, User.custom_role_id == CustomRole.id)
        .where(User.tenant_id == tenant_id)
        .order_by(User.created_at.desc())
    )
    users = result.all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role_name": cr.name if cr else None,
            "role_id": str(u.custom_role_id) if u.custom_role_id else None,
            "account_status": u.account_status,
            "active": u.active,
            "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u, cr in users
    ]


def _user_dict(u: User, cr: CustomRole = None) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role_name": cr.name if cr else None,
        "role_id": str(u.custom_role_id) if u.custom_role_id else None,
        "account_status": u.account_status,
        "active": u.active,
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


async def check_super_user_protection(
    db: AsyncSession,
    tenant_id: str,
    user_id: str
):
    # Find super user role for this tenant
    su_role = await db.execute(
        select(CustomRole).where(
            CustomRole.tenant_id == tenant_id,
            CustomRole.is_system == True,
            CustomRole.name == "Super User"
        )
    )
    su_role = su_role.scalar_one_or_none()
    if not su_role:
        return
    
    # Count users with super user role
    count = await db.execute(
        select(func.count(User.id)).where(
            User.custom_role_id == su_role.id,
            User.account_status == "active"
        )
    )
    count = count.scalar()
    
    # Check if this user is the last super user
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if user and count == 1 and user.custom_role_id == su_role.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the last Super User. Assign Super User role to another member first."
        )


class InviteRequest(BaseModel):
    email: str
    role_id: str
    full_name: str | None = None
    name: str | None = None  # legacy alias

@router.post("/users/invite", dependencies=[Depends(verify_internal_token)])
async def invite_user(
    data: InviteRequest,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    existing = await session.execute(
        select(User).where(User.email == data.email, User.tenant_id == tenant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        tenant_id=tenant_id, 
        email=data.email, 
        custom_role_id=data.role_id, 
        account_status="active",
        active=True, 
        full_name=data.full_name
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    # Get role to construct user dict
    cr_result = await session.execute(select(CustomRole).where(CustomRole.id == data.role_id))
    cr = cr_result.scalar_one_or_none()
    
    return _user_dict(user, cr)


# ── Atoms ────────────────────────────────────────────────────────────────────

@router.get("/atoms")
async def list_atoms(current_user: dict = Depends(get_current_user)):
    return ALL_ATOMS


# ── Roles ────────────────────────────────────────────────────────────────────

@router.get("/roles")
async def list_roles(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_user["tenant_memberships"][0]["tenant_id"] if current_user.get("tenant_memberships") else None
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant membership found")

    result = await session.execute(
        select(CustomRole).where(CustomRole.tenant_id == tenant_id)
    )
    roles = result.scalars().all()
    out = []
    for role in roles:
        atoms_result = await session.execute(
            select(RoleAtom).where(RoleAtom.role_id == role.id)
        )
        atoms = [a.atom for a in atoms_result.scalars().all()]
        out.append({
            "id": str(role.id),
            "name": role.name,
            "is_system": role.is_system,
            "atoms": atoms,
        })
    return out


class CreateRoleBody(BaseModel):
    name: str
    atoms: list[str] = []


@router.post("/roles")
async def create_role(
    body: CreateRoleBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_atom("users.manage_roles", current_user["user_id"], session)
    tenant_id = current_user["tenant_memberships"][0]["tenant_id"] if current_user.get("tenant_memberships") else None
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant membership found")

    role = CustomRole(
        tenant_id=tenant_id,
        name=body.name,
        is_system=False,
        created_by=current_user["user_id"],
    )
    session.add(role)
    await session.flush()
    for atom in body.atoms:
        if atom in ALL_ATOMS:
            session.add(RoleAtom(role_id=role.id, atom=atom))
    await session.commit()
    return {"id": str(role.id), "name": role.name, "is_system": role.is_system, "atoms": body.atoms}


class UpdateRoleBody(BaseModel):
    name: Optional[str] = None
    atoms: Optional[list[str]] = None


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: uuid.UUID,
    body: UpdateRoleBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_atom("users.manage_roles", current_user["user_id"], session)
    result = await session.execute(select(CustomRole).where(CustomRole.id == str(role_id)))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    if role.is_system:
        raise HTTPException(403, "Cannot modify system role")
    if body.name:
        role.name = body.name
    if body.atoms is not None:
        await session.execute(delete(RoleAtom).where(RoleAtom.role_id == str(role_id)))
        for atom in body.atoms:
            if atom in ALL_ATOMS:
                session.add(RoleAtom(role_id=role.id, atom=atom))
    await session.commit()
    return {"id": str(role.id), "name": role.name, "is_system": role.is_system, "atoms": body.atoms or []}


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_atom("users.manage_roles", current_user["user_id"], session)
    result = await session.execute(select(CustomRole).where(CustomRole.id == str(role_id)))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    if role.is_system:
        raise HTTPException(403, "Cannot delete system role")
    await session.delete(role)
    await session.commit()
    return {"ok": True}


# ── Assign Role ──────────────────────────────────────────────────────────────

class AssignRoleBody(BaseModel):
    role_id: Optional[str] = None  # None to unassign


@router.post("/users/{user_id}/assign-role")
async def assign_role(
    user_id: str,
    body: AssignRoleBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_atom("users.manage_roles", current_user["user_id"], session)
    tenant_id = current_user["tenant_memberships"][0]["tenant_id"] if current_user.get("tenant_memberships") else None
    
    await check_super_user_protection(session, tenant_id, str(user_id))

    result = await session.execute(select(User).where(User.id == str(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
        
    user.custom_role_id = body.role_id if body.role_id else None
    await session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/from-org")
async def remove_user_from_org(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Depending on how frontend expects this... wait, spec says FLOW 6 User removed from org
    # Check atoms if necessary.
    tenant_id = current_user["tenant_memberships"][0]["tenant_id"] if current_user.get("tenant_memberships") else None
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID missing")

    await check_super_user_protection(session, tenant_id, str(user_id))

    result = await session.execute(
        select(User).where(User.id == str(user_id), User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Remove from user_tenants
    await session.execute(
        delete(UserTenant).where(
            UserTenant.user_id == user.id,
            UserTenant.tenant_id == tenant_id
        )
    )
    
    user.custom_role_id = None
    
    other_orgs = await session.execute(
        select(func.count(UserTenant.id)).where(UserTenant.user_id == user.id)
    )
    if other_orgs.scalar() == 0:
        user.account_status = "pending"
    else:
        user.account_status = "active"

    await session.commit()
    return {"message": "User removed from organisation"}
