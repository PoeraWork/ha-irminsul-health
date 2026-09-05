"""Data models and validation for Irminsul Health."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from .const import (
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from .metrics import METRICS

MAX_NOTE_LENGTH = 500
MAX_EXTERNAL_ID_LENGTH = 200
MAX_FUTURE_SKEW = timedelta(minutes=10)


class ObservationValidationError(ValueError):
    """Raised when an observation is invalid."""


class MetricNotAllowedError(ValueError):
    """Raised when a profile does not accept an observation's metric."""


class ProfileUnavailableError(RuntimeError):
    """Raised when a profile is unloading."""


@dataclass(frozen=True, slots=True)
class Observation:
    """A normalized health observation."""

    observation_id: str
    metric: str
    value: float
    unit: str
    observed_at: str
    external_id: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        """Restore an observation from storage."""
        return cls(
            observation_id=str(data["observation_id"]),
            metric=str(data["metric"]),
            value=float(data["value"]),
            unit=str(data["unit"]),
            observed_at=str(data["observed_at"]),
            external_id=data.get("external_id"),
            note=data.get("note"),
        )


@dataclass(slots=True)
class IrminsulRuntimeData:
    """Runtime data shared by platforms and the webhook."""

    store: Any
    metric_policy: Callable[[], frozenset[str]] = field(
        default=lambda: frozenset(METRICS)
    )
    accepting: bool = True
    webhook_id: str | None = None
    listeners: set[Callable[[], None]] = field(default_factory=set)
    rate_limiter: RequestRateLimiter = field(
        default_factory=lambda: RequestRateLimiter()
    )

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to observation changes."""
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    def notify(self) -> None:
        """Notify entities that stored observations changed."""
        for listener in tuple(self.listeners):
            listener()

    def check_writable(self, observations: list[Observation]) -> None:
        """Check the current policy again at the storage write boundary."""
        if not self.accepting:
            raise ProfileUnavailableError("health profile is reloading")
        allowed = self.metric_policy()
        if any(observation.metric not in allowed for observation in observations):
            raise MetricNotAllowedError(
                "one or more metrics are disabled for this profile"
            )


@dataclass(slots=True)
class RequestRateLimiter:
    """Limit accepted webhook attempts for one health profile."""

    maximum: int = RATE_LIMIT_REQUESTS
    window_seconds: int = RATE_LIMIT_WINDOW_SECONDS
    _attempts: deque[float] = field(default_factory=deque)

    def consume(self, now: float) -> int | None:
        """Record an attempt or return the retry delay in seconds."""
        cutoff = now - self.window_seconds
        while self._attempts and self._attempts[0] <= cutoff:
            self._attempts.popleft()
        if len(self._attempts) >= self.maximum:
            return max(1, math.ceil(self._attempts[0] + self.window_seconds - now))
        self._attempts.append(now)
        return None


def parse_observation(payload: Any, *, now: datetime | None = None) -> Observation:
    """Validate and normalize one observation payload."""
    if not isinstance(payload, dict):
        raise ObservationValidationError("observation must be an object")

    metric = payload.get("metric")
    if not isinstance(metric, str) or metric not in METRICS:
        raise ObservationValidationError("unsupported metric")

    value = _parse_number(payload.get("value"))
    unit = payload.get("unit")
    try:
        value = METRICS[metric].normalize(value, unit)
    except ValueError as err:
        raise ObservationValidationError(str(err)) from err
    normalized_unit = METRICS[metric].unit

    observed_at = _parse_timestamp(payload.get("observed_at"), now=now)
    external_id = _parse_optional_text(
        payload.get("external_id"), "external_id", MAX_EXTERNAL_ID_LENGTH
    )
    note = _parse_optional_text(payload.get("note"), "note", MAX_NOTE_LENGTH)

    identity = (
        f"{metric}|external:{external_id}"
        if external_id
        else f"{metric}|{value:.6f}|{observed_at}"
    )
    observation_id = sha256(identity.encode()).hexdigest()

    return Observation(
        observation_id=observation_id,
        metric=metric,
        value=value,
        unit=normalized_unit,
        observed_at=observed_at,
        external_id=external_id,
        note=note,
    )


def _parse_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ObservationValidationError("value must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as err:
        raise ObservationValidationError("value must be a number") from err
    if not math.isfinite(parsed):
        raise ObservationValidationError("value must be finite")
    return parsed


def _parse_timestamp(value: Any, *, now: datetime | None = None) -> str:
    if not isinstance(value, str):
        raise ObservationValidationError("observed_at is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ObservationValidationError("observed_at must be ISO 8601") from err
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationValidationError("observed_at must include a time-zone offset")
    parsed = parsed.astimezone(UTC)
    current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    if parsed > current + MAX_FUTURE_SKEW:
        raise ObservationValidationError("observed_at is too far in the future")
    return parsed.isoformat()


def _parse_optional_text(value: Any, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ObservationValidationError(f"{field_name} must be text")
    value = value.strip()
    if not value:
        return None
    if len(value) > maximum:
        raise ObservationValidationError(
            f"{field_name} must be at most {maximum} characters"
        )
    return value
