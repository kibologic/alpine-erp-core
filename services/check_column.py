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
        res = await conn.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='products' AND column_name='reorder_level'"))
        row = res.fetchone()
        if row:
            print("reorder_level found")
        else:
            print("reorder_level NOT found")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
