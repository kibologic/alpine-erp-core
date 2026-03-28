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
    async with engine.connect() as conn:
        res = await conn.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [r[0] for r in res.fetchall()]
        print(f"Tables found: {tables}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
