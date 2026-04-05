"""
Backfill script: ensures every Super User (is_system=True) custom role has all 21 atoms.
Also fixes any user_tenants.role that was set to a UUID instead of 'admin'.

Run from services/ dir:
  cd services && python3 ../scripts/backfill_super_user_atoms.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/services")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    try:
        env_path = os.path.join(os.path.dirname(__file__), "../services/.env")
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL"):
                    DATABASE_URL = line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


async def run():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import core.models  # noqa: registers models
    from core.models import RoleAtom
    from core.atoms import SUPER_USER_ATOMS

    async with async_session() as session:
        # Step 1: Seed atoms for roles that have 0 atoms
        result = await session.execute(text("""
            SELECT cr.id::text, cr.name, cr.tenant_id::text
            FROM custom_roles cr
            WHERE cr.is_system = true
            AND NOT EXISTS (SELECT 1 FROM role_atoms ra WHERE ra.role_id = cr.id)
        """))
        zero_atom_roles = result.fetchall()
        print(f"Roles with 0 atoms: {len(zero_atom_roles)}")
        for role_id, role_name, tenant_id in zero_atom_roles:
            print(f"  Seeding {len(SUPER_USER_ATOMS)} atoms for role {role_id} ({role_name})")
            for atom in SUPER_USER_ATOMS:
                session.add(RoleAtom(role_id=role_id, atom=atom))
            # Fix UserTenant.role UUID -> 'admin'
            await session.execute(
                text("UPDATE user_tenants SET role = :r WHERE tenant_id = :tid AND role = :old"),
                {"r": "admin", "tid": tenant_id, "old": role_id},
            )

        # Step 2: Top up roles that have some atoms but not all 21
        result2 = await session.execute(text("""
            SELECT cr.id::text, array_agg(ra.atom) as existing_atoms
            FROM custom_roles cr
            LEFT JOIN role_atoms ra ON ra.role_id = cr.id
            WHERE cr.is_system = true
            GROUP BY cr.id
            HAVING COUNT(ra.id) > 0 AND COUNT(ra.id) < :total
        """), {"total": len(SUPER_USER_ATOMS)})
        incomplete = result2.fetchall()
        print(f"Roles with incomplete atoms: {len(incomplete)}")
        for role_id, existing_atoms in incomplete:
            missing = [a for a in SUPER_USER_ATOMS if a not in existing_atoms]
            print(f"  Adding {len(missing)} missing atoms to role {role_id}: {missing}")
            for atom in missing:
                session.add(RoleAtom(role_id=role_id, atom=atom))

        await session.commit()

        # Final verification
        result3 = await session.execute(text("""
            SELECT cr.id::text, COUNT(ra.id) as atom_count
            FROM custom_roles cr
            LEFT JOIN role_atoms ra ON ra.role_id = cr.id
            WHERE cr.is_system = true
            GROUP BY cr.id
            ORDER BY cr.created_at DESC
        """))
        rows = result3.fetchall()
        print("\n=== DB VERIFICATION ===")
        all_ok = True
        for r in rows:
            ok = r[1] == len(SUPER_USER_ATOMS)
            if not ok:
                all_ok = False
            print(f"  {'OK' if ok else 'FAIL'} role_id={r[0]} atom_count={r[1]}")
        print(f"\nAll Super User roles have {len(SUPER_USER_ATOMS)} atoms: {all_ok}")
        return all_ok


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
