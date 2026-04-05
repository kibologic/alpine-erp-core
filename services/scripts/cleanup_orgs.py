"""
Consolidate all product/inventory data into Kibologic Demo org,
then delete all other orgs and their orphaned users.

Usage:
  python3 scripts/cleanup_orgs.py --dry-run
  python3 scripts/cleanup_orgs.py --confirm

Must be run from the services/ directory:
  cd services && python3 scripts/cleanup_orgs.py --dry-run
"""

import asyncio
import os
import sys

import asyncpg

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEMO_ADMIN_USER = "00000000-0000-0000-0000-000000000002"

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://alpine:alpine_dev_2026@localhost:5432/alpine_erp",
).replace("postgresql+asyncpg://", "postgresql://")


# ── helpers ──────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    """Short slug for conflict suffixes."""
    return name.replace(" ", "")[:12]


async def gather_summary(conn) -> dict:
    other_tenants = await conn.fetch(
        "SELECT id, name FROM tenants WHERE id != $1 ORDER BY name",
        DEMO_TENANT_ID,
    )

    products_by_tenant = {}
    sku_conflicts = []
    total_categories = 0

    for t in other_tenants:
        tid, tname = str(t["id"]), t["name"]

        prods = await conn.fetch(
            "SELECT id, sku, name FROM products WHERE tenant_id = $1", tid
        )
        products_by_tenant[tid] = {"name": tname, "products": prods}

        cats = await conn.fetchval(
            "SELECT COUNT(*) FROM categories WHERE tenant_id = $1", tid
        )
        total_categories += cats

        for p in prods:
            exists = await conn.fetchval(
                "SELECT 1 FROM products WHERE tenant_id = $1 AND sku = $2",
                DEMO_TENANT_ID,
                p["sku"],
            )
            if exists:
                sku_conflicts.append((tname, p["sku"], p["name"]))

    users_to_delete = await conn.fetch(
        """
        SELECT u.id, u.email FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM user_tenants ut
            WHERE ut.user_id = u.id AND ut.tenant_id = $1
        )
        """,
        DEMO_TENANT_ID,
    )

    stock_movements = await conn.fetchval(
        "SELECT COUNT(*) FROM stock_movements WHERE tenant_id != $1",
        DEMO_TENANT_ID,
    )

    return {
        "other_tenants": other_tenants,
        "products_by_tenant": products_by_tenant,
        "total_categories": total_categories,
        "sku_conflicts": sku_conflicts,
        "users_to_delete": users_to_delete,
        "stock_movements": stock_movements,
    }


def print_summary(s: dict) -> None:
    print("\n" + "=" * 60)
    print("  CLEANUP SUMMARY")
    print("=" * 60)

    print(f"\nOrgs to delete ({len(s['other_tenants'])}):")
    for t in s["other_tenants"]:
        td = s["products_by_tenant"].get(str(t["id"]), {})
        n_prod = len(td.get("products", []))
        print(f"  • {t['name']:<30} {n_prod} products")

    total_products = sum(
        len(v["products"]) for v in s["products_by_tenant"].values()
    )
    print(f"\nData to migrate to Kibologic Demo:")
    print(f"  Categories  : {s['total_categories']}")
    print(f"  Products    : {total_products}")
    print(f"  Stock moves : {s['stock_movements']}")

    if s["sku_conflicts"]:
        print(f"\nSKU conflicts (will be renamed with org suffix):")
        for org, sku, name in s["sku_conflicts"]:
            print(f"  • [{org}] {sku} ({name})")
    else:
        print(f"\nNo SKU conflicts.")

    print(f"\nUsers to delete ({len(s['users_to_delete'])}):")
    for u in s["users_to_delete"]:
        print(f"  • {u['email']}")

    print("=" * 60)


# ── migration ─────────────────────────────────────────────────────────────────

async def migrate_categories(conn, tenant_id: str, tenant_name: str) -> None:
    """Reassign categories from other tenant to Demo. No unique constraint, just move."""
    result = await conn.execute(
        "UPDATE categories SET tenant_id = $1 WHERE tenant_id = $2",
        DEMO_TENANT_ID,
        tenant_id,
    )
    n = int(result.split()[-1])
    if n:
        print(f"    categories: moved {n}")


async def migrate_products(conn, tenant_id: str, tenant_name: str) -> None:
    """
    Reassign products from other tenant to Demo.
    Handle uq_product_tenant_sku: if SKU already exists in Demo, append org slug.
    """
    products = await conn.fetch(
        "SELECT id, sku FROM products WHERE tenant_id = $1", tenant_id
    )
    slug = _slug(tenant_name)
    renamed = 0

    for p in products:
        pid, sku = str(p["id"]), p["sku"]
        # Check if this SKU already exists in Demo
        exists = await conn.fetchval(
            "SELECT 1 FROM products WHERE tenant_id = $1 AND sku = $2",
            DEMO_TENANT_ID,
            sku,
        )
        if exists:
            new_sku = f"{sku}-{slug}"
            # Make sure the new SKU is also unique (iterate if needed)
            suffix_n = 1
            base_new = new_sku
            while await conn.fetchval(
                "SELECT 1 FROM products WHERE tenant_id = $1 AND sku = $2",
                DEMO_TENANT_ID,
                new_sku,
            ):
                new_sku = f"{base_new}-{suffix_n}"
                suffix_n += 1
            await conn.execute(
                "UPDATE products SET tenant_id = $1, sku = $2 WHERE id = $3",
                DEMO_TENANT_ID,
                new_sku,
                pid,
            )
            renamed += 1
        else:
            await conn.execute(
                "UPDATE products SET tenant_id = $1 WHERE id = $2",
                DEMO_TENANT_ID,
                pid,
            )

    if products:
        print(f"    products  : moved {len(products)}, renamed {renamed} SKUs")


async def migrate_stock_movements(conn, tenant_id: str) -> None:
    result = await conn.execute(
        "UPDATE stock_movements SET tenant_id = $1 WHERE tenant_id = $2",
        DEMO_TENANT_ID,
        tenant_id,
    )
    n = int(result.split()[-1])
    if n:
        print(f"    stock_mvmt: moved {n}")


# ── deletion ──────────────────────────────────────────────────────────────────

async def delete_other_tenants(conn, other_tenant_ids: list[str]) -> None:
    """
    Delete all other tenant data in safe dependency order.

    Must manually delete before tenant DELETE:
      1. join_requests      — tenant_id FK is NO ACTION (not CASCADE)
      2. password_reset_tokens — user_id FK is RESTRICT; users cascade from tenants
      3. custom_roles       — tenant_id FK is NO ACTION (not CASCADE)
         (role_atoms + org_invites CASCADE from custom_roles)

    CASCADE from tenants handles everything else:
      user_tenants, users, audit_log, cash_sessions → sales → sale_lines,
      payments, fiscal_submissions, tabs → tab_lines, kitchen_orders,
      terminal_configs, customers, products, categories, stock_movements.
    """
    placeholders = ", ".join(f"${i+1}" for i in range(len(other_tenant_ids)))

    # 1. join_requests: tenant_id is NO ACTION; user_id is RESTRICT
    r = await conn.execute(
        f"DELETE FROM join_requests WHERE tenant_id = ANY(ARRAY[{placeholders}]::uuid[])",
        *other_tenant_ids,
    )
    print(f"  join_requests deleted   : {r.split()[-1]}")

    # 2. password_reset_tokens: user_id RESTRICT; users are about to cascade-delete
    #    Delete tokens for users whose home tenant is being removed
    r = await conn.execute(
        f"""
        DELETE FROM password_reset_tokens
        WHERE user_id IN (
            SELECT id FROM users WHERE tenant_id = ANY(ARRAY[{placeholders}]::uuid[])
        )
        """,
        *other_tenant_ids,
    )
    print(f"  password_reset_tokens   : {r.split()[-1]}")

    # 3. custom_roles: tenant_id is NO ACTION; cascades role_atoms + org_invites
    r = await conn.execute(
        f"DELETE FROM custom_roles WHERE tenant_id = ANY(ARRAY[{placeholders}]::uuid[])",
        *other_tenant_ids,
    )
    print(f"  custom_roles deleted    : {r.split()[-1]}")

    # 4. Delete tenants — CASCADE handles the rest
    result = await conn.execute(
        f"DELETE FROM tenants WHERE id != '{DEMO_TENANT_ID}'"
    )
    n = int(result.split()[-1])
    print(f"  tenants deleted         : {n} (cascade removed sessions, sales, users, etc.)")


async def delete_orphaned_users(conn) -> int:
    """
    Delete users who have no user_tenants entry (not a member of any remaining org).
    These are users whose home tenant was Demo but who were never given membership,
    or leftover rows — cascade from tenants won't touch them since their tenant_id
    points to Demo (which we keep).
    """
    orphans = await conn.fetch(
        """
        SELECT u.id, u.email FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM user_tenants ut WHERE ut.user_id = u.id)
        """
    )
    if not orphans:
        print("  No orphaned users remaining.")
        return 0

    orphan_ids = [str(o["id"]) for o in orphans]

    # Clear RESTRICT FK blockers for these specific users
    await conn.execute(
        "DELETE FROM join_requests WHERE user_id = ANY($1::uuid[])", orphan_ids
    )
    await conn.execute(
        "DELETE FROM password_reset_tokens WHERE user_id = ANY($1::uuid[])", orphan_ids
    )

    result = await conn.execute(
        "DELETE FROM users WHERE NOT EXISTS (SELECT 1 FROM user_tenants ut WHERE ut.user_id = users.id)"
    )
    n = int(result.split()[-1])
    print(f"  Deleted {n} orphaned user(s):")
    for o in orphans:
        print(f"    • {o['email']}")
    return n


# ── main ─────────────────────────────────────────────────────────────────────

async def run(dry_run: bool) -> None:
    conn = await asyncpg.connect(DSN)
    try:
        summary = await gather_summary(conn)
        print_summary(summary)

        if dry_run:
            print("\n[DRY RUN] No changes made. Re-run with --confirm to execute.\n")
            return

        print("\nExecuting...\n")

        async with conn.transaction():
            # ── Phase 1: migrate inventory data ──────────────────────────────
            print("Phase 1 — Migrating inventory data to Kibologic Demo:")
            for tenant in summary["other_tenants"]:
                tid = str(tenant["id"])
                tname = tenant["name"]
                products = summary["products_by_tenant"].get(tid, {}).get("products", [])
                cats = await conn.fetchval(
                    "SELECT COUNT(*) FROM categories WHERE tenant_id = $1", tid
                )
                if cats == 0 and len(products) == 0:
                    continue
                print(f"\n  [{tname}]")
                await migrate_categories(conn, tid, tname)
                await migrate_products(conn, tid, tname)
                await migrate_stock_movements(conn, tid)

            # ── Phase 2: delete other tenants ─────────────────────────────────
            print("\nPhase 2 — Deleting other tenants:")
            other_ids = [str(t["id"]) for t in summary["other_tenants"]]
            await delete_other_tenants(conn, other_ids)

            # ── Phase 3: delete orphaned users (home=Demo, no membership) ─────
            print("\nPhase 3 — Deleting orphaned users (home=Demo, no membership):")
            await delete_orphaned_users(conn)

        print("\nDone. Transaction committed.\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--confirm" in args:
        asyncio.run(run(dry_run=False))
    elif "--dry-run" in args:
        asyncio.run(run(dry_run=True))
    else:
        print("Usage: python3 scripts/cleanup_orgs.py [--dry-run | --confirm]")
        sys.exit(1)
