import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.db import get_session
from core.models import Media
from core.auth_deps import get_current_tenant_id, get_current_user

router = APIRouter(prefix="/media", tags=["media"])

_MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/var/alpine/media")

@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    entity: str | None = Form(default=None),
    entity_id: str | None = Form(default=None),
    tenant_id: str = Depends(get_current_tenant_id),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}_{file.filename}"
    dest_dir = Path(_MEDIA_ROOT) / tenant_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_filename

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    url = f"/api/v1/media/{tenant_id}/{safe_filename}"
    mime_type = file.content_type or "application/octet-stream"
    size_bytes = len(contents)
    uploaded_by = current_user["user_id"]

    media_record = Media(
        id=file_id,
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
        filename=file.filename,
        url=url,
        size_bytes=size_bytes,
        mime_type=mime_type,
        entity=entity,
        entity_id=entity_id
    )
    db.add(media_record)
    await db.commit()

    return {"id": file_id, "url": url, "filename": file.filename, "size_bytes": size_bytes}

@router.get("/{requested_tenant}/{filename}")
async def download_media(
    requested_tenant: str,
    filename: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session)
):
    # Ensure no cross-tenant directory traversal or leak
    if requested_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden.")

    # Even though file is available on disk, we verify the ORM record still exists
    # If the user is in Tenant A, but tries to download Media belonging to Tenant B,
    # the SQLAlchemy global guard will silently intercept it and return None here.
    file_id = filename.split("_", 1)[0]
    result = await db.execute(select(Media).where(Media.id == file_id))
    media_record = result.scalar_one_or_none()
    
    if not media_record:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(_MEDIA_ROOT) / tenant_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File object not found on disc")
        
    return FileResponse(file_path, media_type=media_record.mime_type, filename=media_record.filename)
