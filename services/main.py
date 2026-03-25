from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, Query
from core.auth import verify_internal_token
from core.exceptions import register_handlers
from core.db import engine
from core.module_registry import register_module, load_all_modules, get_registered_modules
from core.config import get_config
from core.realtime import setup_realtime, _server
from gbil.logger import configure as configure_logger, get_logger
import core.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    configure_logger(
        level=cfg.LOG_LEVEL,
        environment=cfg.ENVIRONMENT,
        service_name=cfg.SERVICE_NAME,
    )
    setup_realtime()
    log = get_logger("alpine-erp-core")
    log.info("startup", service=cfg.SERVICE_NAME, environment=cfg.ENVIRONMENT)
    yield
    log.info("shutdown")


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


@app.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    tenant_id: Optional[str] = Query(default=None),
):
    """WebSocket endpoint. Clients connect as: /ws?tenant_id=<id>"""
    await _server.handle_connection(websocket, tenant_id=tenant_id)


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
from modules.ws.router import router as ws_router

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

register_module(
    name="ws",
    router_factory=lambda app: app.include_router(ws_router),
    tier="core",
)

load_all_modules(app)
