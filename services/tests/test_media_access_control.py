import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from main import app
from core.db import AsyncSessionLocal
from core.models import Tenant, Media, User, AuthToken
from datetime import datetime, timedelta

pytestmark = pytest.mark.asyncio

async def test_forged_media_download_fails():
    """
    Simulates a full HTTP lifecycle attack where a valid user of Org A
    attempts to download a media file belonging to Org B by directly guessing the URL.
    """
    async with AsyncSessionLocal() as session:
        t1_id = str(uuid.uuid4())
        t2_id = str(uuid.uuid4())
        
        session.add(Tenant(id=t1_id, name="Attacker Org", slug=f"ao-{t1_id[:8]}"))
        session.add(Tenant(id=t2_id, name="Victim Org", slug=f"vo-{t2_id[:8]}"))
        
        user_org1 = User(id=str(uuid.uuid4()), tenant_id=t1_id, email=f"attacker@{t1_id}.com", password_hash="1")
        session.add(user_org1)
        
        # Victim org has a secret file mapped
        secret_file_id = str(uuid.uuid4())
        m2 = Media(id=secret_file_id, tenant_id=t2_id, uploaded_by="u2", filename="secret.pdf", url="", size_bytes=5000, mime_type="application/pdf")
        session.add(m2)
        
        # Generate valid Stateful token for Attacker
        attacker_token_str = f"sec-{uuid.uuid4()}"
        auth_t = AuthToken(
            id=str(uuid.uuid4()), 
            user_id=user_org1.id, 
            token=attacker_token_str, 
            expires_at=datetime.utcnow() + timedelta(days=1)
        )
        session.add(auth_t)
        
        await session.flush()
        
        headers = {
            "Authorization": f"Bearer {attacker_token_str}",
            "X-Tenant-ID": t2_id  # Attacker attempts to forge the header for Org 2!
        }
        
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attack: Attempt to download Victim's private file
        url = f"/api/v1/media/{t2_id}/{secret_file_id}_secret.pdf"
        response = await client.get(url, headers=headers)
        
        # Security Guard should explicitly reject due to header mismatch with Token claims OR global ORM intercept intercepting None.
        # It must NOT return 200 FileResponse
        assert response.status_code in [403, 401]
