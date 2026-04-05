import pytest
import uuid
import asyncio
from sqlalchemy import select, func
from core.db import AsyncSessionLocal
from core.models import Tenant, Media
from core.tenant import set_current_tenant

async def attack():
    """
    Tests that complex aggregation functions like func.count() or func.sum()
    cannot bypass the ORM constraint guard and inadvertently leak volume data
    across organizations.
    """
    async with AsyncSessionLocal() as session:
        # 1. Setup Data for Attack
        t1_id = str(uuid.uuid4())
        t2_id = str(uuid.uuid4())
        
        session.add(Tenant(id=t1_id, name="Blue Org aggregate test", slug=f"ba-{t1_id[:8]}"))
        session.add(Tenant(id=t2_id, name="Red Org aggregate test", slug=f"ra-{t2_id[:8]}"))
        
        # Org 1 has 1 file
        m1 = Media(id=str(uuid.uuid4()), tenant_id=t1_id, uploaded_by="u1", filename="file1.txt", url="", size_bytes=100, mime_type="txt")
        # Org 2 has 3 files
        m2 = Media(id=str(uuid.uuid4()), tenant_id=t2_id, uploaded_by="u2", filename="secret1.txt", url="", size_bytes=5000, mime_type="txt")
        m3 = Media(id=str(uuid.uuid4()), tenant_id=t2_id, uploaded_by="u2", filename="secret2.txt", url="", size_bytes=5000, mime_type="txt")
        m4 = Media(id=str(uuid.uuid4()), tenant_id=t2_id, uploaded_by="u2", filename="secret3.txt", url="", size_bytes=5000, mime_type="txt")
        
        session.add_all([m1, m2, m3, m4])
        await session.flush()
        
        # 2. Attack: Logged in as Org 1
        set_current_tenant(t1_id)
        
        # Unsafely querying the count of ALL media files
        query = select(func.count(Media.id))
        result = await session.execute(query)
        total_count = result.scalar()
        
        # The result MUST be 1, because Org 1 only has 1 file. 
        # If it returns 4, the Guard failed to inject WHERE into the aggregate calculation.
        assert total_count == 1
        
        # Attack 2: Unsafely querying aggregate SUM
        query_sum = select(func.sum(Media.size_bytes))
        result_sum = await session.execute(query_sum)
        total_bytes = result_sum.scalar()
        
        # The sum should only be 100
        assert total_bytes == 100
        print("✅ Aggregate isolation validated perfectly!")

if __name__ == "__main__":
    asyncio.run(attack())
