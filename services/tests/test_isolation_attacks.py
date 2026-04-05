import asyncio
import uuid
import sys
import os

# Add service dir to path to resolve 'core'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

from sqlalchemy import select, update
from core.models import Tenant, Media, Base
from core.tenant import set_current_tenant
from core.tasks import run_tenant_task
from core.db import AsyncSessionLocal, engine

async def simulate_attack():
    if not AsyncSessionLocal:
        print("DATABASE_URL not set, cannot run attacks.")
        return

    print("--- ⚔️  Multi-Tenant Isolation Attack Simulation ---")
    
    # Initialize missing schemas safely on Postgres (CREATE TABLE IF NOT EXISTS)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        # 1. Setup Mock Tenants
        org1_id = str(uuid.uuid4())
        org2_id = str(uuid.uuid4())
        
        print(f"Creating Org1 ({org1_id}) and Org2 ({org2_id})...")
        session.add(Tenant(id=org1_id, name="Secure Org 1", slug=f"org1-{org1_id[:8]}", tier="free"))
        session.add(Tenant(id=org2_id, name="Target Org 2", slug=f"org2-{org2_id[:8]}", tier="free"))
        await session.flush()

        # 2. Setup Mock Data (Org 2 has sensitive data)
        media2 = Media(
            id=str(uuid.uuid4()), 
            tenant_id=org2_id, 
            uploaded_by="attacker@test.com",
            filename="SECRET-financials.pdf",
            url=f"/media/{org2_id}/SECRET-financials.pdf",
            size_bytes=1024,
            mime_type="application/pdf"
        )
        session.add(media2)
        await session.flush()
        
        print(f"Org 2 created a sensitive media file: {media2.id}")

        # 3. ATTEMPT IDOR ATTACK (Org 1 context)
        print("\n[ATTACK 1] Switching context to Org 1 and fetching Org 2's media...")
        set_current_tenant(org1_id)
        
        query = select(Media).where(Media.id == media2.id)
        result = await session.execute(query)
        stolen_file = result.scalar_one_or_none()
        
        if stolen_file:
            print(f"❌ IDOR FAILED: Org 1 successfully stole Org 2's data!")
        else:
            print(f"✅ SUCCESS: Global Guard intercepted IDOR attempt.")

        # 4. ATTEMPT CROSS-ORG UPDATE (Org 1 context)
        print("\n[ATTACK 2] Attempting to update Org 2's media visibility from Org 1...")
        try:
            upd_query = update(Media).where(Media.id == media2.id).values(filename="PwnedByOrg1.pdf")
            await session.execute(upd_query)
            await session.flush()
            
            # Reset temporarily to verify
            set_current_tenant(None)
            check_query = select(Media).where(Media.id == media2.id)
            verified_media = (await session.execute(check_query)).scalar_one()
            
            if verified_media.filename == "PwnedByOrg1.pdf":
                print(f"❌ UPDATE BLOCKED FAILED: Org 1 successfully modified Org 2's data!")
            else:
                print(f"✅ SUCCESS: Update silently ignored or restricted to Org 1's boundary.")
        except Exception as e:
            print(f"✅ SUCCESS: Update correctly blocked by guard: {e}")

        # 5. ATTEMPT UN-CONTEXTED JOB
        print("\n[ATTACK 3] Attempting an un-contexted background job mutation...")
        set_current_tenant(None)
        try:
            upd_query = update(Media).where(Media.id == media2.id).values(filename="Ghost.pdf")
            await session.execute(upd_query)
            print(f"❌ BACKGROUND LEAK FAILED: Un-contexted update was allowed!")
        except RuntimeError as e:
            print(f"✅ SUCCESS: Un-contexted bulk update triggered system RuntimeError: {e}")
            
        await session.rollback()
        print("\n--- Simulation Complete ---")

if __name__ == "__main__":
    asyncio.run(simulate_attack())
