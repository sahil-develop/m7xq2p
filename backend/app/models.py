from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UTCDateTime(TypeDecorator):
    """Stores aware datetimes and always returns them as UTC-aware values.

    SQLite (used for fast unit tests) drops tzinfo; without this, comparisons between
    stored and in-memory timestamps would silently mix naive and aware datetimes.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; pass a timezone-aware value")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class WindForecast(Base):
    """One WINDFOR value: national wind forecast for an hourly target time."""

    __tablename__ = "wind_forecasts"
    # The unique constraint's (start_time, publish_time) index also serves the
    # "latest forecast per target time" lookup, so no separate index is needed.
    __table_args__ = (
        UniqueConstraint("start_time", "publish_time", name="uq_forecast_start_publish"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    publish_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)


class WindActual(Base):
    """One FUELHH WIND value: national outturn for a half-hourly settlement period."""

    __tablename__ = "wind_actuals"

    start_time: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)


class ImportState(Base):
    __tablename__ = "import_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    forecast_rows: Mapped[int | None] = mapped_column(Integer)
    actual_rows: Mapped[int | None] = mapped_column(Integer)
