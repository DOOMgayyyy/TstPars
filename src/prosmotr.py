import asyncio
import asyncpg
from config import DB_CONFIG

async def show_prices():
    conn = await asyncpg.connect(**DB_CONFIG)

    rows = await conn.fetch("""
        SELECT
            m.id AS medicine_id,
            m.name AS medicine_name,
            p.price,
            ph.name AS pharmacy_name
        FROM pharmacy_prices p
        JOIN medicines m ON p.medicine_id = m.id
        JOIN pharmacies ph ON p.pharmacy_id = ph.id
        ORDER BY m.id
        LIMIT 20;
    """)

    print(f"{'ID':<5} | {'Название':<40} | {'Цена':<10} | {'Аптека'}")
    print("-" * 80)
    for row in rows:
        print(f"{row['medicine_id']:<5} | {row['medicine_name'][:40]:<40} | {row['price']:<10} | {row['pharmacy_name']}")

    await conn.close()

asyncio.run(show_prices())
