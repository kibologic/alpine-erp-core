from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, Query
from core.auth import verify_internal_token
from core.exceptions import register_handlers
from core.db import engine
from core.module_registry import register_module, load_all_modules, get_registered_modules
from core.config import get_config
from gbil.logger import configure as configure_logger, get_logger
from core.ws_manager import manager
import asyncio
import core.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    configure_logger(
        level=cfg.LOG_LEVEL,
        environment=cfg.ENVIRONMENT,
        service_name=cfg.SERVICE_NAME,
    )
    log = get_logger("alpine-erp-core")
    log.info("startup", service=cfg.SERVICE_NAME, environment=cfg.ENVIRONMENT)

    async def heartbeat_loop():
        while True:
            await asyncio.sleep(30)
            for tid, connections in list(manager._connections.items()):
                dead = set()
                for ws in connections:
                    try:
                        await ws.send_text('{"type":"ping"}')
                    except Exception:
                        dead.add(ws)
                for ws in dead:
                    manager._connections[tid].discard(ws)

    asyncio.create_task(heartbeat_loop())
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


@app.websocket("/ws/tenant/{tenant_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    token: str = Query(...)
):
    if not token:
        await websocket.close(code=4001)
        return
    await manager.connect(tenant_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(tenant_id, websocket)


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
from modules.stock_take.router import router as stock_take_router
from modules.approvals.router import router as approvals_router
from modules.push.router import router as push_router
from modules.media.router import router as media_router
from modules.dashboard.router import router as dashboard_router

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
register_module(
    name="stock_take",
    router_factory=lambda app: app.include_router(stock_take_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="approvals",
    router_factory=lambda app: app.include_router(approvals_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="push",
    router_factory=lambda app: app.include_router(push_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="media",
    router_factory=lambda app: app.include_router(media_router, prefix="/api/v1"),
    tier="core",
)
register_module(
    name="dashboard",
    router_factory=lambda app: app.include_router(dashboard_router, prefix="/api/v1"),
    tier="core",
)

load_all_modules(app)
