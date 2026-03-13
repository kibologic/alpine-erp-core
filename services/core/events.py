"""
Alpine ERP — Domain Event Bus (Stub)
────────────────────────────────────
Phase 3 event infrastructure, per DIRECTIVE.md.

Architecture decisions:
- Pure in-process async dispatcher (no Kafka/Redis yet).
- Handlers registered with `on_event()`.
- `publish_event()` MUST NOT block or raise inside handlers;
  exceptions are logged and swallowed so the calling
  transaction commits cleanly.
- When an async broker is added (Phase N), simply swap out
  `_dispatch()` with a producer.send() call — signature stays stable.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Handler registry: event_name → list[async handler]
_handlers: dict[str, list[Callable[[str, dict], Coroutine]]] = {}


def on_event(event_name: str):
    """Decorator: register an async handler for a named event."""
    def decorator(fn: Callable[[str, dict], Coroutine]):
        _handlers.setdefault(event_name, []).append(fn)
        return fn
    return decorator


async def _dispatch(event_name: str, payload: dict) -> None:
    """Fan-out to all registered handlers. Errors are isolated."""
    for handler in _handlers.get(event_name, []):
        try:
            await handler(event_name, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[events] Handler %s raised for %s: %s",
                handler.__name__, event_name, exc, exc_info=True
            )


async def publish_event(event_name: str, payload: dict) -> None:
    """
    Publish a domain event.

    Non-blocking: schedules the dispatch as a background task
    so that the calling database transaction is never blocked or
    rolled back by a downstream handler failure.

    Emitted events:
        purchase_order_drafted   — payload: {tenant_id, po_id, po_number}
        purchase_order_approved  — payload: {tenant_id, po_id, po_number, approved_by}
        goods_received           — payload: {tenant_id, po_id, line_id, product_id, quantity}
    """
    logger.debug("[events] %s → %s", event_name, payload)
    # Fire-and-forget so callers' transactions commit unimpeded
    asyncio.ensure_future(_dispatch(event_name, payload))
