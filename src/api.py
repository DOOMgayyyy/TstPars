from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
from config import DB_CONFIG

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешить все источники для разработки, в продакшене уточнить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)

@app.get("/search")
async def search_medicines(q: str = "", min_price: float = 0, max_price: float = None, category_id: int = None, limit: int = 20):
    conn = await get_db_connection()
    try:
        # Используем конкатенацию '||' для SQL-запроса
        sql = """
        SELECT m.id, m.name, m.description, m.image_url, 
               p.price, ph.name AS pharmacy_name
        FROM medicines m
        JOIN pharmacy_prices p ON m.id = p.medicine_id
        JOIN pharmacies ph ON p.pharmacy_id = ph.id
        WHERE LOWER(m.name) LIKE '%' || LOWER($1) || '%'
        """
        params = [q]
        
        if category_id:
            sql += " AND m.type_id = $" + str(len(params) + 1)
            params.append(category_id)
        
        if min_price > 0:
            sql += " AND p.price >= $" + str(len(params) + 1)
            params.append(min_price)
        
        if max_price:
            sql += " AND p.price <= $" + str(len(params) + 1)
            params.append(max_price)
        
        sql += " ORDER BY m.name LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        results = await conn.fetch(sql, *params)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@app.get("/medicine/{medicine_id}")
async def get_medicine_details(medicine_id: int):
    conn = await get_db_connection()
    try:
        # Основная информация о лекарстве
        medicine = await conn.fetchrow(
            "SELECT * FROM medicines WHERE id = $1", medicine_id
        )
        
        # Цены в аптеках
        prices = await conn.fetch(
            "SELECT p.price, p.last_updated, ph.name AS pharmacy_name "
            "FROM pharmacy_prices p "
            "JOIN pharmacies ph ON p.pharmacy_id = ph.id "
            "WHERE p.medicine_id = $1", medicine_id
        )
        
        return {
            "medicine": dict(medicine) if medicine else None,
            "prices": [dict(p) for p in prices]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@app.get("/categories")
async def get_categories():
    conn = await get_db_connection()
    try:
        sql = """
        SELECT id, name FROM medicine_types
        ORDER BY name;
        """
        results = await conn.fetch(sql)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@app.get("/autocomplete")
async def autocomplete(q: str = ""):
    conn = await get_db_connection()
    try:
        # То же самое исправление здесь
        sql = """
        SELECT m.id, m.name
        FROM medicines m
        WHERE LOWER(m.name) LIKE '%' || LOWER($1) || '%'
        ORDER BY m.name
        LIMIT 5;
        """
        # Важный момент: в вашем коде был LIKE '%' LOWER($1) '%', но параметр передавался без wildcards.
        # asyncpg не подставляет параметры прямо в строку, поэтому wildcards '%' должны быть частью SQL-запроса.
        # Второй параметр для fetch должен быть сам 'q'.
        results = await conn.fetch(sql, q) 
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()