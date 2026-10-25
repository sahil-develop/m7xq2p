"""The assignment window: day-ahead purchase decisions made during January 2026.

A decision taken on day D (UK local time) buys power for delivery day D+1, so the
delivery window runs 2026-01-02 .. 2026-02-01 and forecasts must have been published
no later than the decision cutoff on D.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)
# GB day-ahead auctions close mid-morning UK time (EPEX hourly ~09:20, N2EX ~09:50).
# 09:00 leaves the trading desk time to act on the forecast before gate closure.
DEFAULT_DECISION_CUTOFF = time(9, 0)


def decision_dates() -> list[date]:
    return [
        DECISION_START + timedelta(days=offset)
        for offset in range((DECISION_END - DECISION_START).days + 1)
    ]


def local_midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=LONDON)


def delivery_window() -> tuple[datetime, datetime]:
    """Half-open [start, end) covering every delivery day, as aware datetimes."""
    return (
        local_midnight(DECISION_START + timedelta(days=1)),
        local_midnight(DECISION_END + timedelta(days=2)),
    )


def decision_date_for(target: datetime) -> date:
    """The decision day whose day-ahead purchase covers this delivery timestamp."""
    return target.astimezone(LONDON).date() - timedelta(days=1)


def cutoff_for(decision_date: date, cutoff: time) -> datetime:
    return datetime.combine(decision_date, cutoff, tzinfo=LONDON)
