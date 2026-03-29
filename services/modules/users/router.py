import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
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

router = APIRouter(prefix="/users", tags=["Users"])


async def _check_atom(atom: str, user_id: str, session: AsyncSession):
    result = await session.execute(
        select(RoleAtom)
        .join(CustomRole, RoleAtom.role_id == CustomRole.id)
        .join(User, User.custom_role_id == CustomRole.id)
        .where(User.id == user_id, RoleAtom.atom == atom)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail=f"Missing permission: {atom}")


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
            "custom_role_id": str(u.custom_role_id) if u.custom_role_id else None,
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
        "custom_role_id": str(u.custom_role_id) if u.custom_role_id else None,
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


@router.post("/{user_id}/assign-role")
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_atom("users.manage_roles", current_user["user_id"], session)
    result = await session.execute(select(User).where(User.id == str(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    user.custom_role_id = body.role_id if body.role_id else None
    await session.commit()
    return {"ok": True}
