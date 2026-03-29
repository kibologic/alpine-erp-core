"""
Seed script for Alpine ERP — idempotent (ON CONFLICT DO NOTHING).
Uses asyncpg directly against postgresql+asyncpg://user:pass@host/dbname
"""

import asyncio
import uuid
import bcrypt
from datetime import datetime

import os

DSN = os.environ.get("DATABASE_URL")


def now_utc() -> datetime:
    return datetime.utcnow()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


async def seed():
    conn = await asyncpg.connect(DSN)
    try:
        # ── Tenant ────────────────────────────────────────────────────────────
        tenant_slug = "alpine-demo"
        existing_tenant = await conn.fetchrow(
            "SELECT id FROM tenants WHERE slug = $1", tenant_slug
        )
        if existing_tenant:
            tenant_id = existing_tenant["id"]
            print(f"[tenant] exists → {tenant_id}")
        else:
            tenant_id = new_id()
            await conn.execute(
                """
                INSERT INTO tenants (id, name, slug, tier, active, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT DO NOTHING
                """,
                tenant_id,
                "Alpine Hardware Demo",
                tenant_slug,
                "pro",
                True,
                now_utc(),
            )
            print(f"[tenant] created → {tenant_id}")

        # ── Users ─────────────────────────────────────────────────────────────
        users_data = [
            ("admin@alpine.demo",   "admin",   hash_password("admin123")),
            ("manager@alpine.demo", "manager", hash_password("manager123")),
            ("cashier@alpine.demo", "cashier", hash_password("cashier123")),
        ]
        user_ids = {}
        for email, role, pw_hash in users_data:
            existing = await conn.fetchrow(
                "SELECT id FROM users WHERE tenant_id = $1 AND email = $2",
                tenant_id, email,
            )
            if existing:
                user_ids[email] = existing["id"]
                print(f"[user] exists → {email}")
            else:
                uid = new_id()
                await conn.execute(
                    """
                    INSERT INTO users (id, tenant_id, email, password_hash, role, active, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT DO NOTHING
                    """,
                    uid, tenant_id, email, pw_hash, role, True, now_utc(),
                )
                user_ids[email] = uid
                print(f"[user] created → {email}")

        # ── Categories ────────────────────────────────────────────────────────
        category_names = [
            "Building Materials",
            "Plumbing",
            "Electrical",
            "Tools & Equipment",
            "Paint & Finishes",
            "Safety & PPE",
        ]
        category_ids = {}
        for cat_name in category_names:
            existing = await conn.fetchrow(
                "SELECT id FROM categories WHERE tenant_id = $1 AND name = $2",
                tenant_id, cat_name,
            )
            if existing:
                category_ids[cat_name] = existing["id"]
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
        print(f"[categories] seeded: {len(category_ids)}")

        # ── Suppliers ─────────────────────────────────────────────────────────
        suppliers_data = [
            ("Builders Warehouse Supply Co",  "orders@bwsupply.co",    "+265 111 000001"),
            ("East Africa Hardware Dist",      "sales@eahardware.co",   "+265 111 000002"),
            ("Malawi Building Materials Ltd",  "info@malbuild.co",      "+265 111 000003"),
            ("ProTools Africa",                "orders@protools.africa", "+265 111 000004"),
        ]
        for s_name, s_email, s_phone in suppliers_data:
            existing = await conn.fetchrow(
                "SELECT id FROM suppliers WHERE tenant_id = $1 AND name = $2",
                tenant_id, s_name,
            )
            if not existing:
                await conn.execute(
                    """
                    INSERT INTO suppliers
                        (id, tenant_id, name, email, phone, is_active, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT DO NOTHING
                    """,
                    new_id(), tenant_id, s_name, s_email, s_phone,
                    True, now_utc(), now_utc(),
                )
        print(f"[suppliers] seeded: {len(suppliers_data)}")

        # ── Products ──────────────────────────────────────────────────────────
        # (name, sku, price, cost, category_key)
        BM = "Building Materials"
        PL = "Plumbing"
        EL = "Electrical"
        TL = "Tools & Equipment"
        PT = "Paint & Finishes"
        SF = "Safety & PPE"

        products_data = [
            ("Cement 50kg",        "BM-001", 18500, 14000, BM),
            ("River Sand",         "BM-002",  3500,  2500, BM),
            ("Clay Bricks per 100","BM-003", 35000, 28000, BM),
            ("Roofing Sheet",      "BM-004", 12000,  9000, BM),
            ("Steel Rod 12mm",     "BM-005",  8500,  6500, BM),
            ("PVC Pipe 1/2 inch",  "PL-001",  4500,  3200, PL),
            ("Ball Valve",         "PL-002",  3200,  2100, PL),
            ("Elbow Fitting",      "PL-003",   850,   550, PL),
            ("Water Tank 1000L",   "PL-004", 85000, 65000, PL),
            ("Cable 2.5mm",        "EL-001",  1200,   850, EL),
            ("Circuit Breaker 20A","EL-002",  4500,  3100, EL),
            ("Socket Outlet",      "EL-003",  2800,  1900, EL),
            ("Hammer",             "TL-001",  6500,  4500, TL),
            ("Tape Measure 5m",    "TL-002",  3200,  2100, TL),
            ("Spirit Level 60cm",  "TL-003",  8500,  6000, TL),
            ("Crown Paint 4L",     "PT-001", 22000, 16000, PT),
            ("Paint Brush 4 inch", "PT-002",  2500,  1600, PT),
            ("Hard Hat",           "SF-001",  5500,  3800, SF),
            ("Safety Boots",       "SF-002", 18000, 13000, SF),
        ]

        product_ids = {}
        for p_name, sku, price, cost, cat_key in products_data:
            existing = await conn.fetchrow(
                "SELECT id FROM products WHERE tenant_id = $1 AND sku = $2",
                tenant_id, sku,
            )
            if existing:
                product_ids[sku] = existing["id"]
            else:
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
                    10.0, 16.5, True, now_utc(),
                )
                product_ids[sku] = pid
        print(f"[products] seeded: {len(product_ids)}")

        # ── Stock Movements ───────────────────────────────────────────────────
        admin_uid = user_ids.get("admin@alpine.demo")
        sm_count = 0
        for sku, pid in product_ids.items():
            existing = await conn.fetchrow(
                """
                SELECT id FROM stock_movements
                WHERE tenant_id = $1 AND product_id = $2 AND reason = 'initial_stock'
                """,
                tenant_id, pid,
            )
            if not existing:
                await conn.execute(
                    """
                    INSERT INTO stock_movements
                        (id, tenant_id, product_id, quantity, reason, created_by, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT DO NOTHING
                    """,
                    new_id(), tenant_id, pid, 50.0, "initial_stock",
                    admin_uid, now_utc(),
                )
                sm_count += 1
        print(f"[stock_movements] seeded: {sm_count} new (skipped existing)")

        # ── Customers ─────────────────────────────────────────────────────────
        customers_data = [
            ("Chisomo Banda",    "+265 999 100001", "chisomo@example.com"),
            ("Takondwa Phiri",   "+265 999 100002", "takondwa@example.com"),
            ("Mphatso Mwale",    "+265 999 100003", None),
            ("Kondwani Chirwa",  "+265 999 100004", None),
            ("Thandiwe Tembo",   "+265 999 100005", "thandiwe@example.com"),
            ("Grace Kumwenda",   "+265 999 100006", None),
        ]
        for c_name, c_phone, c_email in customers_data:
            existing = await conn.fetchrow(
                "SELECT id FROM customers WHERE tenant_id = $1 AND phone = $2",
                tenant_id, c_phone,
            )
            if not existing:
                await conn.execute(
                    """
                    INSERT INTO customers (id, tenant_id, name, phone, email, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT DO NOTHING
                    """,
                    new_id(), tenant_id, c_name, c_phone, c_email, now_utc(),
                )
        print(f"[customers] seeded: {len(customers_data)}")

        # ── Row counts ────────────────────────────────────────────────────────
        print("\n── Final row counts ──────────────────────────────────")
        tables = [
            "tenants", "users", "categories", "suppliers",
            "products", "stock_movements", "customers",
        ]
        for tbl in tables:
            row = await conn.fetchrow(f"SELECT COUNT(*) AS n FROM {tbl}")
            print(f"  {tbl:<22} {row['n']}")
        print("─────────────────────────────────────────────────────")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
