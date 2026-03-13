import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

INTERNAL_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
header_scheme = APIKeyHeader(name="X-Internal-Token", auto_error=False)


async def verify_internal_token(
    token: str | None = Security(header_scheme),
) -> None:
    if not INTERNAL_TOKEN:
        raise RuntimeError(
            "INTERNAL_SERVICE_TOKEN is not set. "
            "This must be configured before starting the service."
        )
    if token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def get_current_tenant(
    tenant_id: str = Security(APIKeyHeader(name="X-Tenant-ID")),
) -> str:
    # Placeholder for real tenant validation/lookup
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return tenant_id
