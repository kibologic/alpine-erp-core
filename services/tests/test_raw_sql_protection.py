import asyncio
from sqlalchemy import text
import sqlalchemy.exc
from core.db import engine
import os

async def attack():
    os.environ["PARANOID_TENANT_MODE"] = "true"
    
    # We attempt an explicitly dirty fetch against 'media' table without specifying tenant_id
    # SQLAlchemy ORM handles tenant_id injection automatically, but raw executes do not.
    
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT id FROM media WHERE size_bytes > 0"))
            
    except sqlalchemy.exc.InvalidRequestError as e:
        assert "PARANOID MODE TRIGGERED" in str(e)
        print("✅ Raw SQL Trap Success: ", e)
    
    # If the user explicitly includes a check against tenant_id, paranoid mode trusts it.
    async with engine.begin() as conn:
        # Note: 1=0 to avoid accidentally returning data
        result = await conn.execute(text("SELECT id FROM media WHERE tenant_id = '00000000-0000-0000-0000-000000000000' AND 1=0"))
        print("✅ Safe SQL Trap Byapss Validation Success")

if __name__ == "__main__":
    asyncio.run(attack())

