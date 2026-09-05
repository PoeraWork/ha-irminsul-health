"""Tests for the health observation webhook."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.irminsul_health.models import IrminsulRuntimeData
from custom_components.irminsul_health.storage import ObservationStore
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


@pytest.mark.parametrize(
    ("metric", "value", "unit"),
    [("uric_acid", 426, "µmol/L"), ("blood_glucose", 108, "mg/dL")],
)
async def test_accept_observation(hass, metric, value, unit) -> None:
    """Accept a valid authorized observation."""
    store = MagicMock()
    store.async_add_many = AsyncMock(return_value=(1, 0))
    runtime = IrminsulRuntimeData(store=store)
    request = _request(
        {
            "schema_version": 1,
            "observations": [
                {
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "observed_at": "2026-09-05T08:30:00+08:00",
                }
            ],
        }
    )

    response = await async_handle_webhook(hass, runtime, "user", "test-token", request)

    assert response.status == 200
    assert json.loads(response.body) == {"accepted": 1, "duplicates": 0}
    observation = store.async_add_many.call_args.args[0][0]
    assert observation.metric == metric
    assert observation.value == (6.0 if metric == "blood_glucose" else 426)


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


def _reading(metric="weight", value=60, unit="kg"):
    return {
        "metric": metric,
        "value": value,
        "unit": unit,
        "observed_at": "2025-01-01T00:00:00Z",
    }


async def test_profile_policy_rejects_entire_batch(hass):
    """No partial writes when a batch includes a disabled metric."""
    store = ObservationStore(hass, "test-entry")
    store._store.async_delay_save = MagicMock()
    runtime = IrminsulRuntimeData(store, metric_policy=lambda: frozenset({"weight"}))
    request = _request(
        {
            "schema_version": 1,
            "observations": [_reading(), _reading("steps", 100, "steps")],
        }
    )
    response = await async_handle_webhook(hass, runtime, "user", "test-token", request)
    assert response.status == 403
    assert store.as_dict() == {"observations": []}
    store._store.async_delay_save.assert_not_called()


@pytest.mark.parametrize("unload", [False, True])
async def test_policy_rechecked_after_waiting_for_store_lock(hass, unload):
    """A request already parsed cannot bypass a subsequent disable or unload."""
    store = ObservationStore(hass, "test-entry")
    store._store.async_delay_save = MagicMock()
    allowed = frozenset({"weight"})
    checked = asyncio.Event()

    def policy():
        checked.set()
        return allowed

    runtime = IrminsulRuntimeData(store, metric_policy=policy)
    request = _request({"schema_version": 1, "observations": [_reading()]})
    await store._lock.acquire()
    task = asyncio.create_task(
        async_handle_webhook(hass, runtime, "user", "test-token", request)
    )
    try:
        await asyncio.wait_for(checked.wait(), timeout=5)
        if unload:
            runtime.accepting = False
        else:
            allowed = frozenset()
    finally:
        store._lock.release()
    response = await task
    assert response.status == (503 if unload else 403)
    assert store.as_dict() == {"observations": []}


async def test_profiles_have_independent_policies(hass):
    """One profile's whitelist never grants another profile permission."""
    for index, allowed in enumerate([frozenset({"weight"}), frozenset()]):
        store = ObservationStore(hass, f"entry-{index}")
        store._store.async_delay_save = MagicMock()
        runtime = IrminsulRuntimeData(
            store, metric_policy=lambda allowed=allowed: allowed
        )
        response = await async_handle_webhook(
            hass,
            runtime,
            f"user-{index}",
            "test-token",
            _request({"schema_version": 1, "observations": [_reading()]}),
        )
        assert response.status == (200 if index == 0 else 403)
