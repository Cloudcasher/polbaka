"""Пуш-уведомления: слушаем сигнал new_report из Postgres и оповещаем подписчиков.

Механика: триггер в базе (db/notify_trigger.sql) шлёт NOTIFY при каждой новой
отметке — хоть с сайта, хоть из бота. Мы держим отдельное соединение с LISTEN
и реагируем мгновенно, без опроса базы по таймеру.
"""

import asyncio
import json
import logging
import os
import time

import asyncpg
from aiogram import Bot

from . import queries as q
from .texts import FUEL_LABELS, station_title

log = logging.getLogger("notifier")

# Не дёргаем одного человека по одной АЗС чаще, чем раз в час
COOLDOWN_SEC = 3600
_last_sent: dict[tuple[int, int, str], float] = {}


async def _on_new_report(bot: Bot, payload: str) -> None:
    data = json.loads(payload)
    if data["status"] != "available":
        return  # уведомляем только о ПОЯВЛЕНИИ топлива

    station_id, fuel = data["station_id"], data["fuel_type"]
    tg_ids = await q.subscribers_for(station_id, fuel)
    if not tg_ids:
        return

    st = await q.station_by_id(station_id)
    text = (
        f"⛽ Появился <b>{FUEL_LABELS.get(fuel, fuel)}</b>!\n"
        f"«{station_title(st)}»\n\n"
        f"Только что отметил водитель. Поторопись — и подтверди отметку, когда приедешь 😉"
    )

    now = time.monotonic()
    for tg_id in tg_ids:
        key = (tg_id, station_id, fuel)
        if now - _last_sent.get(key, 0) < COOLDOWN_SEC:
            continue
        try:
            await bot.send_message(tg_id, text)
            _last_sent[key] = now
        except Exception as e:  # юзер заблокировал бота и т.п. — не роняем рассылку
            log.warning("Не доставлено tg_id=%s: %r", tg_id, e)


async def run(bot: Bot) -> None:
    """Держит LISTEN-соединение живым; переподключается при обрыве."""
    while True:
        try:
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            queue: asyncio.Queue[str] = asyncio.Queue()

            def listener(_conn, _pid, _channel, payload):
                queue.put_nowait(payload)

            await conn.add_listener("new_report", listener)
            log.info("Слушаю new_report...")
            while True:
                payload = await queue.get()
                await _on_new_report(bot, payload)
        except (asyncpg.PostgresError, OSError) as e:
            log.warning("LISTEN-соединение упало (%r), переподключаюсь через 5 с", e)
            await asyncio.sleep(5)
