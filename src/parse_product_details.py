import asyncio
import os
import re
import json
from urllib.parse import urljoin

import asyncpg
import httpx
from bs4 import BeautifulSoup, Tag

from config import DB_CONFIG, URLS_DIR, CONCURRENCY_LIMIT

class ProductProcessor:
    def __init__(self, session: httpx.AsyncClient, db_pool: asyncpg.Pool):
        self.base_url = 'https://gosapteka18.ru'
        self.session = session
        self.db_pool = db_pool
        self.price_regexes = [
            re.compile(r'product-card__price-value[^>]*>([\d\s,]+)'),
            re.compile(r'"price"\s*:\s*"(\d+\.?\d*)"'),
            re.compile(r'itemprop="price"[^>]+content="(\d+\.?\d*)"')
        ]
        self.pharmacy_name = "Госаптека 18"  # можно вынести в config

    async def log_error(self, url: str, error: str):
        with open("error_log.txt", "a", encoding="utf-8") as log_file:
            log_file.write(f"Failed URL: {url}\nError: {error}\n\n")

    async def fetch_html(self, url: str) -> str | None:
        try:
            await asyncio.sleep(0.5)
            response = await self.session.get(url, timeout=20)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"🚫 Ошибка загрузки {url}: {e}")
            await self.log_error(url, f"Fetch error: {e}")
            return None

    def _get_title(self, soup: BeautifulSoup) -> str:
        try:
            tag = soup.select_one('h1.title.headline-main__title.product-card__title')
            return tag.get_text(strip=True) if tag else "Без названия"
        except Exception:
            return "Без названия"

    def _get_image(self, soup: BeautifulSoup) -> str:
        try:
            tag = soup.select_one('img.product-card__picture-view-img')
            if tag and 'src' in tag.attrs:
                return urljoin(self.base_url, tag['src'])
            return ""
        except Exception:
            return ""

    def _get_description(self, soup: BeautifulSoup) -> dict:
        try:
            block = soup.select_one('div.product-card__description')
            if not block:
                return {}
            sections = {}
            for header in block.find_all('h4'):
                header_text = header.get_text(strip=True)
                content = []
                for sibling in header.find_next_siblings():
                    if sibling.name == 'h4':
                        break
                    if isinstance(sibling, Tag):
                        content.append(sibling.get_text(" ", strip=True))
                sections[header_text] = " ".join(content)
            return sections
        except Exception:
            return {}

    def _get_price(self, html: str) -> float | None:
        for regex in self.price_regexes:
            if match := regex.search(html):
                try:
                    price_str = match.group(1).replace(' ', '').replace(',', '.')
                    return float(price_str)
                except (ValueError, TypeError):
                    continue
        return None

    async def get_pharmacy_id(self, pharmacy_name: str, pharmacy_url: str) -> int:
        async with self.db_pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO pharmacies (name, address)
                VALUES ($1, $2)
                ON CONFLICT (address) DO UPDATE
                SET name = EXCLUDED.name
                """,
                pharmacy_name, pharmacy_url
            )
            return await connection.fetchval(
                "SELECT id FROM pharmacies WHERE address = $1",
                pharmacy_url
            )


    async def save_to_db(self, data: dict) -> int:
        async with self.db_pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO medicine_types (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                    data['type_name']
                )
                type_id = await connection.fetchval(
                    "SELECT id FROM medicine_types WHERE name = $1",
                    data['type_name']
                )
                await connection.execute(
                    """
                    INSERT INTO medicines (name, description, image_url, type_id)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name) DO UPDATE SET
                        description = EXCLUDED.description,
                        image_url = EXCLUDED.image_url,
                        type_id = EXCLUDED.type_id;
                    """,
                    data['name'], data['description'], data['image_url'], type_id
                )
                return await connection.fetchval("SELECT id FROM medicines WHERE name = $1", data['name'])

    async def save_price(self, pharmacy_id: int, medicine_id: int, price: float):
        async with self.db_pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO pharmacy_prices (pharmacy_id, medicine_id, price, quantity)
                VALUES ($1, $2, $3, 0)
                ON CONFLICT (pharmacy_id, medicine_id) DO UPDATE SET
                    price = EXCLUDED.price,
                    last_updated = NOW();
                """,
                pharmacy_id, medicine_id, price
            )

    async def process_product(self, product_url: str, category_name: str):
        print(f"⏳ Собираем данные для: {product_url}")
        html = await self.fetch_html(product_url)
        if not html:
            return

        soup = BeautifulSoup(html, 'html.parser')

        title = self._get_title(soup)
        description_dict = self._get_description(soup) or {"Описание": "Нет данных"}
        description_text = "\n\n".join([f"{k}:\n{v}" for k, v in description_dict.items()])
        image_url = self._get_image(soup)
        price = self._get_price(html) or 0.0
        medicine_type_name = category_name or "Без категории"

        medicine_id = await self.save_to_db({
            'name': title,
            'description': description_text,
            'image_url': image_url,
            'type_name': medicine_type_name
        })

        pharmacy_id = await self.get_pharmacy_id(self.pharmacy_name, "https://gosapteka18.ru")

        await self.save_price(pharmacy_id, medicine_id, price)
        print(f"💾 Сохранено: {title} — {price} руб.")

async def main():
    if not os.path.exists(URLS_DIR):
        print(f"❌ Директория '{URLS_DIR}' не найдена.")
        return

    db_pool = await asyncpg.create_pool(**DB_CONFIG)
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def worker(url, processor, cat_name):
        async with semaphore:
            await processor.process_product(url, cat_name)

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as session:
        processor = ProductProcessor(session, db_pool)
        tasks = []
        for filename in os.listdir(URLS_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(URLS_DIR, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    category_name = data.get('category_name_slug', 'Без категории')
                    cleaned_urls = []
                    for url in data['product_urls']:
                        if '.html' in url:
                            clean_url = url.split('.html')[0] + '.html'
                            cleaned_urls.append(clean_url)
                        else:
                            cleaned_urls.append(url)
                    for url in cleaned_urls:
                        tasks.append(asyncio.create_task(worker(url, processor, category_name)))

        if not tasks:
            print("🤷 Не найдено URL для обработки.")
            await db_pool.close()
            return

        print(f"✅ Найдено {len(tasks)} задач для обработки.")
        await asyncio.gather(*tasks)

    await db_pool.close()
    print("\n\n🎉 Все товары обработаны и сохранены в базу данных!")

if __name__ == "__main__":
    asyncio.run(main())
