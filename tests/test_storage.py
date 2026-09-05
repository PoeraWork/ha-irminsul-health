"""Tests for bounded observation storage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.irminsul_health.models import parse_observation
from custom_components.irminsul_health.storage import (
    ObservationConflictError,
    ObservationStore,
)


async def test_add_and_deduplicate(hass) -> None:
    """Store an observation once when a sender retries."""
    store = ObservationStore(hass, "test-entry")
    store._store.async_delay_save = MagicMock()
    observation = parse_observation(
        {
            "metric": "uric_acid",
            "value": 426,
            "unit": "µmol/L",
            "observed_at": "2026-09-05T08:30:00+08:00",
            "external_id": "meter-1",
        }
    )

    assert await store.async_add_many([observation]) == (1, 0)
    assert await store.async_add_many([observation]) == (0, 1)
    assert store.latest("uric_acid") == observation
    store._store.async_delay_save.assert_called_once()


async def test_reject_external_id_conflict(hass) -> None:
    """Reject reusing an external ID for different content."""
    store = ObservationStore(hass, "test-entry")
    store._store.async_delay_save = MagicMock()
    first = parse_observation(
        {
            "metric": "uric_acid",
            "value": 426,
            "unit": "µmol/L",
            "observed_at": "2026-09-05T08:30:00+08:00",
            "external_id": "meter-1",
        }
    )
    conflicting = parse_observation(
        {
            "metric": "uric_acid",
            "value": 500,
            "unit": "µmol/L",
            "observed_at": "2026-09-05T08:31:00+08:00",
            "external_id": "meter-1",
        }
    )

    await store.async_add_many([first])
    with pytest.raises(ObservationConflictError):
        await store.async_add_many([conflicting])


async def test_load_uric_acid_profile_and_add_glucose(hass) -> None:
    """Keep old data when an existing profile starts receiving another metric."""
    acid = parse_observation(
        {
            "metric": "uric_acid",
            "value": 400,
            "unit": "µmol/L",
            "observed_at": "2026-01-01T00:00:00Z",
        }
    )
    glucose = parse_observation(
        {
            "metric": "blood_glucose",
            "value": 5.6,
            "unit": "mmol/L",
            "observed_at": "2026-01-02T00:00:00Z",
        }
    )
    store = ObservationStore(hass, "test-entry")
    store._store.async_load = AsyncMock(return_value={"observations": [acid.as_dict()]})
    store._store.async_delay_save = MagicMock()
    await store.async_load()
    assert store.latest("blood_glucose") is None
    assert await store.async_add_many([glucose]) == (1, 0)
    assert store.latest("uric_acid") == acid
    assert store.latest("blood_glucose") == glucose
    assert store.as_dict() == {"observations": [acid.as_dict(), glucose.as_dict()]}
    assert await store.async_add_many([acid, glucose]) == (0, 2)


async def test_retention_is_per_metric(hass):
    """Frequent activity updates cannot evict an older lab observation."""
    store = ObservationStore(hass, "test-entry")
    store._store.async_delay_save = MagicMock()
    acid = parse_observation(
        {
            "metric": "uric_acid",
            "value": 400,
            "unit": "µmol/L",
            "observed_at": "2025-01-01T00:00:00Z",
        }
    )
    start = datetime(2025, 1, 2, tzinfo=UTC)
    steps = [
        parse_observation(
            {
                "metric": "steps",
                "value": i,
                "unit": "steps",
                "observed_at": (start + timedelta(minutes=i)).isoformat(),
            }
        )
        for i in range(505)
    ]
    await store.async_add_many([acid, *steps])
    assert store.latest("uric_acid") == acid
    assert store.latest("steps") == steps[-1]
    records = store.as_dict()["observations"]
    assert len(records) == 501
    assert records[1] == steps[5].as_dict()


async def test_equal_timestamps_stay_stable_across_flush_and_load(hass):
    """Same-time measurements retain insertion order and the same latest value."""
    store = ObservationStore(hass, "test-entry")
    store._store.async_delay_save = MagicMock()
    store._store.async_save = AsyncMock()
    readings = [
        parse_observation(
            {
                "metric": "weight",
                "value": value,
                "unit": "kg",
                "observed_at": "2025-01-01T00:00:00Z",
                "external_id": str(value),
            }
        )
        for value in (60, 61)
    ]
    for reading in readings:
        await store.async_add_many([reading])
    await store.async_flush()
    saved = store._store.async_save.call_args.args[0]
    assert saved["observations"] == [item.as_dict() for item in readings]
    store._store.async_load = AsyncMock(return_value=saved)
    await store.async_load()
    assert store.latest("weight") == readings[-1]
    assert await store.async_add_many(readings) == (0, 2)
