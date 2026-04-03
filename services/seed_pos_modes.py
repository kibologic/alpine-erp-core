import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import os

# Hardcoded for the demo environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://alpine:alpine_dev_2026@localhost:5432/alpine_erp")
TENANT_ID = "00000000-0000-0000-0000-000000000001" # Default demo tenant

# Import models
# Note: In a production script we'd import from the app, 
# but for a quick seed we can just define the minimal insert.
from core.models import TerminalConfig, Base

async def seed_terminal_config():
    engine = create_async_engine(DATABASE_URL)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with AsyncSessionLocal() as session:
        # Check if config exists
        result = await session.execute(
            select(TerminalConfig).where(
                TerminalConfig.tenant_id == TENANT_ID,
                TerminalConfig.terminal_id == "REG-001"
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            print("Seeding TerminalConfig for REG-001...")
            config = TerminalConfig(
                id=str(uuid.uuid4()),
                tenant_id=TENANT_ID,
                terminal_id="REG-001",
                name="Main Bar Terminal",
                enabled_modes=["instant", "tabbed", "orderful"],
                default_mode="tabbed" # Default to tabbed for the demo
            )
            session.add(config)
            await session.commit()
            print("Seed complete.")
        else:
            print("TerminalConfig for REG-001 already exists. Updating to enable tabs...")
            existing.enabled_modes = ["instant", "tabbed", "orderful"]
            existing.default_mode = "tabbed"
            await session.commit()
            print("Update complete.")

if __name__ == "__main__":
    asyncio.run(seed_terminal_config())
