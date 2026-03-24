"""
Alpine ERP — WebSocket / Realtime Layer
────────────────────────────────────────
Bridges gbil-events to connected WebSocket clients.
Events published via core.events.publish_event() are forwarded
to the relevant tenant room in real time.
"""

from gbil.realtime import get_server
from gbil.events import get_bus

_server = get_server()


def setup_realtime() -> None:
    """
    Wire the event bus → realtime bridge.
    Call once in lifespan after logger is configured.
    """
    bus = get_bus()

    @bus.subscribe("*")
    async def _forward_to_tenant(event) -> None:
        if event.tenant_id:
            await _server.to_tenant(event.tenant_id).emit(
                event.type, event.payload
            )
