"""
Seed 3 test orgs for selling modes QA:
  1. ZAS Retail    — instant only   (zas@test.com / test123)
  2. Cousins Bar   — tabbed only    (cousins@test.com / test123)
  3. Chennai Spice — instant+tabbed (chennai@test.com / test123)

Idempotent — safe to re-run.
"""

import asyncio
import uuid
import json
import os
import sys

import asyncpg
import bcrypt
from datetime import datetime

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://alpine:alpine_dev_2026@localhost:5432/alpine_erp"
).replace("postgresql+asyncpg://", "postgresql://")


def now_utc() -> datetime:
    return datetime.utcnow()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


ORGS = [
    {
        "tenant_id": "00000000-0000-0000-0000-000000000002",
        "name": "ZAS Retail",
        "slug": "zas-retail",
        "email": "zas@test.com",
        "terminal_id": "ZAS-001",
        "terminal_name": "ZAS Main Register",
        "enabled_modes": ["instant"],
        "default_mode": "instant",
        "categories": ["Electronics", "Accessories", "Cables"],
        "products": [
            ("USB-C Cable 1m",     "ZAS-P001", 3500, 2200, "Cables"),
            ("HDMI Cable 2m",      "ZAS-P002", 5000, 3200, "Cables"),
            ("Phone Case",         "ZAS-P003", 4500, 2800, "Accessories"),
            ("Screen Protector",   "ZAS-P004", 2000, 1200, "Accessories"),
            ("Wireless Earbuds",   "ZAS-P005", 35000, 22000, "Electronics"),
            ("Power Bank 10000mAh","ZAS-P006", 25000, 16000, "Electronics"),
            ("USB Hub 4-Port",     "ZAS-P007", 8500, 5500, "Electronics"),
            ("Bluetooth Speaker",  "ZAS-P008", 45000, 30000, "Electronics"),
        ],
    },
    {
        "tenant_id": "00000000-0000-0000-0000-000000000003",
        "name": "Cousins Bar",
        "slug": "cousins-bar",
        "email": "cousins@test.com",
        "terminal_id": "BAR-001",
        "terminal_name": "Bar Main Terminal",
        "enabled_modes": ["tabbed"],
        "default_mode": "tabbed",
        "categories": ["Beers", "Spirits", "Cocktails", "Soft Drinks", "Food"],
        "products": [
            ("Carlsberg 500ml",    "BAR-P001",  2500,  1500, "Beers"),
            ("Guinness 500ml",     "BAR-P002",  3000,  1800, "Beers"),
            ("Kuche Kuche 330ml",  "BAR-P003",  1800,  1000, "Beers"),
            ("Coke 300ml",         "BAR-P004",   800,   450, "Soft Drinks"),
            ("Water 500ml",        "BAR-P005",   500,   250, "Soft Drinks"),
            ("Fanta Orange 300ml", "BAR-P006",   800,   450, "Soft Drinks"),
            ("Gin & Tonic",        "BAR-P007",  5500,  3000, "Cocktails"),
            ("Mojito",             "BAR-P008",  6000,  3200, "Cocktails"),
            ("Whiskey Shot",       "BAR-P009",  4500,  2500, "Spirits"),
            ("Chicken Wings x6",   "BAR-P010",  9000,  5000, "Food"),
            ("Chips & Dip",        "BAR-P011",  5500,  3000, "Food"),
            ("Loaded Nachos",      "BAR-P012", 12000,  7000, "Food"),
        ],
    },
    {
        "tenant_id": "00000000-0000-0000-0000-000000000004",
        "name": "Chennai Spice",
        "slug": "chennai-spice",
        "email": "chennai@test.com",
        "terminal_id": "REST-001",
        "terminal_name": "Chennai Front Desk",
        "enabled_modes": ["instant", "tabbed"],
        "default_mode": "tabbed",
        "categories": ["Starters", "Mains", "Breads", "Rice & Biryani", "Desserts", "Drinks"],
        "products": [
            ("Samosa x3",            "CHN-P001",  3500,  1800, "Starters"),
            ("Paneer Tikka",         "CHN-P002",  8500,  4500, "Starters"),
            ("Chicken 65",           "CHN-P003",  9500,  5200, "Starters"),
            ("Butter Chicken",       "CHN-P004", 14000,  8000, "Mains"),
            ("Palak Paneer",         "CHN-P005", 12000,  6500, "Mains"),
            ("Lamb Rogan Josh",      "CHN-P006", 16000,  9000, "Mains"),
            ("Dal Tadka",            "CHN-P007",  9000,  4800, "Mains"),
            ("Garlic Naan",          "CHN-P008",  2500,  1200, "Breads"),
            ("Paratha",              "CHN-P009",  2000,   950, "Breads"),
            ("Chicken Biryani",      "CHN-P010", 18000, 10000, "Rice & Biryani"),
            ("Veg Biryani",          "CHN-P011", 14000,  7500, "Rice & Biryani"),
            ("Mango Lassi",          "CHN-P012",  4500,  2200, "Drinks"),
            ("Masala Chai",          "CHN-P013",  2000,   900, "Drinks"),
            ("Gulab Jamun x2",       "CHN-P014",  4000,  2000, "Desserts"),
            ("Kulfi",                "CHN-P015",  3500,  1800, "Desserts"),
        ],
    },
]


async def seed_org(conn, org: dict):
    tenant_id = org["tenant_id"]
    email = org["email"]
    pw_hash = hash_password("test123")

    # ── Tenant ────────────────────────────────────────────────────────────────
    existing = await conn.fetchrow("SELECT id FROM tenants WHERE id = $1", tenant_id)
    if existing:
        print(f"  [tenant] exists → {org['name']}")
    else:
        await conn.execute(
            """
            INSERT INTO tenants (id, name, slug, tier, active, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            tenant_id, org["name"], org["slug"], "pro", True, now_utc(),
        )
        print(f"  [tenant] created → {org['name']}")

    # ── Admin user ────────────────────────────────────────────────────────────
    existing_user = await conn.fetchrow(
        "SELECT id FROM users WHERE email = $1 AND tenant_id = $2",
        email, tenant_id,
    )
    if existing_user:
        user_id = existing_user["id"]
        print(f"  [user]   exists → {email}")
    else:
        user_id = new_id()
        await conn.execute(
            """
            INSERT INTO users (id, tenant_id, email, password_hash, account_status, active, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT DO NOTHING
            """,
            user_id, tenant_id, email, pw_hash, "active", True, now_utc(),
        )
        print(f"  [user]   created → {email}")

    # ── user_tenants link ─────────────────────────────────────────────────────
    existing_link = await conn.fetchrow(
        "SELECT id FROM user_tenants WHERE user_id = $1 AND tenant_id = $2",
        user_id, tenant_id,
    )
    if not existing_link:
        await conn.execute(
            """
            INSERT INTO user_tenants (id, user_id, tenant_id, role, joined_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING
            """,
            new_id(), user_id, tenant_id, "admin", now_utc(),
        )

    # ── Categories ────────────────────────────────────────────────────────────
    category_ids = {}
    for cat_name in org["categories"]:
        existing_cat = await conn.fetchrow(
            "SELECT id FROM categories WHERE tenant_id = $1 AND name = $2",
            tenant_id, cat_name,
        )
        if existing_cat:
            category_ids[cat_name] = existing_cat["id"]
        else:
            cid = new_id()
            await conn.execute(
                """
                INSERT INTO categories (id, tenant_id, name, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
                """,
                cid, tenant_id, cat_name, now_utc(),
            )
            category_ids[cat_name] = cid
    print(f"  [cats]   {len(category_ids)} categories")

    # ── Products ──────────────────────────────────────────────────────────────
    product_count = 0
    for p_name, sku, price, cost, cat_key in org["products"]:
        existing_prod = await conn.fetchrow(
            "SELECT id FROM products WHERE tenant_id = $1 AND sku = $2",
            tenant_id, sku,
        )
        if not existing_prod:
            pid = new_id()
            await conn.execute(
                """
                INSERT INTO products
                    (id, tenant_id, category_id, name, sku, price, cost,
                     reorder_level, tax_rate, is_active, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT DO NOTHING
                """,
                pid, tenant_id, category_ids[cat_key],
                p_name, sku, price, cost,
                5.0, 16.5, True, now_utc(),
            )
            # Seed initial stock
            await conn.execute(
                """
                INSERT INTO stock_movements
                    (id, tenant_id, product_id, quantity, reason, created_by, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                new_id(), tenant_id, pid, 100.0, "initial_stock", user_id, now_utc(),
            )
            product_count += 1
    print(f"  [prods]  {product_count} new products + stock")

    # ── TerminalConfig ────────────────────────────────────────────────────────
    existing_tc = await conn.fetchrow(
        "SELECT id FROM terminal_configs WHERE tenant_id = $1 AND terminal_id = $2",
        tenant_id, org["terminal_id"],
    )
    if existing_tc:
        await conn.execute(
            """
            UPDATE terminal_configs
            SET enabled_modes = $1, default_mode = $2
            WHERE id = $3
            """,
            json.dumps(org["enabled_modes"]), org["default_mode"], existing_tc["id"],
        )
        print(f"  [term]   updated → {org['terminal_id']} modes={org['enabled_modes']}")
    else:
        await conn.execute(
            """
            INSERT INTO terminal_configs
                (id, tenant_id, terminal_id, name, enabled_modes, default_mode, config)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb)
            ON CONFLICT DO NOTHING
            """,
            new_id(), tenant_id, org["terminal_id"], org["terminal_name"],
            json.dumps(org["enabled_modes"]), org["default_mode"],
            json.dumps({}),
        )
        print(f"  [term]   created → {org['terminal_id']} modes={org['enabled_modes']}")


async def main():
    print(f"Connecting to: {DSN[:40]}...")
    conn = await asyncpg.connect(DSN)
    try:
        for org in ORGS:
            print(f"\n── {org['name']} ({'·'.join(org['enabled_modes'])}) ──────────────────")
            await seed_org(conn, org)

        print("\n── Verification ─────────────────────────────────────────")
        for org in ORGS:
            tc = await conn.fetchrow(
                "SELECT enabled_modes, default_mode FROM terminal_configs WHERE tenant_id = $1",
                org["tenant_id"],
            )
            prod_count = await conn.fetchrow(
                "SELECT COUNT(*) AS n FROM products WHERE tenant_id = $1",
                org["tenant_id"],
            )
            modes = json.loads(tc["enabled_modes"]) if tc else []
            print(f"  {org['name']:<16} modes={modes}  products={prod_count['n']}")

        print("\n── Done ──────────────────────────────────────────────────")
        print("Logins:")
        for org in ORGS:
            print(f"  {org['email']:<26} password=test123  terminal={org['terminal_id']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
