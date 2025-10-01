import json
from typing import Optional, Tuple, List
from sqlmodel import select
from app.models import SearchQuery, WeatherSnapshot
from datetime import date

def create_query_with_snapshot(
    session,
    *,
    input_text: str,
    resolved_name: str,
    lat: float,
    lon: float,
    current: dict,
    forecast: Optional[list] = None,
    date_range: Optional[Tuple[Optional[date], Optional[date]]] = None, 
    label: Optional[str] = None,
) -> SearchQuery:
    q = SearchQuery(
        input_text=input_text,
        resolved_name=resolved_name,
        lat=lat,
        lon=lon,
        date_start=(date_range[0] if date_range else None),
        date_end=(date_range[1] if date_range else None),
        label=label,
    )
    session.add(q)
    session.flush()  # ensures q.id exists

    snap = WeatherSnapshot(
        query_id=q.id,
        current_json=json.dumps(current),
        forecast_json=json.dumps(forecast or []),
    )
    session.add(snap)
    session.commit()
    session.refresh(q)
    return q

def list_queries(session, limit: int = 50):
    stmt = select(SearchQuery).order_by(SearchQuery.created_at.desc()).limit(limit)
    return session.exec(stmt).all()

def get_query(session, qid: int) -> Optional[SearchQuery]:
    return session.get(SearchQuery, qid)

def get_latest_snapshot(session, query_id: int) -> Optional[WeatherSnapshot]:
    stmt = (
        select(WeatherSnapshot)
        .where(WeatherSnapshot.query_id == query_id)
        .order_by(WeatherSnapshot.created_at.desc())
        .limit(1)
    )
    return session.exec(stmt).first()

def unpack_snapshot(snapshot: WeatherSnapshot) -> Tuple[dict, List[dict]]:
    current = json.loads(snapshot.current_json) if snapshot and snapshot.current_json else {}
    forecast = json.loads(snapshot.forecast_json) if snapshot and snapshot.forecast_json else []
    return current, forecast

def update_query_core(
    session,
    *,
    query_id: int,
    input_text: Optional[str] = None,
    resolved_name: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    date_range: Optional[Tuple[Optional[date], Optional[date]]] = None,
    label: Optional[str] = None,
) -> Optional[SearchQuery]:
    row = session.get(SearchQuery, query_id)
    if not row:
        return None
    if input_text is not None:
        row.input_text = input_text
    if resolved_name is not None:
        row.resolved_name = resolved_name
    if lat is not None:
        row.lat = lat
    if lon is not None:
        row.lon = lon
    if date_range is not None:
        row.date_start, row.date_end = date_range
    if label is not None:
        row.label = label
    session.add(row)
    session.commit()
    session.refresh(row)
    return row

def append_snapshot(
    session,
    *,
    query_id: int,
    current: dict,
    forecast: List[dict],
) -> WeatherSnapshot:
    snap = WeatherSnapshot(
        query_id=query_id,
        current_json=json.dumps(current),
        forecast_json=json.dumps(forecast),
    )
    session.add(snap)
    session.commit()
    session.refresh(snap)
    return snap

def delete_query_cascade(session, query_id: int) -> bool:
    row = session.get(SearchQuery, query_id)
    if not row:
        return False
    session.delete(row)  # cascade handles snapshots
    session.commit()
    return True