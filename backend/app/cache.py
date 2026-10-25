"""Redis read-through cache for the dashboard payload.

Keys: `wind-dashboard:v2:cutoff=HHMM`, one per decision cutoff. Entries expire after
CACHE_TTL_SECONDS and are explicitly deleted after every successful ingestion. Redis
is an optimisation only: any Redis failure is logged and the request is served from
Postgres instead.
"""

import json
import logging
from collections.abc import Generator
from datetime import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)

CACHE_PREFIX = "wind-dashboard:v2:"
CACHE_TTL_SECONDS = 3600


def cache_key(cutoff: time) -> str:
    return f"{CACHE_PREFIX}cutoff={cutoff.strftime('%H%M')}"


def create_redis() -> Redis | None:
    url = get_settings().redis_url
    if not url:
        return None
    return Redis.from_url(url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)


def get_redis() -> Generator[Redis | None, None, None]:
    """FastAPI dependency; closes the connection pool after the request."""
    client = create_redis()
    try:
        yield client
    finally:
        if client is not None:
            client.close()


def read_dashboard_cache(client: Redis | None, cutoff: time) -> dict[str, Any] | None:
    if client is None:
        return None
    try:
        value = client.get(cache_key(cutoff))
    except RedisError:
        logger.warning("Redis read failed; serving dashboard from Postgres", exc_info=True)
        return None
    return json.loads(value) if value is not None else None


def write_dashboard_cache(client: Redis | None, cutoff: time, payload: dict[str, Any]) -> None:
    if client is None:
        return
    try:
        client.setex(cache_key(cutoff), CACHE_TTL_SECONDS, json.dumps(payload))
    except RedisError:
        logger.warning("Redis write failed; dashboard response not cached", exc_info=True)


def invalidate_dashboard_cache(client: Redis | None) -> int:
    """Delete every cached dashboard variant. Returns the number of keys removed."""
    if client is None:
        return 0
    try:
        keys = list(client.scan_iter(match=f"{CACHE_PREFIX}*"))
        return client.delete(*keys) if keys else 0
    except RedisError:
        # Stale entries still expire via TTL; surface the problem without failing the sync.
        logger.error(
            "Redis invalidation failed; cached dashboards expire within TTL", exc_info=True
        )
        return 0
