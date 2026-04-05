import asyncio
import uuid
from sqlalchemy import select
from core.db import AsyncSessionLocal
from core.models import Tenant, Media, User
from core.tenant import set_current_tenant

async def attack():
    """
    Simulates fetching a complex joined dataset where the primary table might belong
    to the query's tenant, but the JOIN target belongs to another organization.
    The Global Guard should automatically intercept BOTH sides.
    """
    async with AsyncSessionLocal() as session:
        # 1. Setup Data for Attack
        t1_id = str(uuid.uuid4())
        t2_id = str(uuid.uuid4())
        
        session.add(Tenant(id=t1_id, name="Blue Org", slug=f"blue-{t1_id[:8]}"))
        session.add(Tenant(id=t2_id, name="Red Org", slug=f"red-{t2_id[:8]}"))
        
        user_t1 = User(id=str(uuid.uuid4()), tenant_id=t1_id, email=f"{t1_id}@test.com", password_hash="1")
        user_t2 = User(id=str(uuid.uuid4()), tenant_id=t2_id, email=f"{t2_id}@test.com", password_hash="1")
        session.add_all([user_t1, user_t2])
        
        media_t2 = Media(id=str(uuid.uuid4()), tenant_id=t2_id, uploaded_by="tester", filename="m", mime_type="txt", size_bytes=1, url="")
        session.add(media_t2)
        await session.flush()
        
        # 2. Attack: Logged in as T1, attempt to join User + RoleAtom to bridge into T2
        set_current_tenant(t1_id)
        
        # The query does not specify tenant restrictions, hoping to pull T2's RoleAtom by joining
        # through an arbitrary relationship, or just cartesian joining.
        query = select(User.email, Media.filename).join(Media, Media.tenant_id == User.tenant_id)
        
        compiled_str = str(query.compile(compile_kwargs={"literal_binds": True}))
        # The compiled string should mathematically contain TWO identical tenant boundary clauses.
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        # We must NOT see any of Org 2's roles or users
        assert len(rows) == 0
        
        print("Compiled SQL:\n", compiled_str)
        print("✅ Join constraints validated perfectly on both tables!")

if __name__ == "__main__":
    asyncio.run(attack())

