from datetime import date

import pytest
from sqlalchemy import func, select

from app.cache import cache_key
from app.elexon import ElexonAPIError
from app.ingestion import sync_january_data
from app.models import ImportState, WindActual, WindForecast
from app.period import DEFAULT_DECISION_CUTOFF


class FakeElexon:
    def __init__(self, forecast_mw: float = 500, broken: bool = False) -> None:
        self.forecast_mw = forecast_mw
        self.broken = broken
        self.forecast_windows: list[tuple] = []
        self.actual_dates: tuple[date, date] | None = None
        self.closed = False

    def fetch_forecasts(self, published_from, published_to):
        self.forecast_windows.append((published_from, published_to))
        if published_from.day != 31 or published_from.month != 12:
            return []
        return [
            # Duplicate row in one response: the later value must win without a DB error.
            {
                "publishTime": "2025-12-31T22:30:00Z",
                "startTime": "2026-01-02T00:00:00Z",
                "generation": 1,
            },
            {
                "publishTime": "2025-12-31T22:30:00Z",
                "startTime": "2026-01-02T00:00:00Z",
                "generation": self.forecast_mw,
            },
            # Target before the delivery window: dropped.
            {
                "publishTime": "2025-12-31T22:30:00Z",
                "startTime": "2026-01-01T12:00:00Z",
                "generation": 9,
            },
        ]

    def fetch_actuals(self, first_day, last_day):
        self.actual_dates = (first_day, last_day)
        if self.broken:
            return [{"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": "x"}]
        return [
            {"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 400},
            {"fuelType": "WIND", "startTime": "2026-01-02T00:30:00Z", "generation": 420},
        ]

    def close(self):
        self.closed = True


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_sync_imports_window_and_invalidates_cache(session_factory, memory_redis):
    memory_redis.setex(cache_key(DEFAULT_DECISION_CUTOFF), 60, "{}")
    memory_redis.setex("unrelated", 60, "keep")
    fake = FakeElexon()

    result = sync_january_data(session_factory, lambda: fake, lambda: memory_redis)

    assert result == {"forecasts": 1, "actuals": 2}
    assert fake.closed
    assert fake.forecast_windows[0][0].isoformat() == "2025-12-31T00:00:00+00:00"
    assert fake.forecast_windows[-1][1].isoformat() == "2026-01-31T23:59:59+00:00"
    assert fake.actual_dates == (date(2026, 1, 2), date(2026, 2, 1))
    assert memory_redis.values == {"unrelated": "keep"}
    with session_factory() as session:
        assert session.scalars(select(WindForecast.generation_mw)).all() == [500]
        assert _count(session, WindActual) == 2
        state = session.get(ImportState, 1)
        assert state.last_synced_at is not None
        assert (state.forecast_rows, state.actual_rows) == (1, 2)


def test_sync_is_idempotent_and_updates_revised_values(session_factory, memory_redis):
    sync_january_data(session_factory, FakeElexon, lambda: memory_redis)
    sync_january_data(session_factory, lambda: FakeElexon(forecast_mw=650), lambda: memory_redis)

    with session_factory() as session:
        assert session.scalars(select(WindForecast.generation_mw)).all() == [650]
        assert _count(session, WindActual) == 2


def test_failed_sync_leaves_existing_data_and_cache_untouched(session_factory, memory_redis):
    sync_january_data(session_factory, FakeElexon, lambda: memory_redis)
    memory_redis.setex(cache_key(DEFAULT_DECISION_CUTOFF), 60, "{}")

    with pytest.raises(ElexonAPIError):
        sync_january_data(
            session_factory, lambda: FakeElexon(forecast_mw=999, broken=True), lambda: memory_redis
        )

    with session_factory() as session:
        assert session.scalars(select(WindForecast.generation_mw)).all() == [500]
    assert cache_key(DEFAULT_DECISION_CUTOFF) in memory_redis.values
