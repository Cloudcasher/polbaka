"""POST /reports — приём отметок о ситуации на заправке."""

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..schemas import ReportIn, ReportOut

router = APIRouter(tags=["reports"])

# Защита от спама: без неё аноним циклом перекрасит весь город в «пусто».
# Простой in-memory лимит по IP; настоящий антифрод — Фаза 4.
RATE_LIMIT = 20          # отметок
RATE_WINDOW = 3600       # за час
_recent: dict[str, deque] = defaultdict(deque)


def _rate_ok(ip: str) -> bool:
    now = time.monotonic()
    hits = _recent[ip]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        return False
    hits.append(now)
    return True


@router.post("/reports", response_model=ReportOut, status_code=201)
async def create_report(report: ReportIn, request: Request) -> ReportOut:
    if not _rate_ok(request.client.host):
        raise HTTPException(
            status_code=429, detail="Слишком много отметок — попробуйте позже"
        )

    pool = db.get_pool()

    station_exists = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM stations WHERE id = $1)", report.station_id
    )
    if not station_exists:
        raise HTTPException(status_code=404, detail="Станция не найдена")

    # MVP: все отметки анонимные (user_id = NULL, вес 0.3).
    # Вход через Telegram и репутация подключатся в Фазе 2.
    row = await pool.fetchrow(
        """
        INSERT INTO reports (station_id, user_id, fuel_type, status,
                             queue_min, limit_liters, comment, source)
        VALUES ($1, NULL, $2, $3, $4, $5, $6, 'web')
        RETURNING id, station_id, fuel_type::text, status::text, created_at
        """,
        report.station_id,
        report.fuel_type.value,
        report.status.value,
        report.queue_min,
        report.limit_liters,
        report.comment,
    )
    return ReportOut(**dict(row))
