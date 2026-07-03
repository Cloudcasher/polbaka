"""Pydantic-модели: контракты запросов и ответов API.

FastAPI по ним валидирует входящие данные (кривой JSON отобьётся сам)
и рисует документацию в Swagger.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FuelType(str, Enum):
    AI92 = "AI92"
    AI95 = "AI95"
    AI98 = "AI98"
    AI100 = "AI100"
    DT = "DT"
    GAS = "GAS"


class ReportStatus(str, Enum):
    available = "available"
    low = "low"
    queue = "queue"
    empty = "empty"


# ── Входящая отметка (шаблон: только строгие значения) ─────────────────────
class ReportIn(BaseModel):
    station_id: int
    fuel_type: FuelType
    status: ReportStatus
    queue_min: int | None = Field(None, ge=0, le=600, description="Очередь в минутах")
    limit_liters: int | None = Field(None, gt=0, le=1000, description="Лимит отпуска, л")
    comment: str | None = Field(None, max_length=500)


class ReportOut(BaseModel):
    id: int
    station_id: int
    fuel_type: FuelType
    status: ReportStatus
    created_at: datetime


# ── Статусы для карты ───────────────────────────────────────────────────────
class FuelStatusOut(BaseModel):
    status: ReportStatus
    confidence: float
    level: str                      # confirmed / single / stale
    age_min: int
    queue_min: int | None = None
    limit_liters: int | None = None


class StationOut(BaseModel):
    id: int
    name: str | None
    brand: str | None
    lat: float
    lon: float
    address: str | None
    city: str | None
    fuel_statuses: dict[str, FuelStatusOut] = {}   # ключ — марка топлива


class StationDetail(StationOut):
    region: str | None
    recent_reports: list[ReportOut] = []
