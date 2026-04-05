"""
datapipe.coerce — Type Coercion Engine
=======================================
Converts raw Excel cell values (typically strings or None) into
correctly-typed Python values based on ColumnDefinition metadata.

Returns CoercionError on failure — never raises.
No ERP knowledge. Pure type conversion logic.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from .introspect import ColumnDefinition, ColumnKind


# ─── Result Types ─────────────────────────────────────────────────────────────

@dataclass
class CoercionError:
    field: str
    raw_value: Any
    expected_kind: ColumnKind
    message: str


CoercionResult = tuple[Any, Optional[CoercionError]]
"""(coerced_value, error_or_None)"""


# ─── Coercion Helpers ─────────────────────────────────────────────────────────

def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("true", "yes", "1", "y"):
        return True
    if s in ("false", "no", "0", "n"):
        return False
    raise ValueError(f"Cannot interpret '{raw}' as boolean")


def _to_date(raw: Any) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    # Try common date formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date '{raw}'")


def _to_datetime(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime '{raw}'")


def _to_uuid(raw: Any) -> str:
    """Validate and normalise a UUID string."""
    s = str(raw).strip()
    uuid.UUID(s)   # raises ValueError if invalid
    return s


# ─── Public API ───────────────────────────────────────────────────────────────

def coerce_value(field_name: str, raw: Any, col_def: ColumnDefinition) -> CoercionResult:
    """
    Coerce a single raw cell value to the correct Python type.

    Returns (coerced, None) on success, (None, CoercionError) on failure.
    Handles None values: returns (None, None) if col is nullable.
    """
    # Empty / None handling
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if col_def.nullable or col_def.default is not None:
            return (None, None)
        return (None, CoercionError(
            field=field_name,
            raw_value=raw,
            expected_kind=col_def.kind,
            message="Field is required but was empty",
        ))

    try:
        kind = col_def.kind
        if kind == ColumnKind.TEXT:
            return (str(raw).strip(), None)
        if kind == ColumnKind.INTEGER:
            return (int(float(str(raw).strip())), None)
        if kind == ColumnKind.DECIMAL:
            return (float(str(raw).strip()), None)
        if kind == ColumnKind.BOOLEAN:
            return (_to_bool(raw), None)
        if kind == ColumnKind.DATE:
            return (_to_date(raw), None)
        if kind == ColumnKind.DATETIME:
            return (_to_datetime(raw), None)
        if kind == ColumnKind.UUID:
            return (_to_uuid(raw), None)
        if kind == ColumnKind.ENUM:
            val = str(raw).strip()
            if col_def.enum_values and val not in col_def.enum_values:
                return (None, CoercionError(
                    field=field_name,
                    raw_value=raw,
                    expected_kind=kind,
                    message=f"Invalid value '{val}'. Allowed: {col_def.enum_values}",
                ))
            return (val, None)
        if kind == ColumnKind.JSON:
            # JSON fields accept dict/list directly from openpyxl, or string
            if isinstance(raw, (dict, list)):
                return (raw, None)
            import json
            return (json.loads(str(raw)), None)
        # Fallback
        return (raw, None)

    except Exception as exc:
        return (None, CoercionError(
            field=field_name,
            raw_value=raw,
            expected_kind=col_def.kind,
            message=str(exc),
        ))


def coerce_row(
    raw_row: dict[str, Any],
    sdo_columns: dict[str, ColumnDefinition],
) -> tuple[dict[str, Any], list[CoercionError]]:
    """
    Coerce all fields in a row dict.

    Args:
        raw_row:     { field_name: raw_value, ... }
        sdo_columns: { field_name: ColumnDefinition, ... }

    Returns:
        (coerced_row, [errors])
    """
    coerced: dict[str, Any] = {}
    errors: list[CoercionError] = []

    for field_name, col_def in sdo_columns.items():
        raw = raw_row.get(field_name)
        value, error = coerce_value(field_name, raw, col_def)
        if error:
            errors.append(error)
        else:
            coerced[field_name] = value

    return coerced, errors
