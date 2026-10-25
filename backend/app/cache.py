from typing import Any

from redis import Redis

from app.config import get_settings

CACHE_KEY = "wind-dashboard:v1:jan-2026"
CACHE_TTL_SECONDS = 300


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def read_dashboard_cache(client: Redis) -> dict[str, Any] | None:
    value = client.get(CACHE_KEY)
    if value is None:
        return None
    import json

    return json.loads(value)


def write_dashboard_cache(client: Redis, payload: dict[str, Any]) -> None:
    import json

    client.setex(CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(payload, default=str))


def invalidate_dashboard_cache(client: Redis) -> None:
    client.delete(CACHE_KEY)
