"""Load the January 2026 decision window from Elexon into Postgres.

The sync is idempotent (upserts keyed on natural keys) and runs in one transaction, so
a failed or retried run never leaves a half-imported dataset behind.
"""

import argparse
import logging
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.cache import create_redis, invalidate_dashboard_cache
from app.database import SessionLocal
from app.elexon import ElexonClient, actual_values, forecast_values
from app.models import ImportState, WindActual, WindForecast
from app.period import DECISION_END, DECISION_START, delivery_window

logger = logging.getLogger(__name__)
UPSERT_BATCH_SIZE = 5000
FETCH_CHUNK_DAYS = 7


def _upsert(session: Session, model: type, rows: list[dict], keys: list[str]) -> None:
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    for offset in range(0, len(rows), UPSERT_BATCH_SIZE):
        statement = insert(model).values(rows[offset : offset + UPSERT_BATCH_SIZE])
        session.execute(
            statement.on_conflict_do_update(
                index_elements=keys,
                set_={"generation_mw": statement.excluded.generation_mw},
            )
        )


def _dedupe(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Postgres rejects an upsert batch that touches the same key twice; last row wins."""
    return list({tuple(row[k] for k in keys): row for row in rows}.values())


def fetch_window(client: ElexonClient) -> tuple[list[dict], list[dict]]:
    window_start, window_end = delivery_window()
    # A forecast published the day before a decision can still be the latest one
    # available at an early cutoff, so start one day before the first decision date.
    publish_from = datetime.combine(DECISION_START - timedelta(days=1), time.min, tzinfo=UTC)
    publish_to = datetime.combine(DECISION_END + timedelta(days=1), time.min, tzinfo=UTC)

    forecasts: list[dict] = []
    chunk_start = publish_from
    while chunk_start < publish_to:
        chunk_end = min(chunk_start + timedelta(days=FETCH_CHUNK_DAYS), publish_to)
        rows = client.fetch_forecasts(chunk_start, chunk_end - timedelta(seconds=1))
        forecasts.extend(forecast_values(row) for row in rows)
        chunk_start = chunk_end
    forecasts = [f for f in forecasts if window_start <= f["start_time"] < window_end]

    first_delivery, last_delivery = (
        DECISION_START + timedelta(days=1),
        DECISION_END + timedelta(days=1),
    )
    actuals = [
        values
        for values in map(actual_values, client.fetch_actuals(first_delivery, last_delivery))
        if window_start <= values["start_time"] < window_end
    ]
    return (
        _dedupe(forecasts, ("start_time", "publish_time")),
        _dedupe(actuals, ("start_time",)),
    )


def sync_january_data(
    session_factory: Callable[[], Session] = SessionLocal,
    client_factory: Callable[[], ElexonClient] = ElexonClient,
    cache_factory=create_redis,
) -> dict[str, int]:
    client = client_factory()
    try:
        forecasts, actuals = fetch_window(client)
    finally:
        client.close()

    with session_factory() as session, session.begin():
        _upsert(session, WindForecast, forecasts, ["start_time", "publish_time"])
        _upsert(session, WindActual, actuals, ["start_time"])
        state = session.get(ImportState, 1) or ImportState(id=1)
        state.last_synced_at = datetime.now(UTC)
        state.forecast_rows = session.scalar(select(func.count()).select_from(WindForecast))
        state.actual_rows = session.scalar(select(func.count()).select_from(WindActual))
        session.add(state)

    # Invalidate only after the commit so readers can never re-cache pre-sync data.
    cache = cache_factory()
    try:
        invalidate_dashboard_cache(cache)
    finally:
        if cache is not None:
            cache.close()
    result = {"forecasts": len(forecasts), "actuals": len(actuals)}
    logger.info("Elexon sync complete: %s", result)
    return result


def has_data(session_factory: Callable[[], Session] = SessionLocal) -> bool:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(WindForecast)) > 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import January 2026 Elexon wind data")
    parser.add_argument(
        "--if-empty", action="store_true", help="Skip the import if data is already loaded"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if arguments.if_empty and has_data():
        logger.info("Wind data already present; skipping import")
    else:
        print(sync_january_data())
