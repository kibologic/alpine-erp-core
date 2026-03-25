import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt

_JWT_SECRET = os.getenv("JWT_SECRET", "alpine_dev_jwt_secret_2026")
_JWT_ALGORITHM = "HS256"
_HEARTBEAT_TIMEOUT = 35  # seconds — expect ping every 30s

router = APIRouter(tags=["ws"])


# ── Connection manager ──────────────────────────────────────────────────────

class RegisterConnectionManager:
    def __init__(self):
        # { register_id: { tenant_id: { ws_id: WebSocket } } }
        self._connections: dict[str, dict[str, dict[str, WebSocket]]] = {}

    def add(self, register_id: str, tenant_id: str, ws_id: str, ws: WebSocket):
        self._connections.setdefault(register_id, {}).setdefault(tenant_id, {})[ws_id] = ws

    def remove(self, register_id: str, tenant_id: str, ws_id: str):
        try:
            del self._connections[register_id][tenant_id][ws_id]
            if not self._connections[register_id][tenant_id]:
                del self._connections[register_id][tenant_id]
            if not self._connections[register_id]:
                del self._connections[register_id]
        except KeyError:
            pass

    async def broadcast(
        self,
        register_id: str,
        tenant_id: str,
        message: dict,
        exclude_ws_id: Optional[str] = None,
    ):
        peers = self._connections.get(register_id, {}).get(tenant_id, {})
        dead = []
        for ws_id, ws in peers.items():
            if ws_id == exclude_ws_id:
                continue
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws_id)
        for ws_id in dead:
            self.remove(register_id, tenant_id, ws_id)


manager = RegisterConnectionManager()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _server_message(msg_type: str, register_id: str, tenant_id: str, payload: dict) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": msg_type,
        "source": "server",
        "register_id": register_id,
        "session_id": "",
        "tenant_id": tenant_id,
        "timestamp": _now_iso(),
        "payload": payload,
    }


def _validate_envelope(data: dict) -> bool:
    required = {"id", "type", "source", "register_id", "session_id", "tenant_id", "timestamp", "payload"}
    return required.issubset(data.keys())


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/register/{register_id}")
async def register_ws(
    websocket: WebSocket,
    register_id: str,
    token: Optional[str] = Query(default=None),
):
    # Auth
    if not token:
        await websocket.close(code=4001)
        return

    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except JWTError:
        await websocket.close(code=4001)
        return

    tenant_id: str = payload.get("tenant_id", "")
    if not tenant_id:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    ws_id = str(uuid.uuid4())
    manager.add(register_id, tenant_id, ws_id, websocket)

    # Send initial session_update on connect
    await websocket.send_text(json.dumps(
        _server_message("session_update", register_id, tenant_id, {
            "register_id": register_id,
            "status": "idle",
        })
    ))

    last_ping = asyncio.get_event_loop().time()

    async def _heartbeat_watcher():
        nonlocal last_ping
        while True:
            await asyncio.sleep(5)
            if asyncio.get_event_loop().time() - last_ping > _HEARTBEAT_TIMEOUT:
                await websocket.close(code=4002)
                return

    watcher_task = asyncio.create_task(_heartbeat_watcher())

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Heartbeat ping
            if msg.get("type") == "ping":
                last_ping = asyncio.get_event_loop().time()
                await websocket.send_text(json.dumps(
                    _server_message("pong", register_id, tenant_id, {})
                ))
                continue

            # Validate envelope
            if not _validate_envelope(msg):
                continue

            # Tenant isolation — drop messages from wrong tenant
            if msg.get("tenant_id") != tenant_id:
                continue

            # Fan out to peers on same register
            await manager.broadcast(register_id, tenant_id, msg, exclude_ws_id=ws_id)

    except WebSocketDisconnect:
        pass
    finally:
        watcher_task.cancel()
        manager.remove(register_id, tenant_id, ws_id)
