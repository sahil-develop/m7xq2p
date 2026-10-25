from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://wind_insights:local-dev-only@localhost:5432/wind_insights"
    redis_url: str = "redis://localhost:6379/0"
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    ingestion_token: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
