"""Tests for the health observation webhook."""

import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.irminsul_health.models import IrminsulRuntimeData
from custom_components.irminsul_health.webhook import async_handle_webhook


def _request(payload: object, token: str = "test-token") -> MagicMock:
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}
    body = json.dumps(payload).encode()
    request.content_length = len(body)
    request.content.read = AsyncMock(return_value=body)
    return request


async def test_reject_missing_token(hass) -> None:
    """Reject a request without the ingest token."""
    store = MagicMock()
    store.async_add_many = AsyncMock()
    runtime = IrminsulRuntimeData(store=store)
    request = _request({}, token="wrong-token")

    response = await async_handle_webhook(hass, runtime, "user", "test-token", request)

    assert response.status == 401
    store.async_add_many.assert_not_awaited()


async def test_accept_observation(hass) -> None:
    """Accept a valid authorized observation."""
    store = MagicMock()
    store.async_add_many = AsyncMock(return_value=(1, 0))
    runtime = IrminsulRuntimeData(store=store)
    request = _request(
        {
            "schema_version": 1,
            "observations": [
                {
                    "metric": "uric_acid",
                    "value": 426,
                    "unit": "µmol/L",
                    "observed_at": "2026-09-05T08:30:00+08:00",
                }
            ],
        }
    )

    response = await async_handle_webhook(hass, runtime, "user", "test-token", request)

    assert response.status == 200
    assert json.loads(response.body) == {"accepted": 1, "duplicates": 0}


async def test_reject_deep_json(hass) -> None:
    """Return a client error for JSON that exceeds the parser depth."""
    store = MagicMock()
    runtime = IrminsulRuntimeData(store=store)
    request = MagicMock()
    request.headers = {"Authorization": "Bearer test-token"}
    request.content_length = 2401
    request.content.read = AsyncMock(return_value=(b"[" * 1200 + b"0" + b"]" * 1200))

    response = await async_handle_webhook(hass, runtime, "user", "test-token", request)

    assert response.status == 400
