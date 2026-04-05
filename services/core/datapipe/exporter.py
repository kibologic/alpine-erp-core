"""
datapipe.exporter — Data Export Engine
========================================
Exports live tenant data from the DB into XLSX format.
Uses the same builder as the template generator to guarantee round-trip consistency.

Export → Edit → Import = consistent cycle.
"""
from __future__ import annotations

from typing import Any, Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .builder import build_template
from .introspect import SchemaDefinitionObject
from .mapper import FKResolution


async def _resolve_fk_display_values(
    session: AsyncSession,
    tenant_id: str,
    rows: list[Any],
    sdo: SchemaDefinitionObject,
    fk_resolutions: dict[str, FKResolution],
) -> list[dict[str, Any]]:
    """
    Convert FK UUID columns back to human-readable values for export.
    This is the inverse of mapper.FKResolver — needed for round-trip export.
    """
    # Build reverse lookups: { table.col → { uuid: display_value } }
    reverse_lookups: dict[str, dict[str, str]] = {}

    for fk_col, resolution in fk_resolutions.items():
        cache_key = f"{resolution.model.__tablename__}.{resolution.match_field}"
        if cache_key not in reverse_lookups:
            result = await session.execute(
                select(resolution.model).where(
                    resolution.model.tenant_id == tenant_id  # type: ignore[attr-defined]
                )
            )
            fk_rows = result.scalars().all()
            reverse_lookups[cache_key] = {
                str(r.id): str(getattr(r, resolution.match_field))
                for r in fk_rows
            }

    serialized: list[dict[str, Any]] = []
    for row in rows:
        row_dict: dict[str, Any] = {}
        for col in sdo.columns:
            val = getattr(row, col.name, None)
            # FK reverse resolution
            resolution = fk_resolutions.get(col.name)
            if resolution and val is not None:
                cache_key = f"{resolution.model.__tablename__}.{resolution.match_field}"
                val = reverse_lookups.get(cache_key, {}).get(str(val), val)
            row_dict[col.name] = val
        serialized.append(row_dict)

    return serialized


async def export_data(
    session: AsyncSession,
    tenant_id: str,
    model_class: Type[DeclarativeBase],
    sdo: SchemaDefinitionObject,
    locked_fields: set[str],
    excluded_fields: set[str],
    fk_resolutions: dict[str, FKResolution],
    filters: Optional[dict[str, Any]] = None,
    schema_version: str = "1",
) -> bytes:
    """
    Export all tenant-scoped records for a model as XLSX.

    Args:
        session:          AsyncSession.
        tenant_id:        Tenant scope — all queries are scoped to this.
        model_class:      The SQLAlchemy ORM model.
        sdo:              Schema definition for this table.
        locked_fields:    System fields to mark as locked in the export.
        excluded_fields:  Fields to omit entirely from the export.
        fk_resolutions:   FK columns to display as human-readable values.
        filters:          Optional extra WHERE conditions { column: value }.
        schema_version:   Embedded in the file metadata for drift detection.

    Returns:
        XLSX file as bytes.
    """
    query = select(model_class).where(
        model_class.tenant_id == tenant_id  # type: ignore[attr-defined]
    )

    if filters:
        for col_name, val in filters.items():
            if hasattr(model_class, col_name):
                query = query.where(getattr(model_class, col_name) == val)

    result = await session.execute(query)
    rows   = result.scalars().all()

    # Resolve FK UUIDs → display values for export
    data_rows = await _resolve_fk_display_values(
        session, tenant_id, rows, sdo, fk_resolutions
    )

    return build_template(
        sdo             = sdo,
        locked_fields   = locked_fields,
        excluded_fields = excluded_fields,
        fk_resolutions  = fk_resolutions,
        data_rows       = data_rows,
        schema_version  = schema_version,
        include_sample  = False,
        show_locked     = True,
    )
