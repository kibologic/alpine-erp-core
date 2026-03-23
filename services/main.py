import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from core.auth import verify_internal_token
from core.exceptions import register_handlers
from core.db import engine
from core.module_registry import register_module, load_all_modules, get_registered_modules
import core.models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic migrations — no create_all here
    yield


app = FastAPI(
    title="Alpine ERP Core",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

register_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/modules")
async def list_modules() -> list[dict]:
    """Returns all registered modules — used by frontend to sync module availability."""
    return get_registered_modules()


# --- Module self-registration ---
# Open-core modules only. Enterprise modules live in kibologic/alpine-erp.

from modules.auth.router import router as auth_router
from modules.tenant.router import router as tenant_router
from modules.inventory.router import router as inventory_router
from modules.pos.router import router as pos_router
from modules.users.router import router as users_router
from modules.users.audit_router import router as audit_router

register_module(
    name="auth",
    router_factory=lambda app: app.include_router(auth_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="tenant",
    router_factory=lambda app: app.include_router(tenant_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="inventory",
    router_factory=lambda app: app.include_router(inventory_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="pos",
    router_factory=lambda app: app.include_router(pos_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="users",
    router_factory=lambda app: app.include_router(users_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="audit",
    router_factory=lambda app: app.include_router(audit_router, prefix="/api/v1"),
    tier="core",
)

load_all_modules(app)
