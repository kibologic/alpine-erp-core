import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from os import environ

async def check():
    url = environ.get('DATABASE_URL')
    if not url:
        print("DATABASE_URL not set")
        return
    engine = create_async_engine(url)
    # Mapping to correct Kibologic tables
    tables = {
        'users': 'users',
        'products': 'products',
        'categories': 'categories',
        'suppliers': 'suppliers',
        'customers': 'customers',
        'cash_sessions': 'cash_sessions',
        'sales': 'sales',
        'stock_movements': 'stock_movements'
    }
    async with engine.connect() as conn:
        for key, table in tables.items():
            try:
                res = await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))
                count = res.scalar()
                print(f"{key}: {count}")
            except Exception as e:
                print(f"{key} ({table}): ERROR ({e})")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
