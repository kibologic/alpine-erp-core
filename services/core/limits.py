import uuid
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Tenant, User, UserTenant, Product, CashSession

TIER_LIMITS = {
    "free": {
        "max_users": 3,
        "max_products": 500,
        "max_terminals": 0,
        "device_locked": True,
    },
    "pro": {
        "max_users": 50,
        "max_products": 10000,
        "max_terminals": 10,
        "device_locked": False,
    },
    "enterprise": {
        "max_users": -1,  # unlimited
        "max_products": -1,
        "max_terminals": -1,
        "device_locked": False,
    }
}

async def get_tenant_limits(tenant_id: str, db: AsyncSession) -> dict:
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    tier = tenant.tier if tenant else "free"
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])

async def check_limit(
    tenant_id: str,
    db: AsyncSession,
    limit_type: str,
    device_id: Optional[str] = None
) -> dict:
    """
    Returns: { "allowed": bool, "reason": str, "limit": int, "current": int, "upgrade_message": str }
    """
    limits = await get_tenant_limits(tenant_id, db)
    
    # Bypass all limits if tier is enterprise
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if tenant and tenant.tier == "enterprise":
        return {"allowed": True}
    
    if limit_type == "users":
        max_users = limits["max_users"]
        if max_users == -1:
            return {"allowed": True}
        
        # Count active users in this tenant
        count = await db.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == tenant_id,
                User.account_status == "active"
            )
        )
        return {
            "allowed": count < max_users,
            "reason": f"Free tier limit: {max_users} users maximum",
            "limit": max_users,
            "current": count,
            "upgrade_message": f"You have reached the {max_users} user limit on the free tier. Upgrade to Pro for up to 50 users."
        }
    
    if limit_type == "products":
        max_products = limits["max_products"]
        if max_products == -1:
            return {"allowed": True}
            
        count = await db.scalar(
            select(func.count(Product.id)).where(
                Product.tenant_id == tenant_id,
                Product.is_active == True
            )
        )
        return {
            "allowed": count < max_products,
            "reason": f"Free tier limit: {max_products} products maximum",
            "limit": max_products,
            "current": count,
            "upgrade_message": f"You have reached the {max_products} product limit. Upgrade to Pro for up to 10,000 products."
        }
    
    if limit_type == "terminal":
        max_terminals = limits["max_terminals"]
        device_locked = limits["device_locked"]
        
        if max_terminals == -1:
            return {"allowed": True}
        
        # Check device lock
        result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if device_locked and tenant.terminal_device_id:
            if device_id and tenant.terminal_device_id != device_id:
                return {
                    "allowed": False,
                    "reason": "Terminal is locked to another device",
                    "upgrade_message": "Free tier allows 1 terminal locked to a single device. Upgrade to Pro to use multiple devices."
                }
        
        # Count active sessions
        count = await db.scalar(
            select(func.count(CashSession.id)).where(
                CashSession.tenant_id == tenant_id,
                CashSession.status == "open"
            )
        )
        return {
            "allowed": count < max_terminals,
            "reason": f"Free tier limit: {max_terminals} terminal maximum",
            "limit": max_terminals,
            "current": count,
            "upgrade_message": "Free tier allows 1 terminal. Upgrade to Pro for up to 10 terminals."
        }
    
    return {"allowed": True}

class LimitEnforcer:
    """Legacy wrapper for compatibility with existing routers where needed"""
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    async def check_product_limit(self):
        res = await check_limit(self.tenant_id, self.session, "products")
        if not res["allowed"]:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail=res["upgrade_message"])

    async def check_sales_limit(self):
        # Kept for backward compatibility if needed, though not in new check_limit yet
        pass

    async def check_customer_limit(self):
        # Kept for backward compatibility
        pass

from fastapi import Depends
from core.db import get_session
from core.auth import get_current_tenant

async def get_limit_enforcer(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant)
) -> LimitEnforcer:
    return LimitEnforcer(session, tenant_id)
