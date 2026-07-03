"""Умное ядро ПолБака: превращает сырые отметки в статус, которому можно верить.

Каждая отметка имеет вес:  вес = freshness(возраст) × reputation(автор)

- freshness — экспоненциальное затухание: отметка "стареет" и теряет вес.
  При TAU=60 мин: 5 минут назад ≈ 0.92, час назад ≈ 0.37, 3 часа ≈ 0.05.
- reputation — доверие автору: аноним 0.3, залогиненный от 1.0 (растёт/падает).

Статус заправки = статус с максимальной суммой весов среди свежих отметок.
Уверенность (confidence) = эта сумма. Порог CONFIRMED — «двойное подтверждение»:
примерно две свежие отметки залогиненных или несколько анонимных.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

TAU_MINUTES = 60.0        # характерное время затухания свежести
ANON_REPUTATION = 0.3     # вес анонима (см. ROADMAP, гибридная модель)
MAX_REPORT_AGE_HOURS = 24 # отметки старше суток не учитываем вовсе

# Пороги уверенности для уровней доверия
CONFIRMED_THRESHOLD = 1.5   # «подтверждено» — двойное подтверждение
SINGLE_THRESHOLD = 0.25     # «одиночная отметка» — уже что-то, но верить осторожно


@dataclass
class RawReport:
    """Одна отметка, как она пришла из БД."""
    status: str                 # available / low / queue / empty
    created_at: datetime
    reputation: float | None    # None — аноним без записи в users
    queue_min: int | None = None
    limit_liters: int | None = None


@dataclass
class FuelStatus:
    """Агрегированный статус по одной марке топлива на одной АЗС."""
    status: str
    confidence: float           # сумма весов победившего статуса
    level: str                  # confirmed / single / stale
    age_min: int                # возраст самой свежей отметки, минут
    queue_min: int | None       # очередь из самой свежей отметки
    limit_liters: int | None    # лимит отпуска из самой свежей отметки


def freshness(age_minutes: float) -> float:
    """Вес свежести: 1.0 у только что созданной отметки, ~0 у старой."""
    return math.exp(-age_minutes / TAU_MINUTES)


def report_weight(report: RawReport, now: datetime) -> float:
    age_min = (now - report.created_at).total_seconds() / 60
    reputation = report.reputation if report.reputation is not None else ANON_REPUTATION
    return freshness(age_min) * reputation


def aggregate(reports: list[RawReport], now: datetime | None = None) -> FuelStatus | None:
    """Сводит список отметок по одной (АЗС, марке) в итоговый статус.

    Возвращает None, если отметок нет — на карте такая АЗС будет серой «нет данных».
    """
    if not reports:
        return None
    now = now or datetime.now(timezone.utc)

    # Сумма весов по каждому статусу: у какого больше — тот и победил
    weights: dict[str, float] = {}
    for r in reports:
        weights[r.status] = weights.get(r.status, 0.0) + report_weight(r, now)
    status = max(weights, key=lambda s: weights[s])
    confidence = weights[status]

    by_recency = sorted(reports, key=lambda r: r.created_at, reverse=True)
    newest = by_recency[0]
    age_min = int((now - newest.created_at).total_seconds() / 60)

    # Очередь и лимит — последние ИЗВЕСТНЫЕ значения: если свежая отметка
    # их не указала, не затираем пустотой то, что сообщили раньше
    queue_min = next((r.queue_min for r in by_recency if r.queue_min is not None), None)
    limit_liters = next(
        (r.limit_liters for r in by_recency if r.limit_liters is not None), None
    )

    if confidence >= CONFIRMED_THRESHOLD:
        level = "confirmed"
    elif confidence >= SINGLE_THRESHOLD:
        level = "single"
    else:
        level = "stale"   # что-то было, но протухло — показываем серым

    return FuelStatus(
        status=status,
        confidence=round(confidence, 3),
        level=level,
        age_min=age_min,
        queue_min=queue_min,
        limit_liters=limit_liters,
    )
