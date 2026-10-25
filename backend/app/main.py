import logging
from datetime import date, time
from hmac import compare_digest
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analytics import build_dashboard, filter_by_decision_date
from app.cache import get_redis, read_dashboard_cache, write_dashboard_cache
from app.config import get_settings
from app.database import get_db
from app.period import DECISION_END, DECISION_START, DEFAULT_DECISION_CUTOFF
from app.schemas import DashboardResponse, HealthResponse, IngestionAccepted

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="UK Wind Forecast Insights",
    description=(
        "Day-ahead wind forecasts available to GB power buyers for January 2026 purchase "
        "decisions, and their measured accuracy against outturn. Data: Elexon BMRS "
        "WINDFOR (forecast) and FUELHH fuelType=WIND (actual)."
    ),
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/api/v1/health/live", response_model=HealthResponse, tags=["health"])
def liveness() -> HealthResponse:
    return HealthResponse(status="ok", dependencies={})


@app.get(
    "/api/v1/health/ready",
    response_model=HealthResponse,
    tags=["health"],
    responses={503: {"description": "A required dependency is unavailable"}},
)
def readiness(
    session: Session = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> HealthResponse:
    dependencies: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        dependencies["postgres"] = "ok"
    except SQLAlchemyError:
        logger.exception("Readiness check: Postgres unavailable")
        dependencies["postgres"] = "unavailable"
    if redis is None:
        dependencies["redis"] = "disabled"
    else:
        try:
            redis.ping()
            dependencies["redis"] = "ok"
        except RedisError:
            # The cache is optional, so Redis being down degrades but does not fail readiness.
            dependencies["redis"] = "degraded"
    if dependencies["postgres"] != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "dependencies": dependencies},
        )
    return HealthResponse(status="ok", dependencies=dependencies)


@app.get("/api/v1/dashboard", response_model=DashboardResponse, tags=["dashboard"])
def dashboard(
    decision_date: date | None = Query(
        default=None,
        description="Restrict to one decision date (2026-01-01 .. 2026-01-31).",
    ),
    cutoff: time = Query(
        default=DEFAULT_DECISION_CUTOFF,
        description="Decision time on the decision day, HH:MM Europe/London. Only forecasts "
        "published at or before this moment are used.",
    ),
    session: Session = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> DashboardResponse:
    if decision_date is not None and not DECISION_START <= decision_date <= DECISION_END:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="decision_date must be in January 2026 (2026-01-01 to 2026-01-31)",
        )
    if cutoff.second or cutoff.microsecond or cutoff.tzinfo is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="cutoff must be a local wall-clock time in HH:MM format",
        )

    cached = read_dashboard_cache(redis, cutoff)
    if cached is not None:
        result = DashboardResponse.model_validate(cached)
    else:
        result = build_dashboard(session, cutoff)
        write_dashboard_cache(redis, cutoff, result.model_dump(mode="json"))
    if decision_date is not None:
        result = filter_by_decision_date(result, decision_date)
    return result


@app.post(
    "/api/v1/ingestion/sync",
    response_model=IngestionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
    responses={
        401: {"description": "Missing or invalid bearer token"},
        503: {"description": "Manual ingestion is not configured"},
    },
)
def trigger_ingestion(authorization: str | None = Header(default=None)) -> IngestionAccepted:
    settings = get_settings()
    if not settings.ingestion_token or not settings.redis_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual ingestion is disabled; set INGESTION_TOKEN and REDIS_URL to enable it.",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not compare_digest(
        supplied.strip().encode(), settings.ingestion_token.encode()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    from app.tasks import refresh_january_data  # Imported lazily: only this route needs Celery.

    task = refresh_january_data.delay()
    return IngestionAccepted(task_id=task.id, status="queued")


# Serve the built React app from the same origin in production images.
_static = Path(get_settings().static_dir)
if (_static / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
        candidate = (_static / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(_static.resolve()):
            return FileResponse(candidate)
        return FileResponse(_static / "index.html")
