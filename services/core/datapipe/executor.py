"""
datapipe.executor — Safe Transactional Write Layer
====================================================
Executes validated, FK-resolved rows against the database.

Rules:
  - ALWAYS injects tenant_id
  - ALWAYS runs inside a transaction
  - Rolls back the ENTIRE batch on any error
  - Upserts: inserts new, updates existing (matched by user_key)
  - Never writes a row that came back invalid from validation

No ERP knowledge. Driven entirely by the SQLAlchemy model class and user_key.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


# ─── Result Types ─────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    inserted: int = 0
    updated:  int = 0
    skipped:  int = 0
    errors:   list[tuple[int, str]] = field(default_factory=list)  # (row_idx, message)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "inserted": self.inserted,
            "updated":  self.updated,
            "skipped":  self.skipped,
            "errors":   [{"row": r + 1, "message": m} for r, m in self.errors],
        }


# ─── Public API ───────────────────────────────────────────────────────────────

async def execute_import(
    session: AsyncSession,
    tenant_id: str,
    model_class: Type[DeclarativeBase],
    resolved_rows: list[dict[str, Any]],
    user_key: str,
    locked_fields: set[str],
    excluded_fields: set[str],
    dry_run: bool = False,
) -> ExecutionResult:
    """
    Upsert resolved_rows into the database inside a single transaction.

    If any row fails, the ENTIRE batch is rolled back.

    Args:
        session:        AsyncSession — caller must manage the session lifecycle.
        tenant_id:      Current tenant — injected into every row.
        model_class:    The SQLAlchemy ORM model to write to.
        resolved_rows:  List of fully resolved row dicts.
        user_key:       Column used to detect existing records (e.g. "sku").
        locked_fields:  System fields to never overwrite from import data.
        excluded_fields:Fields to exclude from write set.
        dry_run:        If True, validate only — no DB writes, then rollback.

    Returns:
        ExecutionResult with counts of inserts/updates and any errors.
    """
    result = ExecutionResult()
    always_locked = {"id", "tenant_id", "created_at"} | locked_fields

    try:
        for idx, row in enumerate(resolved_rows):
            # Enforce tenant_id regardless of what was in the file
            row["tenant_id"] = tenant_id

            # Sanitize: remove locked / excluded / unknown fields
            write_data = {
                k: v for k, v in row.items()
                if k not in always_locked and k not in excluded_fields
            }

            # Look for existing row by user_key + tenant_id
            user_key_val = row.get(user_key)
            existing = None

            if user_key_val is not None:
                lookup_result = await session.execute(
                    select(model_class).where(
                        getattr(model_class, "tenant_id") == tenant_id,
                        getattr(model_class, user_key) == str(user_key_val),
                    )
                )
                existing = lookup_result.scalar_one_or_none()

            if existing:
                # UPDATE
                for k, v in write_data.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                result.updated += 1
            else:
                # INSERT
                new_id = str(uuid.uuid4())
                instance = model_class(
                    id=new_id,
                    tenant_id=tenant_id,
                    **{k: v for k, v in write_data.items() if hasattr(model_class, k)},
                )
                session.add(instance)
                result.inserted += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    except Exception as exc:
        await session.rollback()
        result.errors.append((-1, f"Transaction failed and was rolled back: {exc}"))

    return result
