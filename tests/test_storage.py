"""Tests for bounded observation storage."""

from unittest.mock import MagicMock

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
