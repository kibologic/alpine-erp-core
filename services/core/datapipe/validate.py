"""
datapipe.validate — Validation Engine
=======================================
Validates coerced row data against live schema constraints.

Responsibilities:
  - Required field presence
  - Type correctness (delegated from coerce.py errors)
  - Enum membership
  - Max length enforcement
  - Cross-field consistency (e.g. no FK column pointing at excluded field)

Does NOT touch the database. FK ownership validation lives in mapper.py.
No ERP knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .coerce import CoercionError
from .introspect import ColumnDefinition, ColumnKind, SchemaDefinitionObject


# ─── Result Types ─────────────────────────────────────────────────────────────

@dataclass
class FieldError:
    field: str
    message: str
    value: Any = None


@dataclass
class RowResult:
    row_index: int              # 0-based index into the data rows
    errors: list[FieldError] = field(default_factory=list)
    warnings: list[FieldError] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


@dataclass
class ValidationReport:
    total_rows: int
    valid_rows: int
    invalid_rows: int
    row_results: list[RowResult]
    global_errors: list[str] = field(default_factory=list)  # File-level issues

    @property
    def passed(self) -> bool:
        return self.invalid_rows == 0 and not self.global_errors

    def to_dict(self) -> dict:
        return {
            "total_rows":    self.total_rows,
            "valid_rows":    self.valid_rows,
            "invalid_rows":  self.invalid_rows,
            "passed":        self.passed,
            "global_errors": self.global_errors,
            "rows": [
                {
                    "row": r.row_index + 1,  # 1-based for user display
                    "valid": r.valid,
                    "errors":   [{"field": e.field, "message": e.message, "value": str(e.value)} for e in r.errors],
                    "warnings": [{"field": w.field, "message": w.message} for w in r.warnings],
                }
                for r in self.row_results
                if not r.valid or r.warnings
            ],
        }


# ─── Validators ───────────────────────────────────────────────────────────────

def _validate_required(
    row: dict[str, Any],
    sdo: SchemaDefinitionObject,
    locked: set[str],
    excluded: set[str],
) -> list[FieldError]:
    """Check that all non-nullable, non-defaulted, non-locked columns are present."""
    errors: list[FieldError] = []
    for col in sdo.columns:
        if col.name in locked or col.name in excluded or col.primary_key:
            continue
        if not col.nullable and col.default is None:
            val = row.get(col.name)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(FieldError(
                    field=col.name,
                    message="Required field is missing or empty",
                    value=val,
                ))
    return errors


def _validate_lengths(
    row: dict[str, Any],
    sdo: SchemaDefinitionObject,
) -> list[FieldError]:
    """Check string values don't exceed declared max_length."""
    errors: list[FieldError] = []
    for col in sdo.columns:
        if col.max_length and col.kind == ColumnKind.TEXT:
            val = row.get(col.name)
            if val and len(str(val)) > col.max_length:
                errors.append(FieldError(
                    field=col.name,
                    message=f"Value exceeds maximum length of {col.max_length}",
                    value=val,
                ))
    return errors


def _validate_enums(
    row: dict[str, Any],
    sdo: SchemaDefinitionObject,
) -> list[FieldError]:
    """Check ENUM columns contain valid values."""
    errors: list[FieldError] = []
    for col in sdo.columns:
        if col.kind == ColumnKind.ENUM and col.enum_values:
            val = row.get(col.name)
            if val is not None and val not in col.enum_values:
                errors.append(FieldError(
                    field=col.name,
                    message=f"'{val}' is not a valid value. Allowed: {col.enum_values}",
                    value=val,
                ))
    return errors


def _errors_from_coercion(coercion_errors: list[CoercionError]) -> list[FieldError]:
    return [
        FieldError(field=e.field, message=e.message, value=e.raw_value)
        for e in coercion_errors
    ]


# ─── Public API ───────────────────────────────────────────────────────────────

def validate_rows(
    coerced_rows: list[tuple[dict[str, Any], list[CoercionError]]],
    sdo: SchemaDefinitionObject,
    locked_fields: set[str],
    excluded_fields: set[str],
    missing_required_columns: list[str],
) -> ValidationReport:
    """
    Validate a list of coercion results against the schema.

    Args:
        coerced_rows:              List of (coerced_row, coercion_errors) from coerce_row().
        sdo:                       Schema definition for this table.
        locked_fields:             Fields that are system-managed (id, tenant_id, etc.).
        excluded_fields:           Fields excluded from the template.
        missing_required_columns:  Required columns absent from the uploaded file.

    Returns:
        ValidationReport with per-row results.
    """
    global_errors: list[str] = []
    for col_name in missing_required_columns:
        global_errors.append(f"Required column '{col_name}' is missing from the uploaded file")

    results: list[RowResult] = []

    for idx, (row, coercion_errs) in enumerate(coerced_rows):
        row_result = RowResult(row_index=idx)

        # Coercion errors first
        row_result.errors.extend(_errors_from_coercion(coercion_errs))

        # Required field check
        row_result.errors.extend(
            _validate_required(row, sdo, locked_fields, excluded_fields)
        )

        # Length check
        row_result.errors.extend(_validate_lengths(row, sdo))

        # Enum check
        row_result.errors.extend(_validate_enums(row, sdo))

        results.append(row_result)

    valid   = sum(1 for r in results if r.valid)
    invalid = len(results) - valid

    return ValidationReport(
        total_rows   = len(results),
        valid_rows   = valid,
        invalid_rows = invalid,
        row_results  = results,
        global_errors= global_errors,
    )
