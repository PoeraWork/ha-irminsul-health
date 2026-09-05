"""Bounded observation storage for Irminsul Health."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MAX_OBSERVATIONS, SAVE_DELAY_SECONDS, STORAGE_VERSION
from .models import Observation

_LOGGER = logging.getLogger(__name__)


class ObservationConflictError(ValueError):
    """Raised when an external ID is reused with different content."""


class ObservationStore:
    """Persist exact low-frequency health observations."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the store."""
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
            private=True,
            atomic_writes=True,
        )
        self._observations: list[Observation] = []
        self._by_id: dict[str, Observation] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load observations from disk."""
        data = await self._store.async_load() or {}
        loaded: list[Observation] = []
        for item in data.get("observations", []):
            try:
                loaded.append(Observation.from_dict(item))
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Skipped an invalid stored observation")

        self._observations = sorted(
            loaded, key=lambda observation: observation.observed_at
        )[-MAX_OBSERVATIONS:]
        self._by_id = {
            observation.observation_id: observation
            for observation in self._observations
        }

    async def async_add_many(self, observations: list[Observation]) -> tuple[int, int]:
        """Add observations and return accepted and duplicate counts."""
        accepted = 0
        duplicates = 0
        async with self._lock:
            new_items: list[Observation] = []
            batch_by_id: dict[str, Observation] = {}
            for observation in observations:
                existing = self._by_id.get(observation.observation_id)
                if existing is not None:
                    if existing != observation:
                        raise ObservationConflictError(
                            "external_id is already used by a different observation"
                        )
                    duplicates += 1
                    continue

                existing = batch_by_id.get(observation.observation_id)
                if existing is not None:
                    if existing != observation:
                        raise ObservationConflictError(
                            "external_id is reused with different content in this batch"
                        )
                    duplicates += 1
                    continue
                batch_by_id[observation.observation_id] = observation
                new_items.append(observation)

            accepted = len(new_items)
            if accepted:
                self._observations.extend(new_items)
                self._by_id.update(batch_by_id)
                self._observations.sort(key=lambda item: item.observed_at)
                removed = self._observations[:-MAX_OBSERVATIONS]
                self._observations = self._observations[-MAX_OBSERVATIONS:]
                for observation in removed:
                    self._by_id.pop(observation.observation_id, None)
                self._store.async_delay_save(self.as_dict, SAVE_DELAY_SECONDS)

        return accepted, duplicates

    def latest(self, metric: str) -> Observation | None:
        """Return the newest observation for a metric."""
        return next(
            (
                observation
                for observation in reversed(self._observations)
                if observation.metric == metric
            ),
            None,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the storage representation."""
        return {
            "observations": [
                observation.as_dict() for observation in self._observations
            ]
        }

    async def async_remove(self) -> None:
        """Remove stored observations."""
        await self._store.async_remove()
