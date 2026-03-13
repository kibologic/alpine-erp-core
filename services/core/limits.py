from datetime import datetime
from fastapi import HTTPException, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_session
from core.auth import get_current_tenant
from core.models import Product, Sale, Customer

# Hardcoded Free Tier Limits for Alpine ERP
LIMITS = {
    "max_products": 50,
    "max_sales_per_month": 100,
    "max_customers": 20,
}


class LimitEnforcer:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    async def check_product_limit(self):
        count = await self.session.scalar(
            select(func.count(Product.id)).where(Product.tenant_id == self.tenant_id)
        )
        if count >= LIMITS["max_products"]:
            raise HTTPException(
                status_code=403, 
                detail=f"Free tier limit reached: Maximum {LIMITS['max_products']} products allowed."
            )

    async def check_sales_limit(self):
        # Count sales in current month
        first_day = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = await self.session.scalar(
            select(func.count(Sale.id)).where(
                Sale.tenant_id == self.tenant_id,
                Sale.created_at >= first_day
            )
        )
        if count >= LIMITS["max_sales_per_month"]:
            raise HTTPException(
                status_code=403, 
                detail=f"Free tier limit reached: Maximum {LIMITS['max_sales_per_month']} sales per month allowed."
            )

    async def check_customer_limit(self):
        count = await self.session.scalar(
            select(func.count(Customer.id)).where(Customer.tenant_id == self.tenant_id)
        )
        if count >= LIMITS["max_customers"]:
            raise HTTPException(
                status_code=403, 
                detail=f"Free tier limit reached: Maximum {LIMITS['max_customers']} customers allowed."
            )


async def get_limit_enforcer(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant)
) -> LimitEnforcer:
    return LimitEnforcer(session, tenant_id)
