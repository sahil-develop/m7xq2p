"""Config, cache-failure, Celery and static-hosting behaviour."""

import importlib
import ssl
from datetime import time

import httpx
import pytest
from factories import MemoryRedis, broken_redis
from fastapi.testclient import TestClient

from app.cache import (
    cache_key,
    invalidate_dashboard_cache,
    read_dashboard_cache,
    write_dashboard_cache,
)
from app.config import Settings


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@host:5432/db", "postgresql://u:p@host:5432/db"],
)
def test_hosted_postgres_urls_use_psycopg_driver(url):
    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@host:5432/db"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("rediss://:p@host:6379", "rediss://:p@host:6379?ssl_cert_reqs=none"),
        ("rediss://:p@host:6379/0?a=1", "rediss://:p@host:6379/0?a=1&ssl_cert_reqs=none"),
        ("rediss://h:6379?ssl_cert_reqs=required", "rediss://h:6379?ssl_cert_reqs=required"),
        ("redis://localhost:6379/0", "redis://localhost:6379/0"),
        ("", ""),
    ],
)
def test_tls_redis_urls_get_heroku_compatible_cert_setting(url, expected):
    assert Settings(redis_url=url).redis_url == expected


def test_tls_redis_url_is_accepted_by_redis_and_celery_clients():
    from celery import Celery
    from redis import Redis

    url = Settings(redis_url="rediss://:p@example.invalid:6379").redis_url
    Redis.from_url(url)  # parses without connecting
    backend = Celery("probe", broker=url, backend=url).backend  # ValueError if ssl_cert_reqs bad
    assert backend.connparams["ssl_cert_reqs"] == ssl.CERT_NONE


def test_cors_origins_accept_comma_separated_env_value():
    assert Settings(cors_origins="https://a.example, https://b.example").cors_origins == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_origins_env_var_is_not_parsed_as_json(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]


def test_cache_helpers_are_noops_without_redis():
    write_dashboard_cache(None, time(9), {"a": 1})
    assert read_dashboard_cache(None, time(9)) is None
    assert invalidate_dashboard_cache(None) == 0


def test_cache_failures_are_swallowed():
    client = broken_redis()
    write_dashboard_cache(client, time(9), {"a": 1})
    assert read_dashboard_cache(client, time(9)) is None
    assert invalidate_dashboard_cache(client) == 0


def test_invalidation_only_touches_dashboard_keys():
    client = MemoryRedis()
    write_dashboard_cache(client, time(9), {"a": 1})
    write_dashboard_cache(client, time(11), {"a": 2})
    client.setex("celery-task-meta-1", 60, "{}")

    assert invalidate_dashboard_cache(client) == 2
    assert list(client.values) == ["celery-task-meta-1"]
    assert cache_key(time(9, 30)) == "wind-dashboard:v2:cutoff=0930"


def test_celery_task_retries_on_network_errors(monkeypatch):
    from app import tasks

    assert httpx.TransportError in tasks.refresh_january_data.autoretry_for
    assert httpx.HTTPStatusError in tasks.refresh_january_data.autoretry_for
    monkeypatch.setattr(tasks, "sync_january_data", lambda: {"forecasts": 1, "actuals": 2})
    assert tasks.refresh_january_data.apply().get() == {"forecasts": 1, "actuals": 2}


def test_built_frontend_is_served_with_spa_fallback(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('ok')")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    from app import config, main

    config.get_settings.cache_clear()
    try:
        reloaded = importlib.reload(main)
        with TestClient(reloaded.app) as client:
            assert client.get("/").text == "<html>spa</html>"
            assert client.get("/some/deep/link").text == "<html>spa</html>"
            assert client.get("/assets/app.js").text == "console.log('ok')"
            assert client.get("/../../etc/passwd").text == "<html>spa</html>"
            assert client.get("/api/v1/unknown").status_code == 404
    finally:
        monkeypatch.delenv("STATIC_DIR")
        config.get_settings.cache_clear()
        importlib.reload(main)
