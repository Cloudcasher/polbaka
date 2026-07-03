"""SQL-запросы бота. Пул соединений — общий с API (app/db.py)."""

from app import db


async def upsert_tg_user(tg_id: int) -> int:
    """Регистрирует юзера Телеги (или возвращает существующего). Репутация 1.0 — не аноним."""
    pool = db.get_pool()
    return await pool.fetchval(
        """
        INSERT INTO users (tg_id, is_anonymous, reputation)
        VALUES ($1, false, 1.0)
        ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id
        RETURNING id
        """,
        tg_id,
    )


async def nearest_stations(lat: float, lon: float, limit: int = 5) -> list:
    """Ближайшие АЗС к точке — тот самый PostGIS-запрос «что рядом»."""
    pool = db.get_pool()
    return await pool.fetch(
        """
        SELECT id, name, brand, address,
               ST_Distance(geom, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) AS dist_m
        FROM stations
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
        LIMIT $3
        """,
        lat, lon, limit,
    )


async def station_by_id(station_id: int):
    pool = db.get_pool()
    return await pool.fetchrow(
        "SELECT id, name, brand, address, city FROM stations WHERE id = $1", station_id
    )


async def insert_report(station_id: int, user_id: int, fuel: str, status: str) -> None:
    pool = db.get_pool()
    await pool.execute(
        """
        INSERT INTO reports (station_id, user_id, fuel_type, status, source)
        VALUES ($1, $2, $3, $4, 'bot')
        """,
        station_id, user_id, fuel, status,
    )


async def add_subscription(user_id: int, station_id: int, fuel: str) -> bool:
    """True — подписка создана, False — уже была."""
    pool = db.get_pool()
    result = await pool.execute(
        """
        INSERT INTO subscriptions (user_id, station_id, fuel_type)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        user_id, station_id, fuel,
    )
    return result.endswith("1")


async def list_subscriptions(user_id: int) -> list:
    pool = db.get_pool()
    return await pool.fetch(
        """
        SELECT sub.id, sub.fuel_type::text AS fuel_type, st.name, st.brand, st.address, st.id AS station_id
        FROM subscriptions sub
        JOIN stations st ON st.id = sub.station_id
        WHERE sub.user_id = $1
        ORDER BY sub.created_at
        """,
        user_id,
    )


async def delete_subscription(sub_id: int, user_id: int) -> None:
    pool = db.get_pool()
    await pool.execute(
        "DELETE FROM subscriptions WHERE id = $1 AND user_id = $2", sub_id, user_id
    )


async def subscribers_for(station_id: int, fuel: str) -> list[int]:
    """tg_id всех, кто ждёт это топливо на этой АЗС."""
    pool = db.get_pool()
    rows = await pool.fetch(
        """
        SELECT u.tg_id
        FROM subscriptions s
        JOIN users u ON u.id = s.user_id
        WHERE s.station_id = $1 AND s.fuel_type = $2 AND u.tg_id IS NOT NULL
        """,
        station_id, fuel,
    )
    return [r["tg_id"] for r in rows]
