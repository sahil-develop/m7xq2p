from datetime import date

import httpx
import pytest

from app.elexon import ElexonAPIError, ElexonClient, actual_values, forecast_values


def test_forecast_request_uses_publish_day_and_parses_wind_data():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/datasets/WINDFOR/stream")
        assert request.url.params["publishDateTimeFrom"] == "2026-01-01T00:00:00Z"
        return httpx.Response(
            200,
            json=[
                {
                    "publishTime": "2026-01-01T10:30:00Z",
                    "startTime": "2026-01-02T10:00:00Z",
                    "generation": 500,
                }
            ],
        )

    client = ElexonClient(httpx.Client(transport=httpx.MockTransport(handler)))
    rows = client.fetch_forecasts(date(2026, 1, 1))

    assert len(rows) == 1
    assert forecast_values(rows[0])["generation_mw"] == 500


def test_invalid_generation_is_reported():
    with pytest.raises(ElexonAPIError, match="invalid generation"):
        actual_values({"startTime": "2026-01-01T00:00:00Z", "generation": "unknown"})
