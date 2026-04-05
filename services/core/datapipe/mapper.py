"""
datapipe.mapper — FK Resolution Layer
=======================================
Resolves human-readable foreign-key values to tenant-scoped UUIDs.

Example: category_id field in products where the user typed "Beverages"
→ map to the UUID of the Category with name="Beverages" in this tenant.

Tenant isolation is guaranteed: every lookup is scoped to tenant_id.
Caches lookups per mapper instance (one per import session).
No ERP knowledge about which FK maps to what — that lives in manifests.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


# ─── Config Types ─────────────────────────────────────────────────────────────

@dataclass
class FKResolution:
    """
    Declares how to resolve a FK column's human-readable value to a UUID.

    Example:
        FKResolution(
            model=Category,
            match_field="name",    # column in the FK table to match against
            display_label="Category Name",   # shown in template header
        )
    """
    model: Type[DeclarativeBase]
    match_field: str               # e.g. "name", "sku", "email"
    display_label: str             # used in template column header


# ─── Resolver ─────────────────────────────────────────────────────────────────

class FKResolver:
    """
    Stateful FK resolver for a single import session.
    Caches discovered mappings to avoid N+1 queries.
    Tenant-scoped. Cross-tenant references are rejected.
    """

    def __init__(self, session: AsyncSession, tenant_id: str):
        self._session   = session
        self._tenant_id = tenant_id
        self._cache: dict[str, dict[str, str]] = {}
        # Key: f"{table_name}.{match_field}" → { display_value: uuid }

    async def _load_lookup(
        self,
        model: Type[DeclarativeBase],
        match_field: str,
    ) -> dict[str, str]:
        """Load all tenant-scoped FK targets into cache."""
        cache_key = f"{model.__tablename__}.{match_field}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await self._session.execute(
            select(model).where(model.tenant_id == self._tenant_id)  # type: ignore[attr-defined]
        )
        rows = result.scalars().all()
        lookup = {
            str(getattr(r, match_field)): str(r.id)
            for r in rows
            if getattr(r, match_field, None) is not None
        }
        self._cache[cache_key] = lookup
        return lookup

    async def resolve(
        self,
        resolution: FKResolution,
        human_value: Any,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve a human-readable FK value to a tenant-scoped UUID.

        Returns:
            (uuid_str, None)         on success
            (None, error_message)    on failure
        """
        if human_value is None or str(human_value).strip() == "":
            return (None, None)   # Nullable FK — OK

        lookup = await self._load_lookup(resolution.model, resolution.match_field)
        val    = str(human_value).strip()

        if val in lookup:
            return (lookup[val], None)

        available = list(lookup.keys())[:10]
        hint = ", ".join(f'"{v}"' for v in available)
        return (None, (
            f"'{val}' not found in {resolution.model.__tablename__}. "
            f"Available (showing up to 10): {hint or 'none'}"
        ))

    async def resolve_row(
        self,
        row: dict[str, Any],
        resolutions: dict[str, FKResolution],
    ) -> tuple[dict[str, Any], list[tuple[str, str]]]:
        """
        Apply all FK resolutions to a row.

        Args:
            row:         Coerced row dict (field → value).
            resolutions: { fk_column_name: FKResolution }

        Returns:
            (resolved_row, [(field, error_message), ...])
        """
        errors: list[tuple[str, str]] = []
        resolved = dict(row)

        for fk_col, resolution in resolutions.items():
            # The row contains the human-readable display value under fk_col
            # (e.g. category_id contains "Beverages" before resolution)
            human_val = resolved.get(fk_col)
            uuid_val, err = await self.resolve(resolution, human_val)

            if err:
                errors.append((fk_col, err))
            else:
                resolved[fk_col] = uuid_val

        return resolved, errors
