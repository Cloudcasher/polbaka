"""ПолБака API — точка входа.

Запуск:  .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload
Swagger: http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import reports, stations

WEB_DIR = Path(__file__).parent.parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Аналог main() в боте: пул создаётся при старте, закрывается при остановке
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(
    title="ПолБака API",
    description="Краудсорсинговая карта наличия топлива: СПб + Ленобласть",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(stations.router)
app.include_router(reports.router)

# Карта: FastAPI раздаёт web/ как обычный сайт. Проверка маршрутов идёт
# по порядку, поэтому /stations и /reports работают, а всё остальное — статика.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
