from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import httpx

from app.config import get_settings

UTC = timezone.utc


class ElexonAPIError(RuntimeError):
    pass


class ElexonClient:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self.http_client = http_client or httpx.Client(timeout=30)
        self.base_url = get_settings().elexon_base_url.rstrip("/")

    def _get_records(self, dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self.http_client.get(f"{self.base_url}/datasets/{dataset}/stream", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ElexonAPIError(f"Elexon {dataset} response was not a JSON array")
        if any(not isinstance(row, dict) for row in payload):
            raise ElexonAPIError(f"Elexon {dataset} response contained an invalid record")
        return payload

    def fetch_actuals(self, day: date) -> list[dict[str, Any]]:
        rows = self._get_records(
            "FUELHH",
            {
                "settlementDateFrom": day.isoformat(),
                "settlementDateTo": day.isoformat(),
                "fuelType": "WIND",
            },
        )
        return [
            row
            for row in rows
            if row.get("fuelType") == "WIND" and row.get("settlementDate") == day.isoformat()
        ]

    def fetch_forecasts(self, publish_day: date) -> list[dict[str, Any]]:
        day_start = datetime.combine(publish_day, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
        rows = self._get_records(
            "WINDFOR",
            {
                "publishDateTimeFrom": day_start.isoformat().replace("+00:00", "Z"),
                "publishDateTimeTo": day_end.isoformat().replace("+00:00", "Z"),
            },
        )
        return [
            row
            for row in rows
            if _parse_datetime(row.get("publishTime")).date() == publish_day
        ]


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
