# Wind Forecast Insights

A web app for a UK utility's day-ahead trading desk. For every purchase decision in
January 2026 it shows **the national wind forecast the desk could actually see at
decision time**, and measures **how accurate that forecast turned out to be** against
the wind that was delivered.

- **Live app:** _not yet deployed — add the Heroku URL here after `git push heroku main`_ (see [Deployment](#deployment-heroku))
- **Data:** Elexon BMRS [WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream) (forecast) and [FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream) with `fuelType=WIND` (actual). No other data is used.
- **Stack:** React + TypeScript (Vite, Recharts) · Python 3.12 FastAPI · PostgreSQL · Redis · Celery · Docker

## What the January 2026 data shows

Using the default 09:00 UK decision cutoff, across 744 delivery hours (2 Jan – 1 Feb 2026):

| Metric | Value |
|---|---|
| Mean absolute error | **2.04 GW** (18.1% of mean outturn) |
| RMSE | 2.50 GW |
| Bias (forecast − actual) | **+1.75 GW**: the forecast exceeded outturn in 85% of hours |
| 80% of hours: actual vs forecast | between **−4.10 GW and +0.55 GW** |
| Worst delivery day | 28 Jan (MAE 5.37 GW) |

What this means for the desk:
- The forecast is systematically optimistic. Buying against the raw forecast would
  usually leave the desk short of wind and buying back at higher prices.
- The likely-range band in the app turns the error into a planning range. For
  example: "plan for wind 0.5 GW above to 4.1 GW below the forecast". It is computed
  from January itself, so treat it as a description of this month's error rather than
  a validated prediction for other months.
- Deciding later barely helps. A 13:00 cutoff (after the midday run) cuts MAE only to
  1.90 GW, and the bias stays at +1.69 GW.

A likely contributor to the bias, not verified here: FUELHH reports metered output
*after* curtailment of transmission-connected wind, while WINDFOR forecasts available
generation.

## Key definitions and assumptions

| Topic | Decision | Why |
|---|---|---|
| Decision day → delivery day | A decision on day D (UK local) buys for delivery day D+1. Decisions run 1–31 Jan, so delivery runs 2 Jan–1 Feb. | Day-ahead market |
| Forecast "available" at decision time | Latest WINDFOR value with `publishTime` ≤ cutoff on D. This can be a run from D−1 if the cutoff is early. | Mirrors what a trader saw; no look-ahead |
| Default cutoff | **09:00 Europe/London**, adjustable to 06:00, 11:00 or 13:00 in the UI, or any HH:MM via the API | GB day-ahead auctions close mid-morning (EPEX hourly ≈09:20, N2EX ≈09:50 UK). Please confirm the desk's actual decision time. |
| Hourly vs half-hourly | WINDFOR is hourly; FUELHH is half-hourly. Each forecast hour is compared with the **mean of its two half-hours**, and hours missing either half are not scored. | Like-for-like average MW over the hour |
| Error | `forecast − actual`; positive means over-forecast | |
| Metrics | MAE, RMSE, bias, MAPE, nMAE (MAE / mean actual), P10/P50/P90 of signed error, P90 of absolute error | Bias and quantiles matter more than MAPE for procurement sizing |
| Likely range | `[forecast − P90 error, forecast − P10 error]` using the month's error distribution | Empirical, distribution-free 80% interval. It is measured on January itself (in-sample), so it describes this month's error; the UI says so. |

WINDFOR publishes 8 runs a day (02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and
22:30 UTC). Each run covers hourly targets from a few hours before publication up to
21:00 UTC two days later (about 46–66 hours ahead), so the 07:30 run on D covers all of D+1. In January, UK local time equals UTC.
The code still converts through `Europe/London`, so other months would handle BST
correctly.

## Architecture

```
          Elexon BMRS API
                │  httpx (WINDFOR by publish window, FUELHH by settlement date)
                ▼
  ┌────────────────────────┐   nightly beat / POST /ingestion/sync   ┌──────────────┐
  │ Celery worker          │ ◀───────────── broker ───────────────── │ Redis        │
  │ app/ingestion.py       │                                         │ broker+cache │
  └──────────┬─────────────┘                                         └──────▲───────┘
             │ one transaction, idempotent upserts                          │ read-through,
             ▼                                                              │ per-cutoff keys
  ┌────────────────────────┐   SQL (2 range queries)   ┌────────────────────┴───────┐
  │ PostgreSQL             │ ◀──────────────────────── │ FastAPI app/main.py        │
  │ wind_forecasts         │                           │ /api/v1/dashboard           │──▶ React SPA
  │ wind_actuals           │                           │ app/analytics.py            │   (served by
  │ import_state           │                           │ /api/v1/health/{live,ready} │    FastAPI)
  └────────────────────────┘                           └─────────────────────────────┘
```

- **Ingestion** (`app/ingestion.py`)
  - Fetches forecasts published from 31 Dec to 31 Jan (in 7-day chunks) and actuals
    for 2 Jan to 1 Feb, then keeps only targets inside the delivery window.
  - Upserts on natural keys: `(start_time, publish_time)` for forecasts and
    `start_time` for actuals.
  - Runs in one transaction. A failed run changes nothing, and a re-run (e.g. a
    Celery retry) is harmless.
  - The cache is invalidated only after commit, so stale data cannot be re-cached.
- **Analytics** (`app/analytics.py`)
  - Two indexed range queries feed pure-Python selection and metric code.
  - The data is about 18k forecast rows and 1.5k actuals, so building the dashboard
    takes about 0.4 s uncached and about 15 ms from Redis.
- **Cache** (`app/cache.py`)
  - Key `wind-dashboard:v2:cutoff=HHMM`, TTL 1 h, explicitly invalidated after every
    sync.
  - Redis is optional. If it is unset or down, requests fall back to Postgres and
    `/health/ready` reports `redis: degraded` instead of failing.
- **Background jobs** (`app/tasks.py`)
  - Celery beat refreshes nightly at 02:00 UTC, because Elexon revises settlement data.
  - Network and HTTP errors retry with exponential backoff (up to 5 times).
    `acks_late` re-delivers the job if a worker dies mid-run.
- **Manual refresh**: `POST /api/v1/ingestion/sync` with `Authorization: Bearer $INGESTION_TOKEN`.
  The token is compared in constant time, and the endpoint is disabled unless a token
  is configured.
- **Frontend**
  - One fetch per cutoff returns the whole month (744 points). Picking a day filters
    client-side, so it is instant.
  - The view state (`?cutoff=09:00&day=2026-01-10`) is kept in the URL so it can be
    shared. A day outside the window falls back to the whole month.
  - While a new cutoff loads, the previous view stays visible (dimmed) with a loading
    notice. If a request fails, the last good view stays on screen with an error and a
    Retry button. An empty database shows instructions instead of empty charts.

## Repository layout

| Path | Contents |
|---|---|
| `backend/app/main.py` | FastAPI routes: dashboard, health, manual sync. Also serves the built SPA. |
| `backend/app/analytics.py` | Forecast selection at the cutoff, hourly pairing, accuracy metrics and breakdowns |
| `backend/app/period.py` | The January 2026 decision and delivery window, cutoff and timezone helpers |
| `backend/app/ingestion.py` | Elexon → Postgres sync (CLI: `python -m app.ingestion [--if-empty]`) |
| `backend/app/elexon.py` | HTTP client and record validation for WINDFOR and FUELHH |
| `backend/app/cache.py` | Redis read-through cache with graceful degradation |
| `backend/app/tasks.py` | Celery app, nightly schedule, retry policy |
| `backend/app/models.py`, `schemas.py`, `config.py`, `database.py` | ORM models (UTC-aware timestamps), API schemas, settings, DB session |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | pytest suite (runs on Postgres via `TEST_DATABASE_URL`, otherwise SQLite) |
| `frontend/src/App.tsx` | Page layout, controls, data loading |
| `frontend/src/components/` | KPI tiles, forecast chart, bar charts, daily table |
| `frontend/src/lib.ts` (+ `lib.test.ts`) | Likely-range computation and formatters (Vitest) |
| `Dockerfile` | Multi-stage build: React → static files inside the Python API image |
| `backend/Dockerfile` | API-only image built from `backend/` (Render; SPA hosted separately) |
| `compose.yaml` | Postgres, Redis, one-shot migrate+seed, API, Celery worker and beat |
| `heroku.yml` | Heroku container deploy with release-phase migration and seed |
| `.github/workflows/ci.yml` | Lint, format, migration round-trip, tests on Postgres, frontend tests and build, Docker build |
| `.env.example` | Configuration template (no secrets) |
| `AUDIT.md` | Requirement-by-requirement audit with verification evidence |

## Running it

### With Docker (recommended)

```bash
cp .env.example .env            # optional; defaults work locally
docker compose up --build
```

Open http://localhost:8000. API docs (Swagger) are at http://localhost:8000/docs.

On first start, the `migrate` service applies migrations and loads January 2026 from
Elexon. This takes about 10 s and needs internet access.

### Without Docker

You need Python 3.11+, Node 20+, and a reachable PostgreSQL. Redis is optional.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cd backend
export DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5432/wind_forecast_insights
export REDIS_URL=redis://localhost:6379/0     # optional
alembic upgrade head
python -m app.ingestion                       # load Elexon data
uvicorn app.main:app --reload                 # API on :8000

# in another shell
cd frontend && npm install && npm run dev     # UI on :5173, proxies /api to :8000
```

### Tests and checks

```bash
ruff check backend && ruff format --check backend
pytest                                                        # SQLite, no services needed
TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5432/wind_test pytest   # real Postgres
cd frontend && npm test && npm run build
```

The suite covers:
- forecast selection at the cutoff, including the previous-day fallback and the
  delivery-window edges;
- half-hour pairing and the metric formulas;
- per-cutoff cache hits, misses and invalidation;
- Redis outages;
- ingestion idempotency, rollback on bad data, and deduplication;
- Elexon client validation;
- request validation, health endpoints, manual-sync authentication, Celery retry
  wiring, and SPA hosting;
- empty-database responses, zero-output hours in MAPE/nMAE, and UK-local cutoffs
  across daylight saving;
- `rediss://` (Heroku Redis) URL handling for redis-py and Celery;
- frontend: likely-range maths, client-side day filtering, invalid shared links, and
  formatters.

## Deployment (Heroku)

The challenge allows Vercel or Heroku. Heroku is used because the app is a Docker
image with Postgres and an optional worker.

```bash
heroku create <app-name>
heroku stack:set container
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini        # optional: caching + manual/background sync
heroku config:set INGESTION_TOKEN=$(openssl rand -hex 24)   # optional
git push heroku main
```

- The release phase runs migrations and loads the data on the first deploy.
- `DATABASE_URL` from Heroku (`postgres://…`) is normalised automatically.
- `REDIS_URL` from Heroku Redis (`rediss://…`, self-signed certificate) gets
  `ssl_cert_reqs=none` appended unless the URL already sets it, as Heroku documents.
  Without it Celery refuses the URL and redis-py fails certificate verification.
- To enable nightly refreshes, add a worker dyno process running
  `celery -A app.tasks:celery_app worker -B --concurrency=1`. Without it, the app works
  on the data loaded at release.

## Deployment (Vercel frontend + Render backend)

The same repository can also deploy as two services: the SPA on Vercel and the API on
Render. The Docker Compose stack and the single-image build are unaffected.

**Render (web service, Docker runtime)**

- Root Directory: `backend` (uses `backend/Dockerfile`; build context is `backend/`)
- Create a Render Postgres instance and set `DATABASE_URL` to its internal URL
  (`postgresql://…` is normalised automatically).
- `CORS_ORIGINS`: the Vercel origin(s), comma-separated, no trailing slash, e.g.
  `https://<project>.vercel.app`.
- Optional: `REDIS_URL` (Render Key Value) for caching and manual sync, `INGESTION_TOKEN`.
- Pre-Deploy Command: `alembic upgrade head && python -m app.ingestion --if-empty`.
  On instance types without pre-deploy, set the Docker Command to
  `sh -c "alembic upgrade head && python -m app.ingestion --if-empty && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers"`.
- Health Check Path: `/api/v1/health/ready`

**Vercel**

- Root Directory: `frontend`; framework preset Vite (build `npm run build`, output `dist`).
- `VITE_API_BASE_URL`: the Render service origin, e.g. `https://<service>.onrender.com`.
  It is read at build time, so redeploy after changing it.

## API

| Method & path | Purpose |
|---|---|
| `GET /api/v1/dashboard?cutoff=HH:MM&decision_date=YYYY-MM-DD` | Points, summary metrics, daily accuracy, and breakdowns by hour and by horizon. Both parameters are optional; the default cutoff is 09:00. |
| `GET /api/v1/health/live` | Process is up |
| `GET /api/v1/health/ready` | Postgres reachable (503 if not); Redis status reported |
| `POST /api/v1/ingestion/sync` | Queue an Elexon refresh (bearer token) |

Full schema: `/docs` (Swagger UI) or `/openapi.json`.

## Use of AI tools

This project was built with help from AI coding assistants, including Anthropic's
Claude (Claude Code). They were used to review and fix the initial backend, write the
frontend and tests, and draft this README. A later AI-assisted audit pass (Claude Code)
checked every requirement against the brief and fixed the defects listed in `AUDIT.md`. All analysis figures above come from running
the code against live Elexon data.
