import asyncio
from typing import Coroutine, Any
from core.tenant import set_current_tenant, get_current_tenant

def run_tenant_task(tenant_id: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """
    Safely launches an asyncio background task while preserving the given tenant context.
    Standard `asyncio.create_task` drops the contextvars context of the caller
    unless explicitly re-hydrated. This prevents background tasks from bypassing
    the SQLAlchemy global tenant guard.
    """
    async def wrapper():
        # Set the tenant context in the new background task's context var
        set_current_tenant(tenant_id)
        try:
            return await coro
        finally:
            # Clean up just in case, though the task ending drops the context anyway
            set_current_tenant(None)
            
    return asyncio.create_task(wrapper())

def run_task_with_current_tenant(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """
    Safely launches an asyncio background task, automatically inheriting 
    the active tenant context from the current request thread.
    """
    tenant_id = get_current_tenant()
    if not tenant_id:
        raise RuntimeError("Cannot launch tenant task: no active tenant context found.")
    return run_tenant_task(tenant_id, coro)
