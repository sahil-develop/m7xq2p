from datetime import date
from hmac import compare_digest

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analytics import DECISION_END, DECISION_START, build_dashboard
from app.cache import (
    get_redis,
    read_dashboard_cache,
    write_dashboard_cache,
)
from app.config import get_settings
from app.database import get_db
from app.schemas import DashboardResponse, HealthResponse, IngestionAccepted
from app.tasks import refresh_january_data

app = FastAPI(
    title="UK Wind Forecast Insights",
    description=(
        "January 2026 day-ahead wind forecasts and forecast accuracy, "
        "using Elexon WINDFOR and FUELHH data."
    ),
    version="1.0.0",
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


@app.get("/api/v1/health/ready", response_model=HealthResponse, tags=["health"])
def readiness(
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> HealthResponse:
    dependencies: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        dependencies["postgres"] = "ok"
    except SQLAlchemyError:
        dependencies["postgres"] = "unavailable"
    try:
        redis.ping()
        dependencies["redis"] = "ok"
    except RedisError:
        dependencies["redis"] = "unavailable"
    result = "ok" if all(value == "ok" for value in dependencies.values()) else "unavailable"
    if result != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": result, "dependencies": dependencies},
        )
    return HealthResponse(status=result, dependencies=dependencies)


@app.get("/api/v1/dashboard", response_model=DashboardResponse, tags=["dashboard"])
def dashboard(
    decision_date: date | None = Query(
        default=None,
        description="Optional decision date filter; must fall in January 2026.",
    ),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> DashboardResponse:
    if decision_date and not DECISION_START <= decision_date <= DECISION_END:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision_date must fall between 2026-01-01 and 2026-01-31",
        )
    cached = read_dashboard_cache(redis)
    if cached is None:
        response = build_dashboard(session)
        cached = response.model_dump(mode="json")
        write_dashboard_cache(redis, cached)
    if decision_date is not None:
        cached["points"] = [
            point for point in cached["points"] if point["decision_date"] == decision_date.isoformat()
        ]
        cached["daily"] = [
            row for row in cached["daily"] if row["decision_date"] == decision_date.isoformat()
        ]
    return DashboardResponse.model_validate(cached)


@app.post(
    "/api/v1/ingestion/sync",
    response_model=IngestionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
)
def trigger_ingestion(authorization: str | None = Header(default=None)) -> IngestionAccepted:
    expected = get_settings().ingestion_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual ingestion is disabled; configure INGESTION_TOKEN to enable it.",
        )
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    task = refresh_january_data.delay()
    return IngestionAccepted(task_id=task.id, status="queued")
