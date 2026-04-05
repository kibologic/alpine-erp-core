from contextvars import ContextVar
from typing import Optional

# Current active tenant ID for the request lifecycle
_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def set_current_tenant(tenant_id: Optional[str]):
    _tenant_id_ctx.set(tenant_id)

def get_current_tenant() -> Optional[str]:
    return _tenant_id_ctx.get()
