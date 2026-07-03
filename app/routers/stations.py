"""GET /stations — заправки со статусами для карты; GET /stations/{id} — карточка."""

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..schemas import FuelType, ReportOut, StationDetail, StationOut
from ..service import fuel_statuses_for

router = APIRouter(tags=["stations"])


@router.get("/stations", response_model=list[StationOut])
async def list_stations(
    bbox: str = Query(..., description="Область карты: minLon,minLat,maxLon,maxLat"),
    fuel: FuelType | None = Query(None, description="Фильтр по марке топлива"),
) -> list[StationOut]:
    try:
        min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox: ожидается minLon,minLat,maxLon,maxLat")

    pool = db.get_pool()
    rows = await pool.fetch(
        """
        SELECT id, name, brand, lat, lon, address, city
        FROM stations
        WHERE lon BETWEEN $1 AND $3 AND lat BETWEEN $2 AND $4
        LIMIT 5000
        """,
        min_lon, min_lat, max_lon, max_lat,
    )

    statuses = await fuel_statuses_for([r["id"] for r in rows])

    stations = []
    for r in rows:
        fuel_statuses = statuses.get(r["id"], {})
        # Фильтр по топливу: оставляем только запрошенную марку
        if fuel is not None:
            fuel_statuses = {
                k: v for k, v in fuel_statuses.items() if k == fuel.value
            }
        stations.append(StationOut(**dict(r), fuel_statuses=fuel_statuses))
    return stations


@router.get("/stations/{station_id}", response_model=StationDetail)
async def get_station(station_id: int) -> StationDetail:
    pool = db.get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, brand, lat, lon, address, city, region FROM stations WHERE id = $1",
        station_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Станция не найдена")

    statuses = await fuel_statuses_for([station_id])

    recent = await pool.fetch(
        """
        SELECT id, station_id, fuel_type::text AS fuel_type, status::text AS status, created_at
        FROM reports
        WHERE station_id = $1
        ORDER BY created_at DESC
        LIMIT 10
        """,
        station_id,
    )

    return StationDetail(
        **dict(row),
        fuel_statuses=statuses.get(station_id, {}),
        recent_reports=[ReportOut(**dict(r)) for r in recent],
    )
