"""Tests for bounded observation storage."""

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
