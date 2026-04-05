"""
dataimport.manifests — The ONLY place with ERP business knowledge
=================================================================
Declares which tables are importable/exportable, what permissions
are required, and how FK columns resolve to human-readable values.

Adding a new importable table = adding one ImportManifest entry here.
Zero engine changes needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Type

from sqlalchemy.orm import DeclarativeBase

from core.datapipe.mapper import FKResolution
from core.models import Category, Customer, Product, Supplier


# ─── Manifest Definition ──────────────────────────────────────────────────────

@dataclass
class ImportManifest:
    """
    Describes one importable/exportable table from the ERP perspective.
    """
    model: Type[DeclarativeBase]   # SQLAlchemy model
    label: str                      # Human label shown in UI ("Products")
    description: str                # Short description for UI display
    atom_read:  str                 # Permission atom to read/export
    atom_write: str                 # Permission atom to import/write
    user_key:   str                 # Column to match on for upsert ("sku", "name")

    # FK columns the user sees as readable strings: { fk_col: FKResolution }
    fk_resolutions: dict[str, FKResolution] = field(default_factory=dict)

    # Fields hidden entirely from the template (too technical, auto-managed)
    excluded_fields: set[str] = field(default_factory=set)

    # Fields shown (grey, protected) but not editable
    locked_fields: set[str] = field(default_factory=lambda: {"id", "tenant_id", "created_at"})

    # Optional: extra WHERE clause for export (e.g. is_active=True)
    export_filters: dict = field(default_factory=dict)


# ─── Manifest Registry ────────────────────────────────────────────────────────

MANIFESTS: dict[str, ImportManifest] = {

    "products": ImportManifest(
        model       = Product,
        label       = "Products",
        description = "Import or export product catalogue including pricing, cost, and SKU.",
        atom_read   = "inventory.view",
        atom_write  = "inventory.manage",
        user_key    = "sku",
        fk_resolutions = {
            "category_id": FKResolution(
                model         = Category,
                match_field   = "name",
                display_label = "Category Name",
            ),
        },
        excluded_fields = {
            "extra_data",
            "fiscal_codes",
            "canonical_material_id",
            "unspsc_code",
            "quality_tier",
        },
        locked_fields = {"id", "tenant_id", "created_at"},
        export_filters = {"is_active": True},
    ),

    "categories": ImportManifest(
        model       = Category,
        label       = "Categories",
        description = "Import or export product categories.",
        atom_read   = "inventory.view",
        atom_write  = "inventory.manage",
        user_key    = "name",
        locked_fields = {"id", "tenant_id", "created_at"},
    ),

    "suppliers": ImportManifest(
        model       = Supplier,
        label       = "Suppliers",
        description = "Import or export supplier contact information.",
        atom_read   = "inventory.view",
        atom_write  = "inventory.manage",
        user_key    = "name",
        locked_fields = {"id", "tenant_id", "created_at", "updated_at"},
        export_filters = {"is_active": True},
    ),

    "customers": ImportManifest(
        model       = Customer,
        label       = "Customers",
        description = "Import or export customer records.",
        atom_read   = "inventory.view",
        atom_write  = "inventory.manage",
        user_key    = "email",
        locked_fields = {"id", "tenant_id", "created_at"},
    ),
}


def get_manifest(table: str) -> Optional[ImportManifest]:
    """Retrieve a manifest by table name. Returns None if not registered."""
    return MANIFESTS.get(table)


def list_manifests() -> list[dict]:
    """Return a serializable summary of all registered manifests."""
    return [
        {
            "table":       key,
            "label":       m.label,
            "description": m.description,
            "user_key":    m.user_key,
            "atom_read":   m.atom_read,
            "atom_write":  m.atom_write,
        }
        for key, m in MANIFESTS.items()
    ]
