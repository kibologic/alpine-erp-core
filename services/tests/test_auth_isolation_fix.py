import pytest
import uuid
import bcrypt
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from main import app
from core.db import AsyncSessionLocal
from core.models import Tenant, User, UserTenant

pytestmark = pytest.mark.asyncio

async def test_login_flow_after_isolation_hardening():
    """
    Validates that the login flow correctly establishes tenant context
    to satisfy the ORM guard during the 'last_login' update, preventing a 500 error.
    """
    email = f"test-{uuid.uuid4()}@alpine.com"
    password = "securepassword123"
    
    async with AsyncSessionLocal() as session:
        # 1. Setup Tenant and User
        t_id = str(uuid.uuid4())
        tenant = Tenant(id=t_id, name="Test Org", slug=f"test-{t_id[:8]}", active=True)
        session.add(tenant)
        
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=t_id,
            email=email,
            password_hash=pw_hash,
            full_name="Test User",
            account_status="active",
            active=True
        )
        session.add(user)
        
        # Must have membership or login fails with 403
        session.add(UserTenant(user_id=user.id, tenant_id=t_id, role="admin"))
        
        await session.commit()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. Attempt Login
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password}
        )
        
        # 3. Validation
        # If the guard is still broken, this would be a 500
        if response.status_code != 200:
            raise Exception(f"Login failed with {response.status_code}: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == email
        
    # 4. Verify DB was actually updated
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.email == email))
        updated_user = res.scalar_one()
        assert updated_user.last_login is not None
