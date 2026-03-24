"""
Alpine ERP — Domain Event Bus
─────────────────────────────
Thin wrapper around gbil-events. Keeps the existing
publish_event / on_event API stable for all call sites.

Architecture decisions:
- Pure in-process async dispatcher backed by gbil EventBus.
- Handlers registered with on_event(); gbil wildcard routing available.
- publish_event() fires-and-forgets so callers' DB transactions
  commit cleanly — handler exceptions are isolated by gbil.
- When an async broker is added, attach an EventStore to the bus
  in lifespan and swap nothing else.
"""

from typing import Any, Callable, Coroutine
import asyncio

from gbil.events import get_bus, Event

_bus = get_bus()


def on_event(event_name: str):
    """Decorator: register an async handler for a named event."""
    def decorator(fn: Callable):
        async def _wrapper(event: Event) -> None:
            await fn(event.type, event.payload)
        _wrapper.__name__ = fn.__name__
        _bus.on(event_name, _wrapper)
        return fn
    return decorator


async def publish_event(
    event_name: str,
    payload: dict,
    tenant_id: str | None = None,
) -> None:
    """
    Publish a domain event. Fire-and-forget.
    tenant_id is forwarded to gbil Event for realtime routing.
    """
    event = Event(type=event_name, payload=payload, tenant_id=tenant_id)
    asyncio.ensure_future(_bus.publish(event))
