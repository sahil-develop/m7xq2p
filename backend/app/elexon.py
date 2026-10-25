"""Thin client for the two Elexon BMRS datasets this product uses."""

from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.config import get_settings


class ElexonAPIError(RuntimeError):
    """Elexon returned data we cannot trust; retrying will not help."""


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ElexonClient:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self.http_client = http_client or httpx.Client(timeout=settings.elexon_timeout_seconds)
        self.base_url = settings.elexon_base_url.rstrip("/")

    def close(self) -> None:
        self.http_client.close()

    def _get_records(self, dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        # raise_for_status raises httpx.HTTPStatusError, which the Celery task retries.
        response = self.http_client.get(f"{self.base_url}/datasets/{dataset}/stream", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ElexonAPIError(f"Elexon {dataset} response was not a JSON array of records")
        return payload

    def fetch_actuals(self, first_day: date, last_day: date) -> list[dict[str, Any]]:
        """FUELHH WIND outturn for settlement dates first_day..last_day inclusive."""
        rows = self._get_records(
            "FUELHH",
            {
                "settlementDateFrom": first_day.isoformat(),
                "settlementDateTo": last_day.isoformat(),
                "fuelType": "WIND",
            },
        )
        return [row for row in rows if row.get("fuelType") == "WIND"]

    def fetch_forecasts(self, published_from: datetime, published_to: datetime) -> list[dict]:
        """WINDFOR forecasts published in [published_from, published_to]."""
        return self._get_records(
            "WINDFOR",
            {
                "publishDateTimeFrom": _iso_z(published_from),
                "publishDateTimeTo": _iso_z(published_to),
            },
        )


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ElexonAPIError("Elexon record is missing a timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ElexonAPIError("Elexon returned a timestamp without a timezone")
    return parsed.astimezone(UTC)


def _parse_generation(value: Any) -> float:
    try:
        generation = float(value)
    except (TypeError, ValueError) as error:
        raise ElexonAPIError("Elexon record has an invalid generation value") from error
    if generation < 0:
        raise ElexonAPIError("Elexon record has negative wind generation")
    return generation


def forecast_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_time": _parse_datetime(row.get("startTime")),
        "publish_time": _parse_datetime(row.get("publishTime")),
        "generation_mw": _parse_generation(row.get("generation")),
    }


def actual_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_time": _parse_datetime(row.get("startTime")),
        "generation_mw": _parse_generation(row.get("generation")),
    }
