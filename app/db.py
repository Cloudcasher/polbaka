"""Пул соединений с PostgreSQL.

Тот же asyncpg, что и в боте: пул создаётся один раз при старте приложения,
хэндлеры берут из него соединения. Создавать соединение на каждый запрос — дорого.
"""

import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

pool: asyncpg.Pool | None = None


async def connect() -> None:
    global pool
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=10)


async def disconnect() -> None:
    if pool is not None:
        await pool.close()


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "Пул не создан — приложение ещё не стартовало"
    return pool
