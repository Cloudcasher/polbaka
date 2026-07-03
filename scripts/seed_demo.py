"""Демо-данные для теста карты: реалистичные отметки всех видов.

Заполняет ~половину АЗС отметками разных сценариев: подтверждённые,
одиночные, с очередями, лимитами, пустые, протухшие. Все помечены
comment='demo' — удалить можно одной командой:

    DELETE FROM reports WHERE comment = 'demo';

Запуск:  .venv\\Scripts\\python.exe scripts\\seed_demo.py
"""

import asyncio
import os
import random
from datetime import datetime, timedelta, timezone

import asyncpg
from dotenv import load_dotenv

load_dotenv()

FUELS = ["AI92", "AI95", "AI98", "DT", "GAS"]
# Насколько часто марка вообще есть на заправке
FUEL_POPULARITY = {"AI92": 0.9, "AI95": 0.95, "AI98": 0.4, "DT": 0.7, "GAS": 0.15}

DEMO_USERS = 12  # виртуальные «водители» с репутацией 1.0


def minutes_ago(m: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=m)


def make_scenario() -> list[dict]:
    """Придумывает набор отметок для одной (АЗС, марки). Возвращает список отчётов."""
    roll = random.random()
    if roll < 0.30:
        # Подтверждённое наличие: 2-3 свежих отметки
        n = random.randint(2, 3)
        return [
            {"status": "available", "age": random.uniform(2, 30), "trusted": True}
            for _ in range(n)
        ]
    if roll < 0.50:
        # Одиночная отметка «есть»
        return [{"status": "available", "age": random.uniform(5, 45), "trusted": random.random() < 0.5}]
    if roll < 0.65:
        # Очередь (иногда с лимитом)
        rep = {
            "status": "queue",
            "age": random.uniform(5, 40),
            "trusted": True,
            "queue_min": random.choice([10, 15, 20, 30, 45, 60]),
        }
        if random.random() < 0.5:
            rep["limit_liters"] = random.choice([10, 20, 30])
        return [rep]
    if roll < 0.72:
        # Мало топлива, часто с лимитом
        return [{
            "status": "low",
            "age": random.uniform(5, 60),
            "trusted": True,
            "limit_liters": random.choice([10, 20]),
        }]
    if roll < 0.90:
        # Пусто (иногда подтверждено)
        n = random.randint(1, 2)
        return [
            {"status": "empty", "age": random.uniform(3, 50), "trusted": True}
            for _ in range(n)
        ]
    # Протухшая отметка (3-8 часов) — на карте станет серой
    return [{
        "status": random.choice(["available", "empty"]),
        "age": random.uniform(180, 480),
        "trusted": True,
    }]


async def main() -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # Виртуальные водители с репутацией 1.0 (для «подтверждённых» статусов)
        user_ids = []
        for _ in range(DEMO_USERS):
            uid = await conn.fetchval(
                """INSERT INTO users (tg_id, is_anonymous, reputation)
                   VALUES (NULL, false, 1.0) RETURNING id"""
            )
            user_ids.append(uid)

        station_ids = [r["id"] for r in await conn.fetch("SELECT id FROM stations")]

        rows = []
        covered = 0
        for sid in station_ids:
            if random.random() > 0.55:   # ~55% заправок получат отметки
                continue
            covered += 1
            for fuel in FUELS:
                if random.random() > FUEL_POPULARITY[fuel]:
                    continue
                for rep in make_scenario():
                    rows.append((
                        sid,
                        random.choice(user_ids) if rep["trusted"] else None,
                        fuel,
                        rep["status"],
                        rep.get("queue_min"),
                        rep.get("limit_liters"),
                        "demo",
                        minutes_ago(rep["age"]),
                    ))

        await conn.executemany(
            """
            INSERT INTO reports (station_id, user_id, fuel_type, status,
                                 queue_min, limit_liters, comment, source, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'web', $8)
            """,
            rows,
        )
        print(f"Готово: {len(rows)} демо-отметок на {covered} заправках.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
