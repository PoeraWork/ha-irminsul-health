"""Bounded observation storage for Irminsul Health."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MAX_OBSERVATIONS, STORAGE_VERSION
from .models import Observation

_LOGGER = logging.getLogger(__name__)


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
        self._ids: set[str] = set()
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
        self._ids = {observation.observation_id for observation in self._observations}

    async def async_add_many(self, observations: list[Observation]) -> tuple[int, int]:
        """Add observations and return accepted and duplicate counts."""
        accepted = 0
        duplicates = 0
        async with self._lock:
            for observation in observations:
                if observation.observation_id in self._ids:
                    duplicates += 1
                    continue
                self._observations.append(observation)
                self._ids.add(observation.observation_id)
                accepted += 1

            if accepted:
                self._observations.sort(key=lambda item: item.observed_at)
                removed = self._observations[:-MAX_OBSERVATIONS]
                self._observations = self._observations[-MAX_OBSERVATIONS:]
                for observation in removed:
                    self._ids.discard(observation.observation_id)
                await self._store.async_save(self.as_dict())

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
