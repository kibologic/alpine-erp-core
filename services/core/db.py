import logging
import os
from typing import AsyncGenerator

from sqlalchemy import event, select, delete, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState
from core.tenant import get_current_tenant

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
else:
    logger.warning(
        "DATABASE_URL is not set. "
        "Expected format: postgresql+asyncpg://user:pass@host/db. "
        "Database operations will fail until it is configured."
    )


class Base(DeclarativeBase):
    pass


@event.listens_for(AsyncSession, "do_orm_execute")
def _do_orm_execute(state: ORMExecuteState):
    """
    Automatically adds a `tenant_id` filter to any query targeting a model
    that has a `tenant_id` column, provided a tenant context is active.
    """
    tenant_id = get_current_tenant()
    
    # If no tenant is set in the context (global/system tasks), skip filtering.
    # In production, almost all web requests will have a tenant set.
    if not tenant_id:
        return

    if state.is_select:
        # Only filter if the model has a tenant_id attribute
        for mapper in state.all_mappers:
            if hasattr(mapper.class_, "tenant_id"):
                state.statement = state.statement.where(mapper.class_.tenant_id == tenant_id)

    elif state.is_update or state.is_delete:
        # For UPDATE/DELETE, we must also enforce the tenant boundary.
        # We can detect the model by inspecting the statement's table(s).
        # However, for simplicity and safety, we check the bind mapper if available.
        mapper = state.bind_mapper
        if mapper and hasattr(mapper.class_, "tenant_id"):
            state.statement = state.statement.where(mapper.class_.tenant_id == tenant_id)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not set. Cannot create database session."
        )
    async with AsyncSessionLocal() as session:
        yield session
