from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WindForecast(Base):
    __tablename__ = "wind_forecasts"
    __table_args__ = (
        UniqueConstraint("start_time", "publish_time", name="uq_forecast_start_publish"),
        Index("ix_forecast_start_publish", "start_time", "publish_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publish_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)


class WindActual(Base):
    __tablename__ = "wind_actuals"
    __table_args__ = (Index("ix_actual_start_time", "start_time"),)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)


class ImportState(Base):
    __tablename__ = "import_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
