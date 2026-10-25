from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.cache import get_redis, invalidate_dashboard_cache
from app.database import SessionLocal
from app.elexon import ElexonClient, actual_values, forecast_values
from app.models import ImportState, WindActual, WindForecast

DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)
UTC = timezone.utc


def _upsert(session: Session, model: type, values: list[dict]) -> None:
    if not values:
        return
    dialect = session.bind.dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    statement = insert(model).values(values)
    if model is WindForecast:
        statement = statement.on_conflict_do_update(
            index_elements=["start_time", "publish_time"],
            set_={"generation_mw": statement.excluded.generation_mw},
        )
    else:
        statement = statement.on_conflict_do_update(
            index_elements=["start_time"],
            set_={"generation_mw": statement.excluded.generation_mw},
        )
    session.execute(statement)


def sync_january_data(
    session_factory=SessionLocal,
    client_factory=ElexonClient,
    cache_factory=get_redis,
) -> dict[str, int]:
    client = client_factory()
    forecasts_seen = 0
    actuals_seen = 0
    try:
        with session_factory() as session:
            # Delivery starts the day after each decision and ends Jan 31's next-day delivery.
            for offset in range((DECISION_END - DECISION_START).days + 1):
                decision_day = DECISION_START + timedelta(days=offset)
                forecast_rows = [
                    forecast_values(row) for row in client.fetch_forecasts(decision_day)
                ]
                _upsert(session, WindForecast, forecast_rows)
                forecasts_seen += len(forecast_rows)

                delivery_day = decision_day + timedelta(days=1)
                actual_rows = [actual_values(row) for row in client.fetch_actuals(delivery_day)]
                _upsert(session, WindActual, actual_rows)
                actuals_seen += len(actual_rows)
                session.commit()

            state = session.get(ImportState, 1)
            if state is None:
                session.add(ImportState(id=1, last_synced_at=datetime.now(UTC)))
            else:
                state.last_synced_at = datetime.now(UTC)
            session.commit()
        invalidate_dashboard_cache(cache_factory())
    finally:
        client.http_client.close()
    return {"forecasts": forecasts_seen, "actuals": actuals_seen}


if __name__ == "__main__":
    print(sync_january_data())
