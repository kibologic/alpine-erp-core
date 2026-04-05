import asyncio
import os
import sys

# Add current directory to path to allow imports from core
sys.path.append(os.getcwd())

from core.db import engine
from sqlalchemy import text

async def run_migration():
    if not engine:
        print("Engine not initialized. DATABASE_URL is likely missing.")
        return
    
    async with engine.begin() as conn:
        print("Checking for tenants table columns...")
        # Postgres specific 'ADD COLUMN IF NOT EXISTS' is supported in recent versions
        try:
            await conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS default_locale VARCHAR(10) DEFAULT 'en-US'"))
            await conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS default_currency VARCHAR(10) DEFAULT 'MWK'"))
            print("Migration successful or columns already exist.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_migration())
