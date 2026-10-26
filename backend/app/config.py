from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://wind_forecast_insights:local-dev-only"
        "@localhost:5432/wind_forecast_insights"
    )
    # Empty disables caching and background jobs degrade to synchronous CLI runs.
    redis_url: str = ""
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    elexon_timeout_seconds: float = 60.0
    # NoDecode: read CORS_ORIGINS as a comma-separated string, not JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    ingestion_token: str | None = None
    # Directory holding the built React app; served by FastAPI when present.
    static_dir: str = "/app/static"

    @field_validator("database_url")
    @classmethod
    def normalise_database_url(cls, value: str) -> str:
        # Heroku and most hosted Postgres providers hand out postgres:// URLs.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @field_validator("redis_url")
    @classmethod
    def normalise_redis_url(cls, value: str) -> str:
        # Heroku Redis serves TLS with a self-signed certificate. Celery rejects a rediss://
        # URL without ssl_cert_reqs and redis-py would fail verification, so default to the
        # setting Heroku documents unless the URL already chooses one.
        if value.startswith("rediss://") and "ssl_cert_reqs=" not in value:
            return value + ("&" if "?" in value else "?") + "ssl_cert_reqs=none"
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
