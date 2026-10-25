import fnmatch
from datetime import UTC, datetime, timedelta

from redis.exceptions import ConnectionError as RedisConnectionError

from app.models import WindActual, WindForecast


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def forecast(start: datetime, published: datetime, mw: float) -> WindForecast:
    return WindForecast(start_time=start, publish_time=published, generation_mw=mw)


def hourly_actual(start: datetime, first_half_mw: float, second_half_mw: float | None = None):
    """Two half-hourly FUELHH rows for the hour starting at `start`."""
    rows = [WindActual(start_time=start, generation_mw=first_half_mw)]
    rows.append(
        WindActual(
            start_time=start + timedelta(minutes=30),
            generation_mw=first_half_mw if second_half_mw is None else second_half_mw,
        )
    )
    return rows


class MemoryRedis:
    """The subset of redis-py the app uses, held in a dict."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    def delete(self, *keys: str) -> int:
        return sum(self.values.pop(key, None) is not None for key in keys)

    def scan_iter(self, match: str = "*"):
        return iter([key for key in self.values if fnmatch.fnmatch(key, match)])

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        pass


class BrokenRedis(MemoryRedis):
    def _fail(self, *args, **kwargs):
        raise RedisConnectionError("redis is down")

    get = setex = delete = scan_iter = ping = _fail


def broken_redis() -> BrokenRedis:
    return BrokenRedis()
