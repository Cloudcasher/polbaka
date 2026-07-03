"""Импорт АЗС Санкт-Петербурга и Ленобласти из OpenStreetMap (Overpass API) в таблицу stations.

Запуск:  .venv\\Scripts\\python.exe scripts\\import_stations.py

Скрипт можно гонять повторно: заправки апсертятся по osm_id,
дубликатов не будет, обновятся название/бренд/адрес.
"""

import asyncio
import os

import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Импортируем агломерацию целиком: город + область (admin_level=4 у обоих субъектов)
REGIONS = ["Санкт-Петербург", "Ленинградская область"]

# Overpass QL: все объекты amenity=fuel в границах региона.
# out center — для ways/relations вернёт центр полигона вместо списка вершин.
OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:180];
area["name"="{region}"]["admin_level"="4"]->.a;
nwr["amenity"="fuel"](area.a);
out center tags;
"""

# Один и тот же бренд в OSM пишут по-разному — приводим к каноничному виду.
# («Газпром» не трогаем: это отдельная сеть газомоторного топлива, не Газпромнефть.)
BRAND_NORMALIZE = {
    "Газпром Нефть": "Газпромнефть",
    "ЛУКОЙЛ": "Лукойл",
    "ТАТНЕФТЬ": "Татнефть",
    "Tatneft": "Татнефть",
}

# Публичные зеркала Overpass; если первое лежит — пробуем следующее
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

UPSERT_SQL = """
INSERT INTO stations (osm_id, name, brand, lat, lon, geom, address, city, region)
VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($5, $4), 4326)::geography, $6, $7, $8)
ON CONFLICT (osm_id) DO UPDATE SET
    name    = EXCLUDED.name,
    brand   = EXCLUDED.brand,
    lat     = EXCLUDED.lat,
    lon     = EXCLUDED.lon,
    geom    = EXCLUDED.geom,
    address = EXCLUDED.address,
    city    = EXCLUDED.city,
    region  = EXCLUDED.region
"""


async def fetch_stations(region: str) -> list[dict]:
    query = OVERPASS_QUERY_TEMPLATE.format(region=region)
    last_error = None
    for url in OVERPASS_URLS:
        try:
            print(f"[{region}] запрашиваю Overpass: {url} ...")
            headers = {"User-Agent": "BenzRadar/0.1 (dev import script)"}
            async with httpx.AsyncClient(timeout=200, headers=headers) as client:
                resp = await client.post(url, data={"data": query})
                resp.raise_for_status()
                return resp.json()["elements"]
        except (httpx.HTTPError, KeyError) as e:
            print(f"  не вышло ({e!r}), пробую следующее зеркало")
            last_error = e
    raise RuntimeError(f"Все зеркала Overpass недоступны: {last_error!r}")


def build_address(tags: dict) -> str | None:
    street = tags.get("addr:street")
    house = tags.get("addr:housenumber")
    if street and house:
        return f"{street}, {house}"
    return street


def parse(elements: list[dict], region: str) -> list[tuple]:
    rows = []
    skipped = 0
    for el in elements:
        # У node координаты лежат сразу, у way/relation — в поле center
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            skipped += 1
            continue
        tags = el.get("tags", {})
        # У частников бренда в OSM нет — подтягиваем название точки
        brand = tags.get("brand") or tags.get("name")
        brand = BRAND_NORMALIZE.get(brand, brand)
        city = tags.get("addr:city") or (
            region if region == "Санкт-Петербург" else None
        )
        rows.append((
            el["id"],
            tags.get("name"),
            brand,
            lat,
            lon,
            build_address(tags),
            city,
            region,
        ))
    if skipped:
        print(f"[{region}] пропущено объектов без координат: {skipped}")
    return rows


async def main() -> None:
    rows = []
    for region in REGIONS:
        elements = await fetch_stations(region)
        region_rows = parse(elements, region)
        print(f"[{region}] получено: {len(region_rows)}")
        rows.extend(region_rows)

    print(f"Всего к загрузке: {len(rows)}")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.executemany(UPSERT_SQL, rows)
        total = await conn.fetchval("SELECT count(*) FROM stations")
        with_brand = await conn.fetchval(
            "SELECT count(*) FROM stations WHERE brand IS NOT NULL"
        )
    finally:
        await conn.close()

    print(f"Готово. Всего АЗС в базе: {total} (с брендом: {with_brand})")


if __name__ == "__main__":
    asyncio.run(main())
