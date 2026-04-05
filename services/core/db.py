import logging
import os
from typing import AsyncGenerator

from sqlalchemy import event, select, delete, update
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, ORMExecuteState, Session
import sqlalchemy.exc
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

if engine:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _paranoid_raw_sql_guard(conn, cursor, statement, parameters, context, executemany):
        if os.getenv("PARANOID_TENANT_MODE") == "true":
            stmt_lower = statement.lower()
            sensitive_tables = ["sales", "media", "payments", "role_atoms", "kitchen_orders", "tab_lines"]
            
            # If the query hits a sensitive table, it MUST have a tenant constraint or be an alembic migration
            if any(f" {t}" in stmt_lower for t in sensitive_tables) or any(f"\"{t}\"" in stmt_lower for t in sensitive_tables):
                if "tenant_id" not in stmt_lower and "alembic_version" not in stmt_lower:
                    # Allow explicitly tagged super_user options
                    if context and getattr(context, "execution_options", {}).get("super_user"):
                        return
                    raise sqlalchemy.exc.InvalidRequestError(f"PARANOID MODE TRIGGERED 🚨: Un-scoped raw SQL detected hitting sensitive table! Statement: {statement}")

class Base(DeclarativeBase):
    pass


@event.listens_for(Session, "do_orm_execute")
def _do_orm_execute(state: ORMExecuteState):
    """
    Automatically adds a `tenant_id` filter to any query targeting a model
    that has a `tenant_id` column, provided a tenant context is active.
    """
    tenant_id = get_current_tenant()

    if state.execution_options.get("super_user"):
        return

    if state.is_select:
        # If no tenant is set, global/system tasks are allowed to READ all tenants
        if not tenant_id:
            return
            
        for mapper in state.all_mappers:
            if hasattr(mapper.class_, "tenant_id"):
                state.statement = state.statement.where(mapper.class_.tenant_id == tenant_id)

    elif state.is_update or state.is_delete:
        # Prevent any mutations across organizations without an active tenant ID
        # We loop through all mappers related to this query
        for mapper in getattr(state, "all_mappers", []):
            if hasattr(mapper.class_, "tenant_id"):
                if not tenant_id:
                    print(f"DEBUG: Guard blocked update on {mapper.class_.__name__} because tenant_id was None")
                    raise RuntimeError(
                        f"FATAL: Attempted a cross-org UPDATE/DELETE on {mapper.class_.__name__} "
                        "without an active tenant context. Action blocked by security guard."
                    )
                state.statement = state.statement.where(mapper.class_.tenant_id == tenant_id)
        
        # Fallback check in case all_mappers is empty but we have an explicit statement table
        if not getattr(state, "all_mappers", []):
            table = getattr(state.statement, 'table', None)
            if table is not None and 'tenant_id' in table.columns:
                if not tenant_id:
                    raise RuntimeError(
                        f"FATAL: Attempted a cross-org UPDATE/DELETE on table '{table.name}' "
                        "without an active tenant context. Action blocked by security guard."
                    )
                state.statement = state.statement.where(table.c.tenant_id == tenant_id)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not set. Cannot create database session."
        )
    async with AsyncSessionLocal() as session:
        yield session
