import asyncio
import os
import sys
sys.path.append(os.getcwd())
from core.db import engine
from sqlalchemy import text

async def check_data():
    if not engine:
        print("Engine not initialized.")
        return
    async with engine.connect() as conn:
        print("Checking tenant default settings...")
        try:
            result = await conn.execute(text("SELECT id, name, default_currency, default_locale FROM tenants LIMIT 1"))
            row = result.fetchone()
            if row:
                print(f"ID: {row[0]}")
                print(f"Name: {row[1]}")
                print(f"Currency: {row[2]}")
                print(f"Locale: {row[3]}")
            else:
                print("No tenants found.")
        except Exception as e:
            print(f"Error checking data: {e}")

if __name__ == "__main__":
    asyncio.run(check_data())
