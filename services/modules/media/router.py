import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session

router = APIRouter(prefix="/media", tags=["media"])

_MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/var/alpine/media")


def _require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return x_tenant_id


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    entity: str | None = Form(default=None),
    entity_id: str | None = Form(default=None),
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
):
    from sqlalchemy import text

    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}_{file.filename}"
    dest_dir = Path(_MEDIA_ROOT) / tenant_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_filename

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    url = f"/media/{tenant_id}/{safe_filename}"
    mime_type = file.content_type or "application/octet-stream"
    size_bytes = len(contents)

    # Extract uploaded_by from JWT (best-effort)
    uploaded_by = tenant_id  # fallback
    if authorization and authorization.startswith("Bearer "):
        try:
            import os as _os
            from jose import jwt as _jwt
            secret = _os.getenv("JWT_SECRET", "alpine_dev_jwt_secret_2026")
            payload = _jwt.decode(authorization.removeprefix("Bearer "), secret, algorithms=["HS256"])
            uploaded_by = payload.get("user_id", tenant_id)
        except Exception:
            pass

    await db.execute(
        text("""
            INSERT INTO media (id, tenant_id, uploaded_by, filename, url, size_bytes, mime_type, entity, entity_id)
            VALUES (:id, :tid, :uploaded_by, :filename, :url, :size_bytes, :mime_type, :entity, :entity_id)
        """),
        {
            "id": file_id,
            "tid": tenant_id,
            "uploaded_by": uploaded_by,
            "filename": file.filename,
            "url": url,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
            "entity": entity,
            "entity_id": entity_id,
        },
    )
    await db.commit()

    return {"id": file_id, "url": url, "filename": file.filename, "size_bytes": size_bytes}
