"""Общая бизнес-логика, нужная и веб-API, и боту."""

from collections import defaultdict

from . import db, trust
from .schemas import FuelStatusOut

REPORTS_WINDOW_SQL = """
    SELECT r.station_id, r.fuel_type::text AS fuel_type, r.status::text AS status,
           r.queue_min, r.limit_liters, r.created_at, u.reputation
    FROM reports r
    LEFT JOIN users u ON u.id = r.user_id
    WHERE r.station_id = ANY($1)
      AND r.created_at > now() - interval '24 hours'
"""


async def fuel_statuses_for(station_ids: list[int]) -> dict[int, dict[str, FuelStatusOut]]:
    """Собирает свежие отметки по списку АЗС и прогоняет через умное ядро."""
    pool = db.get_pool()
    rows = await pool.fetch(REPORTS_WINDOW_SQL, station_ids)

    # Группируем отметки по (АЗС, марка топлива)
    grouped: dict[tuple[int, str], list[trust.RawReport]] = defaultdict(list)
    for r in rows:
        grouped[(r["station_id"], r["fuel_type"])].append(
            trust.RawReport(
                status=r["status"],
                created_at=r["created_at"],
                reputation=r["reputation"],
                queue_min=r["queue_min"],
                limit_liters=r["limit_liters"],
            )
        )

    result: dict[int, dict[str, FuelStatusOut]] = defaultdict(dict)
    for (station_id, fuel), reports in grouped.items():
        agg = trust.aggregate(reports)
        if agg is not None:
            result[station_id][fuel] = FuelStatusOut(**agg.__dict__)
    return result
