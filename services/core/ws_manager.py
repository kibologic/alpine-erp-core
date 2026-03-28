from fastapi import WebSocket
from typing import Dict, Set
import json
import uuid
from datetime import datetime, timezone


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(
        self, tenant_id: str, websocket: WebSocket
    ):
        await websocket.accept()
        if tenant_id not in self._connections:
            self._connections[tenant_id] = set()
        self._connections[tenant_id].add(websocket)

    def disconnect(
        self, tenant_id: str, websocket: WebSocket
    ):
        if tenant_id in self._connections:
            self._connections[tenant_id].discard(websocket)
            if not self._connections[tenant_id]:
                del self._connections[tenant_id]

    async def broadcast(
        self,
        tenant_id: str,
        event_type: str,
        payload: dict
    ):
        if tenant_id not in self._connections:
            return
        message = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "payload": payload
        }
        dead = set()
        for ws in self._connections[tenant_id]:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections[tenant_id].discard(ws)

    @property
    def connection_count(self) -> int:
        return sum(
            len(conns)
            for conns in self._connections.values()
        )


manager = ConnectionManager()
