# Weather App

A small Python web app that lets users enter a location (city/ZIP/landmark or `lat,lon`), fetches weather from external APIs, and persists results in a **SQLite** database with basic **CRUD** and **export** features. 

## Stack & APIs

- **FastAPI** + **Jinja2** templates
- **httpx** (async) for API calls with short timeouts
- **SQLModel** (on SQLite) for a simple relational schema
- **Open-Meteo** (no API key) – current weather, forecast, and archive
- **Nominatim (OSM)** fallback for geocoding (requires a descriptive `User-Agent`)

---

## Project structure

```
app/
  main.py                 # routes, PRG, wiring
  db.py                   # engine, session, init
  models.py               # SQLModel tables
  services/
    geo.py                # geocoding (primary + fallback)
    weather.py            # current, 5-day, date-range (archive/forecast)
    validators.py         # date-range validation
  repositories/
    queries.py            # CRUD helpers and snapshot utilities
  templates/
    base.html
    index.html            # search form, geolocation button
    result.html           # current + (5-day or date-range) tables
    history.html          # list, per-row actions
    edit.html             # update form
  static/
    app.js                # geolocation JS
    styles.css            # styles
requirements.txt
```

---

## Setup & Run

> Requires **Python 3.10+** (tested on 3.10.5).

### 1) Create a virtual environment

#### Windows (PowerShell)
```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2) Run the app
```bash
python -m uvicorn app.main:app --reload
```
Open: http://127.0.0.1:8000

---

## How to use

1. **Search**: enter a city/ZIP/landmark or `lat,lon`. Optionally add a **date range** (YYYY-MM-DD).  
2. App geocodes, fetches weather, **saves to DB** (Create), then redirects to a bookmarkable **Result** page (Read).  
3. **History**: view past queries; per row you can **View | Edit | Delete | Export**.  
4. **Edit**: change input/label/range → app re-resolves & re-fetches and **appends** a new snapshot (Update).  
5. **Delete**: removes the row and its snapshots (Delete).  
6. **Export**: top-nav “Export All (JSON/CSV)” or per-row JSON/CSV.

---

## Data model

- **SearchQuery**
  - `id` (PK)
  - `input_text` (user input)
  - `resolved_name`, `lat`, `lon`
  - `date_start`, `date_end` (optional)
  - `label` (optional)
  - `created_at`
- **WeatherSnapshot**
  - `id` (PK), `query_id` (FK → SearchQuery, cascade delete)
  - `current_json` (denormalized)
  - `forecast_json` (either 5-day forecast or the validated date-range daily rows)
  - `created_at`

---

## Key design decisions (brief)

- **PRG (Post/Redirect/Get):** POST `/search` does validation, geocoding, API calls, persists, then redirects to GET `/result?id=…`. Avoids duplicates on refresh and cleanly separates writes from reads.
- **Two geocoders:** Open-Meteo first (fast/simple), fallback to Nominatim (great for landmarks) with a **descriptive User-Agent**.
- **Unit conversions:** °C→°F and mm→in computed in the service layer once.
- **Plain templates + static assets:** no inline scripts; tiny `app.js` attaches behavior if elements exist.

---

## Routes (public)

- `GET /` — search form (text + optional date range; “Use my location” button)
- `POST /search` — validate, geocode, fetch, create DB rows → 303 to `/result?id=…`
- `GET /result?id=…` — read from DB; show current + (5-day or date-range)
- `GET /history` — list rows with actions
- `GET /edit?id=…` — edit form
- `POST /update` — validate, re-resolve, re-fetch, update row, append snapshot, redirect to `/result?id=…`
- `POST /delete` — delete row (cascade snapshots), redirect to `/history`
- `GET /export/json[?id=…]` — export all or one row (attachment filename set)
- `GET /export/csv[?id=…]` — export all or one row (attachment filename set)

---

## External APIs (no keys required)

- **Open-Meteo Geocoding:** `https://geocoding-api.open-meteo.com/v1/search`
- **Open-Meteo Forecast:** `https://api.open-meteo.com/v1/forecast`
- **Open-Meteo Archive (ERA5):** `https://archive-api.open-meteo.com/v1/era5`
- **Nominatim (OSM) fallback:** `https://nominatim.openstreetmap.org/search`  
  Include a `User-Agent` like:  
  `weather-intern-demo/0.1 (+https://github.com/<your-repo>; contact: you@example.com)`

---

## Security & privacy notes

- No API keys are used; all calls are public/free.
- We store minimal user input and weather JSON locally (SQLite).
- No PII beyond what you type in the input/label.  
- No cookies/sessions.

---
