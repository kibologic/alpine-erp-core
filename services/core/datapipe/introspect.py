"""
datapipe.introspect — Schema Introspection Engine
==================================================
Reads any SQLAlchemy ORM model and produces a SchemaDefinitionObject (SDO).
No ERP knowledge. Pure SQLAlchemy reflection.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase


# ─── Column Type Classification ───────────────────────────────────────────────

class ColumnKind(str, enum.Enum):
    TEXT    = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE    = "date"
    DATETIME= "datetime"
    UUID    = "uuid"
    JSON    = "json"
    ENUM    = "enum"


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ColumnDefinition:
    name: str
    kind: ColumnKind
    nullable: bool
    primary_key: bool
    foreign_key_table: Optional[str]   # e.g. "categories"
    foreign_key_column: Optional[str]  # e.g. "id"
    enum_values: list[str]            # populated for ENUM columns
    default: Any                       # server or Python default, if known
    max_length: Optional[int]


@dataclass
class SchemaDefinitionObject:
    """
    Complete structural description of one ORM model.
    This is the currency passed between all datapipe layers.
    """
    table_name: str
    model_class: type
    columns: list[ColumnDefinition]

    # Derived helpers (built on construction)
    _by_name: dict[str, ColumnDefinition] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._by_name = {c.name: c for c in self.columns}

    def get(self, name: str) -> Optional[ColumnDefinition]:
        return self._by_name.get(name)

    @property
    def required_columns(self) -> list[ColumnDefinition]:
        return [c for c in self.columns if not c.nullable and not c.primary_key and c.default is None]

    @property
    def pk_columns(self) -> list[ColumnDefinition]:
        return [c for c in self.columns if c.primary_key]


# ─── Type Mapping ─────────────────────────────────────────────────────────────

def _classify_type(col_type) -> ColumnKind:
    """Map a SQLAlchemy column type to a ColumnKind."""
    type_name = type(col_type).__name__.upper()

    if "UUID" in type_name:
        return ColumnKind.UUID
    if "BOOL" in type_name:
        return ColumnKind.BOOLEAN
    if type_name in ("INTEGER", "BIGINTEGER", "SMALLINTEGER", "INT"):
        return ColumnKind.INTEGER
    if type_name in ("NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "DOUBLEPRECISION"):
        return ColumnKind.DECIMAL
    if "DATE" in type_name and "TIME" in type_name:
        return ColumnKind.DATETIME
    if type_name == "DATE":
        return ColumnKind.DATE
    if "ENUM" in type_name:
        return ColumnKind.ENUM
    if type_name in ("JSON", "JSONB"):
        return ColumnKind.JSON
    # Fallback — VARCHAR, TEXT, String, etc.
    return ColumnKind.TEXT


def _extract_default(col) -> Any:
    """Extract a sensible default value from a column if present."""
    if col.default is not None and col.default.is_scalar:
        return col.default.arg
    if col.server_default is not None:
        return "__server_default__"
    return None


def _extract_enum_values(col_type) -> list[str]:
    """Extract enum values if the column is an Enum type."""
    if hasattr(col_type, "enums"):
        return list(col_type.enums)
    return []


# ─── Public API ───────────────────────────────────────────────────────────────

def introspect_model(model_class: Type[DeclarativeBase]) -> SchemaDefinitionObject:
    """
    Introspect a SQLAlchemy ORM model class and return a SchemaDefinitionObject.

    Args:
        model_class: Any class derived from SQLAlchemy's declarative Base.

    Returns:
        SchemaDefinitionObject with full column metadata.

    Example:
        sdo = introspect_model(Product)
        for col in sdo.columns:
            print(col.name, col.kind, col.nullable)
    """
    mapper = sa_inspect(model_class)
    table  = mapper.persist_selectable
    cols: list[ColumnDefinition] = []

    for sa_col in table.columns:
        # FK resolution
        fk_table: Optional[str] = None
        fk_col:   Optional[str] = None
        if sa_col.foreign_keys:
            fk = next(iter(sa_col.foreign_keys))
            parts = fk.target_fullname.split(".")
            if len(parts) == 2:
                fk_table, fk_col = parts

        kind         = _classify_type(sa_col.type)
        enum_values  = _extract_enum_values(sa_col.type) if kind == ColumnKind.ENUM else []
        default      = _extract_default(sa_col)
        max_len      = getattr(sa_col.type, "length", None)

        cols.append(ColumnDefinition(
            name               = sa_col.name,
            kind               = kind,
            nullable           = sa_col.nullable,
            primary_key        = sa_col.primary_key,
            foreign_key_table  = fk_table,
            foreign_key_column = fk_col,
            enum_values        = enum_values,
            default            = default,
            max_length         = max_len,
        ))

    return SchemaDefinitionObject(
        table_name  = table.name,
        model_class = model_class,
        columns     = cols,
    )
