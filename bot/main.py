"""ПолБака-бот — точка входа.

Запуск:  .venv\\Scripts\\python.exe -m bot.main
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from app import db

from . import notifier
from .handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def main() -> None:
    load_dotenv()
    bot = Bot(
        token=os.environ["BOT_TOKEN"],
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(router)

    await db.connect()
    notify_task = asyncio.create_task(notifier.run(bot))
    try:
        await dp.start_polling(bot)
    finally:
        notify_task.cancel()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
