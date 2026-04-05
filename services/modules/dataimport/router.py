"""
dataimport.router — FastAPI Routes
====================================
Thin orchestration layer. Connects the HTTP surface to the datapipe engine.
Each route delegates immediately to the engine — no business logic here.

Endpoints:
  GET  /dataimport/manifests          → list importable tables
  GET  /dataimport/{table}/template   → download blank XLSX template
  GET  /dataimport/{table}/export     → download data as XLSX
  POST /dataimport/{table}/preview    → validate upload (dry-run, no DB write)
  POST /dataimport/{table}/import     → validate + commit
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
import io

from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_internal_token, get_current_tenant
from core.auth_deps import get_user_atoms, get_current_user
from core.db import get_session
from core.datapipe.introspect import introspect_model
from core.datapipe.builder import build_template
from core.datapipe.parser import parse_workbook
from core.datapipe.coerce import coerce_row
from core.datapipe.validate import validate_rows
from core.datapipe.mapper import FKResolver
from core.datapipe.executor import execute_import
from core.datapipe.exporter import export_data

from .manifests import get_manifest, list_manifests

router = APIRouter(
    prefix="/dataimport",
    tags=["Data Import / Export"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _check_atom(atom: str, session: AsyncSession, current_user: dict):
    """Raise 403 if the current user doesn't hold the required atom."""
    user_id = current_user["user_id"]
    atoms   = await get_user_atoms(session, user_id)
    if atom not in atoms:
        raise HTTPException(status_code=403, detail=f"Missing permission: {atom}")


def _get_manifest_or_404(table: str):
    manifest = get_manifest(table)
    if not manifest:
        raise HTTPException(
            status_code=404,
            detail=f"Table '{table}' is not registered for import/export. "
                   f"Available: {list(list_manifests())}",
        )
    return manifest


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/manifests")
async def get_manifests(
    tenant_id: str    = Depends(get_current_tenant),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    List all tables available for import/export.
    Filters to only those the current user has read access to.
    """
    user_atoms = await get_user_atoms(session, current_user["user_id"])
    return [
        m for m in list_manifests()
        if m["atom_read"] in user_atoms
    ]


@router.get("/{table}/template")
async def download_template(
    table: str,
    session: AsyncSession  = Depends(get_session),
    tenant_id: str         = Depends(get_current_tenant),
    current_user: dict     = Depends(get_current_user),
):
    """Download a blank XLSX template for the given table."""
    manifest = _get_manifest_or_404(table)
    await _check_atom(manifest.atom_read, session, current_user)

    sdo  = introspect_model(manifest.model)
    xlsx = build_template(
        sdo             = sdo,
        locked_fields   = manifest.locked_fields,
        excluded_fields = manifest.excluded_fields,
        fk_resolutions  = manifest.fk_resolutions,
        include_sample  = True,
        schema_version  = "1",
    )
    return _xlsx_response(xlsx, f"{table}-template-{date.today()}.xlsx")


@router.get("/{table}/export")
async def export_table(
    table: str,
    session: AsyncSession  = Depends(get_session),
    tenant_id: str         = Depends(get_current_tenant),
    current_user: dict     = Depends(get_current_user),
):
    """Export all tenant data for the given table as XLSX."""
    manifest = _get_manifest_or_404(table)
    await _check_atom(manifest.atom_read, session, current_user)

    sdo  = introspect_model(manifest.model)
    xlsx = await export_data(
        session         = session,
        tenant_id       = tenant_id,
        model_class     = manifest.model,
        sdo             = sdo,
        locked_fields   = manifest.locked_fields,
        excluded_fields = manifest.excluded_fields,
        fk_resolutions  = manifest.fk_resolutions,
        filters         = manifest.export_filters or None,
        schema_version  = "1",
    )
    return _xlsx_response(xlsx, f"{table}-export-{date.today()}.xlsx")


async def _run_import_pipeline(
    table: str,
    file: UploadFile,
    session: AsyncSession,
    tenant_id: str,
    current_user: dict,
    dry_run: bool,
) -> dict:
    """
    Shared pipeline for both preview and import endpoints.
    Returns a dict suitable for JSON response.
    """
    manifest = _get_manifest_or_404(table)
    await _check_atom(manifest.atom_write, session, current_user)

    # 1. Parse the uploaded file
    content  = await file.read()
    sdo      = introspect_model(manifest.model)
    known    = {c.name for c in sdo.columns}
    parse_result = parse_workbook(
        content,
        sheet_name   = sdo.table_name.replace("_", " ").title(),
        known_fields = known,
    )

    # Find the right sheet (exact match or first available)
    sheet_key = sdo.table_name.replace("_", " ").title()
    parsed_sheet = parse_result.sheets.get(sheet_key) or (
        next(iter(parse_result.sheets.values()), None)
    )
    if not parsed_sheet:
        raise HTTPException(status_code=422, detail="No readable sheet found in the uploaded file.")

    raw_rows = parsed_sheet.rows

    # Detect missing required columns
    file_cols    = set(parsed_sheet.headers)
    sdo_col_map  = {c.name: c for c in sdo.columns}
    visible_cols = {
        c.name for c in sdo.columns
        if c.name not in manifest.locked_fields
        and c.name not in manifest.excluded_fields
        and not c.primary_key
    }
    # Map FK display labels → actual column names for the missing-column check
    fk_label_map = {
        res.display_label.lower().replace(" ", "_"): fk_col
        for fk_col, res in manifest.fk_resolutions.items()
    }

    missing_required = []
    for col in sdo.columns:
        if (
            col.name in visible_cols
            and not col.nullable
            and col.default is None
            and col.name not in file_cols
            and fk_label_map.get(col.name) not in file_cols  # FK may appear as display label
        ):
            missing_required.append(col.name)

    # 2. Coerce all rows
    coerced_rows = [
        coerce_row(
            raw_row     = row,
            sdo_columns = {
                k: v for k, v in sdo_col_map.items()
                if k not in manifest.locked_fields
                and k not in manifest.excluded_fields
                and k not in manifest.fk_resolutions  # FK cols handled separately
            },
        )
        for row in raw_rows
    ]

    # 3. Validate
    report = validate_rows(
        coerced_rows           = coerced_rows,
        sdo                    = sdo,
        locked_fields          = manifest.locked_fields,
        excluded_fields        = manifest.excluded_fields,
        missing_required_columns = missing_required,
    )

    if not report.passed:
        return {
            "status":    "validation_failed",
            "dry_run":   dry_run,
            "warnings":  parse_result.warnings,
            **report.to_dict(),
        }

    # 4. FK resolution
    resolver = FKResolver(session, tenant_id)
    resolved_rows: list[dict] = []
    fk_errors: list[dict] = []

    for idx, (coerced, _) in enumerate(coerced_rows):
        resolved, errors = await resolver.resolve_row(coerced, manifest.fk_resolutions)
        if errors:
            for field_name, msg in errors:
                fk_errors.append({"row": idx + 1, "field": field_name, "message": msg})
        else:
            resolved_rows.append(resolved)

    if fk_errors:
        return {
            "status":   "fk_resolution_failed",
            "dry_run":  dry_run,
            "warnings": parse_result.warnings,
            "fk_errors": fk_errors,
        }

    # 5. Execute (or dry-run)
    exec_result = await execute_import(
        session         = session,
        tenant_id       = tenant_id,
        model_class     = manifest.model,
        resolved_rows   = resolved_rows,
        user_key        = manifest.user_key,
        locked_fields   = manifest.locked_fields,
        excluded_fields = manifest.excluded_fields,
        dry_run         = dry_run,
    )

    return {
        "status":   "preview_ok" if dry_run else "imported",
        "dry_run":  dry_run,
        "warnings": parse_result.warnings,
        **exec_result.to_dict(),
        **report.to_dict(),
    }


@router.post("/{table}/preview")
async def preview_import(
    table: str,
    file: UploadFile       = File(...),
    session: AsyncSession  = Depends(get_session),
    tenant_id: str         = Depends(get_current_tenant),
    current_user: dict     = Depends(get_current_user),
):
    """
    Validate an uploaded XLSX file without writing to the database.
    Returns a detailed validation report.
    """
    return await _run_import_pipeline(
        table, file, session, tenant_id, current_user, dry_run=True
    )


@router.post("/{table}/import")
async def import_table(
    table: str,
    file: UploadFile       = File(...),
    session: AsyncSession  = Depends(get_session),
    tenant_id: str         = Depends(get_current_tenant),
    current_user: dict     = Depends(get_current_user),
):
    """
    Validate and commit an uploaded XLSX file.
    The entire batch is rolled back if any row fails.
    """
    return await _run_import_pipeline(
        table, file, session, tenant_id, current_user, dry_run=False
    )
