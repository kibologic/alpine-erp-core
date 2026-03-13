import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from core.auth import verify_internal_token
from core.exceptions import register_handlers
from core.db import engine
import core.models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic migrations — no create_all here
    yield


app = FastAPI(
    title="Alpine ERP Service",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

register_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Open-core module routers
from modules.inventory.router import router as inventory_router
from modules.pos.router import router as pos_router

app.include_router(inventory_router, prefix="/api/v1")
app.include_router(pos_router, prefix="/api/v1")
