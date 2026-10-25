from datetime import date

import httpx
import pytest
from factories import utc

from app.elexon import ElexonAPIError, ElexonClient, actual_values, forecast_values


def _client(handler) -> ElexonClient:
    return ElexonClient(httpx.Client(transport=httpx.MockTransport(handler)))


def test_forecast_request_uses_publish_window_and_parses_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/datasets/WINDFOR/stream")
        assert request.url.params["publishDateTimeFrom"] == "2026-01-01T00:00:00Z"
        assert request.url.params["publishDateTimeTo"] == "2026-01-01T23:59:59Z"
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

    [row] = _client(handler).fetch_forecasts(utc(2026, 1, 1), utc(2026, 1, 1, 23, 59, 59))

    assert forecast_values(row) == {
        "start_time": utc(2026, 1, 2, 10),
        "publish_time": utc(2026, 1, 1, 10, 30),
        "generation_mw": 500,
    }


def test_actuals_request_filters_to_wind():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["fuelType"] == "WIND"
        assert request.url.params["settlementDateFrom"] == "2026-01-02"
        assert request.url.params["settlementDateTo"] == "2026-02-01"
        return httpx.Response(
            200,
            json=[
                {"fuelType": "WIND", "startTime": "2026-01-02T00:00:00Z", "generation": 1},
                {"fuelType": "CCGT", "startTime": "2026-01-02T00:00:00Z", "generation": 2},
            ],
        )

    rows = _client(handler).fetch_actuals(date(2026, 1, 2), date(2026, 2, 1))

    assert [row["fuelType"] for row in rows] == ["WIND"]


def test_non_list_payload_is_rejected():
    client = _client(lambda request: httpx.Response(200, json={"error": "nope"}))

    with pytest.raises(ElexonAPIError, match="JSON array"):
        client.fetch_actuals(date(2026, 1, 2), date(2026, 1, 2))


def test_http_errors_propagate_for_retry():
    client = _client(lambda request: httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_forecasts(utc(2026, 1, 1), utc(2026, 1, 2))


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"startTime": "2026-01-01T00:00:00Z", "generation": "unknown"}, "invalid generation"),
        ({"startTime": "2026-01-01T00:00:00Z", "generation": -5}, "negative"),
        ({"startTime": "2026-01-01T00:00:00", "generation": 5}, "without a timezone"),
        ({"generation": 5}, "missing a timestamp"),
    ],
)
def test_invalid_records_are_reported(row, message):
    with pytest.raises(ElexonAPIError, match=message):
        actual_values(row)
