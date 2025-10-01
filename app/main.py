from __future__ import annotations
import logging
import urllib.parse as up
import csv
import io
from fastapi import FastAPI, Request, Form, status, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional
from datetime import date

from app.services.geo import geocode_one
from app.services.weather import get_current_weather, get_forecast_5d, get_daily_range
from app.services.validators import validate_date_range
from app.db import create_db_and_tables, get_session
from app.repositories.queries import create_query_with_snapshot, list_queries, get_query, get_latest_snapshot, unpack_snapshot, update_query_core, append_snapshot, delete_query_cascade

app = FastAPI(title="Weather App")

logging.basicConfig(level=logging.INFO)

templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Home page with a simple search form.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Form(...),
    start: Optional[str] = Form(None),
    end: Optional[str] = Form(None),
):
    # 1) Validate optional date range
    try:
        dr = validate_date_range(start, end)  # None or DateRange
    except ValueError as e:
        return templates.TemplateResponse("index.html", {"request": request, "error": str(e)}, status_code=400)

    # 2) Geocode
    resolved = await geocode_one(q)
    if resolved is None:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Could not resolve that location. Try a city, ZIP, or 'lat,lon'."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    lat = float(resolved["lat"]); lon = float(resolved["lon"])

    # 3) Fetch data (range vs 5-day)
    if dr:
        range_rows = await get_daily_range(lat, lon, dr.start, dr.end)
        if range_rows is None:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Could not fetch date-range data."}, status_code=502)
        current = await get_current_weather(lat, lon)
        if current is None:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Weather lookup failed. Please try again."}, status_code=502)
        forecast_for_storage = range_rows
    else:
        current = await get_current_weather(lat, lon)
        if current is None:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Weather lookup failed. Please try again."}, status_code=502)
        forecast_for_storage = await get_forecast_5d(lat, lon) or []

    # 4) Persist
    with get_session() as session:
        row = create_query_with_snapshot(
            session,
            input_text=q or "direct-latlon/geolocation",
            resolved_name=resolved["name"],
            lat=lat,
            lon=lon,
            current=current,
            forecast=forecast_for_storage,
            date_range=(dr.start, dr.end) if dr else None,
        )
        query_id = row.id

    # 5) Redirect to read by id
    url = "/result?" + up.urlencode({"id": str(query_id)})
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)



@app.get("/result", response_class=HTMLResponse)
async def result(
    request: Request,
    id: Optional[int] = Query(None),
    # Back-compat (if someone navigates directly with old params)
    q: str = Query(""),
    name: Optional[str] = Query(None),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    """
    Preferred path: id=<query_id> — loads stored snapshot (READ).
    Back-compat: if no id, falls back to live fetch (not persisted).
    """
    if id is not None:
        with get_session() as session:
            row = get_query(session, id)
            if not row:
                return templates.TemplateResponse("index.html", {"request": request, "error": "Record not found."}, status_code=404)
            snap = get_latest_snapshot(session, id)
            current, forecast = unpack_snapshot(snap)

            # If this row has a date range, we show it as "range_rows"
            range_rows = forecast if (row.date_start or row.date_end) else None
            ctx = {
                "request": request,
                "id": row.id,
                "query": row.input_text,
                "resolved": {"name": row.resolved_name, "lat": row.lat, "lon": row.lon},
                "current": current,
                "forecast": None if range_rows else forecast,
                "range_rows": range_rows,
                "date_range": None if not (row.date_start and row.date_end) else type("DR", (), {"start": row.date_start, "end": row.date_end})(),
            }
            return templates.TemplateResponse("result.html", ctx)

    # Back-compat path: compute live (but do not persist)
    if lat is None or lon is None or name is None:
        return templates.TemplateResponse("index.html", {"request": request, "error": "No id provided."}, status_code=400)

    # Validate date range if present (for a direct link)
    dr = None
    if start or end:
        try:
            dr = validate_date_range(start, end)
        except ValueError as e:
            return templates.TemplateResponse("index.html", {"request": request, "error": str(e)}, status_code=400)

    if dr:
        range_rows = await get_daily_range(lat, lon, dr.start, dr.end)
        current = await get_current_weather(lat, lon)
        ctx = {
            "request": request,
            "query": q,
            "resolved": {"name": name, "lat": lat, "lon": lon},
            "current": current,
            "forecast": None,
            "range_rows": range_rows,
            "date_range": dr,
        }
    else:
        current = await get_current_weather(lat, lon)
        forecast = await get_forecast_5d(lat, lon)
        ctx = {
            "request": request,
            "query": q,
            "resolved": {"name": name, "lat": lat, "lon": lon},
            "current": current,
            "forecast": forecast,
            "range_rows": None,
            "date_range": None,
        }
    return templates.TemplateResponse("result.html", ctx)



@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    with get_session() as session:
        rows = list_queries(session, limit=50)
    return templates.TemplateResponse("history.html", {"request": request, "rows": rows})


@app.get("/edit", response_class=HTMLResponse)
def edit(request: Request, id: int = Query(...)):
    with get_session() as session:
        row = get_query(session, id)
        if not row:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Record not found."}, status_code=404)
    return templates.TemplateResponse("edit.html", {"request": request, "row": row})


@app.post("/update", response_class=HTMLResponse)
async def update(
    request: Request,
    id: int = Form(...),
    input_text: str = Form(...),
    label: Optional[str] = Form(None),
    start: Optional[str] = Form(None),
    end: Optional[str] = Form(None),
):
    # Validate date range
    try:
        dr = validate_date_range(start, end)
    except ValueError as e:
        with get_session() as session:
            row = get_query(session, id)
        return templates.TemplateResponse("edit.html", {"request": request, "row": row, "error": str(e)}, status_code=400)

    # Resolve location (allows edit)
    resolved = await geocode_one(input_text)
    if resolved is None:
        with get_session() as session:
            row = get_query(session, id)
        return templates.TemplateResponse("edit.html", {"request": request, "row": row, "error": "Could not resolve that location."}, status_code=400)

    lat = float(resolved["lat"]); lon = float(resolved["lon"])

    # Fetch current + daily (range or 5-day)
    if dr:
        range_rows = await get_daily_range(lat, lon, dr.start, dr.end)
        if range_rows is None:
            with get_session() as session:
                row = get_query(session, id)
            return templates.TemplateResponse("edit.html", {"request": request, "row": row, "error": "Could not fetch date-range data."}, status_code=502)
        current = await get_current_weather(lat, lon)
        forecast_for_storage = range_rows
    else:
        current = await get_current_weather(lat, lon)
        if current is None:
            with get_session() as session:
                row = get_query(session, id)
            return templates.TemplateResponse("edit.html", {"request": request, "row": row, "error": "Weather lookup failed."}, status_code=502)
        forecast_for_storage = await get_forecast_5d(lat, lon) or []

    # Update row + append snapshot
    with get_session() as session:
        updated = update_query_core(
            session,
            query_id=id,
            input_text=input_text,
            resolved_name=resolved["name"],
            lat=lat,
            lon=lon,
            date_range=(dr.start, dr.end) if dr else (None, None),
            label=label,
        )
        if not updated:
            return templates.TemplateResponse("index.html", {"request": request, "error": "Record not found."}, status_code=404)
        append_snapshot(session, query_id=id, current=current, forecast=forecast_for_storage)

    # Redirect to view
    return RedirectResponse(f"/result?id={id}", status_code=303)


@app.post("/delete", response_class=HTMLResponse)
def delete(request: Request, id: int = Form(...)):
    with get_session() as session:
        ok = delete_query_cascade(session, id)
    if not ok:
        return templates.TemplateResponse("index.html", {"request": request, "error": "Record not found."}, status_code=404)
    return RedirectResponse("/history", status_code=303)


@app.get("/export/json")
def export_json(id: Optional[int] = Query(None)):
    with get_session() as session:
        if id is not None:
            row = get_query(session, id)
            if not row:
                return JSONResponse({"error": "Record not found."}, status_code=404)
            snap = get_latest_snapshot(session, id)
            current, forecast = unpack_snapshot(snap)
            payload = {
                "query": {
                    "id": row.id,
                    "input_text": row.input_text,
                    "resolved_name": row.resolved_name,
                    "lat": row.lat, "lon": row.lon,
                    "date_start": row.date_start.isoformat() if row.date_start else None,
                    "date_end": row.date_end.isoformat() if row.date_end else None,
                    "label": row.label,
                    "created_at": row.created_at.isoformat(),
                },
                "snapshot": {"current": current, "forecast": forecast},
            }
            filename = f"weather_{id}.json" if id is not None else "weather_queries.json"
            return JSONResponse(
                payload,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )   
        else:
            rows = list_queries(session, limit=1000)
            payload = []
            for r in rows:
                payload.append({
                    "id": r.id,
                    "input_text": r.input_text,
                    "resolved_name": r.resolved_name,
                    "lat": r.lat, "lon": r.lon,
                    "date_start": r.date_start.isoformat() if r.date_start else None,
                    "date_end": r.date_end.isoformat() if r.date_end else None,
                    "label": r.label,
                    "created_at": r.created_at.isoformat(),
                })
            return JSONResponse(payload)

@app.get("/export/csv")
def export_csv(id: Optional[int] = Query(None)):
    buf = io.StringIO()
    writer = csv.writer(buf)
    if id is not None:
        # single row: flatten a bit
        with get_session() as session:
            row = get_query(session, id)
            if not row:
                return PlainTextResponse("Record not found.", status_code=404)
            writer.writerow(["id","input_text","resolved_name","lat","lon","date_start","date_end","label","created_at"])
            writer.writerow([
                row.id, row.input_text, row.resolved_name, row.lat, row.lon,
                row.date_start.isoformat() if row.date_start else "",
                row.date_end.isoformat() if row.date_end else "",
                row.label or "",
                row.created_at.isoformat(),
            ])
    else:
        with get_session() as session:
            rows = list_queries(session, limit=1000)
        writer.writerow(["id","input_text","resolved_name","lat","lon","date_start","date_end","label","created_at"])
        for r in rows:
            writer.writerow([
                r.id, r.input_text, r.resolved_name, r.lat, r.lon,
                r.date_start.isoformat() if r.date_start else "",
                r.date_end.isoformat() if r.date_end else "",
                r.label or "",
                r.created_at.isoformat(),
            ])
    filename = f"weather_{id}.csv" if id is not None else "weather_queries.csv"
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )