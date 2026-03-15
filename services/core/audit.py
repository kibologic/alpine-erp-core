"""
Alpine ERP — Audit Log Helper
"""

import json
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import AuditLog


async def log_event(
    session: AsyncSession,
    tenant_id: str,
    user_id: str | None,
    action: str,
    entity: str,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id if user_id and user_id != "SYSTEM" else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=json.dumps(detail) if detail else None,
    )
    session.add(entry)
