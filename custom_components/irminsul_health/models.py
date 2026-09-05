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
    METRIC_BLOOD_GLUCOSE,
    METRIC_URIC_ACID,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    UNIT_BLOOD_GLUCOSE,
    UNIT_URIC_ACID,
)

MG_DL_TO_UMOL_L = 59.48
GLUCOSE_MG_DL_PER_MMOL_L = 18.0
MAX_NOTE_LENGTH = 500
MAX_EXTERNAL_ID_LENGTH = 200
MAX_FUTURE_SKEW = timedelta(minutes=10)


class ObservationValidationError(ValueError):
    """Raised when an observation is invalid."""


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
    if metric not in (METRIC_URIC_ACID, METRIC_BLOOD_GLUCOSE):
        raise ObservationValidationError("metric must be uric_acid or blood_glucose")

    value = _parse_number(payload.get("value"))
    unit = payload.get("unit")
    if metric == METRIC_URIC_ACID:
        value = _normalize_uric_acid(value, unit)
        normalized_unit = UNIT_URIC_ACID
    else:
        value = _normalize_blood_glucose(value, unit)
        normalized_unit = UNIT_BLOOD_GLUCOSE

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


def _normalize_uric_acid(value: float, unit: Any) -> float:
    if not isinstance(unit, str):
        raise ObservationValidationError("unit is required")

    normalized_unit = unit.strip().replace("μ", "µ").lower()
    if normalized_unit in {"µmol/l", "umol/l"}:
        normalized_value = value
    elif normalized_unit == "mg/dl":
        normalized_value = value * MG_DL_TO_UMOL_L
    else:
        raise ObservationValidationError("unit must be µmol/L or mg/dL")

    if not 0 < normalized_value <= 3000:
        raise ObservationValidationError("uric acid value is outside 0-3000 µmol/L")
    return round(normalized_value, 2)


def _normalize_blood_glucose(value: float, unit: Any) -> float:
    """Normalize glucose without inferring a diagnosis or measurement type."""
    if not isinstance(unit, str):
        raise ObservationValidationError("unit is required")
    normalized_unit = unit.strip().lower()
    if normalized_unit == "mmol/l":
        normalized_value = value
    elif normalized_unit == "mg/dl":
        normalized_value = value / GLUCOSE_MG_DL_PER_MMOL_L
    else:
        raise ObservationValidationError("blood glucose unit must be mmol/L or mg/dL")
    normalized_value = round(normalized_value, 2)
    if normalized_value <= 0:
        raise ObservationValidationError(
            "blood glucose must be positive after rounding"
        )
    return normalized_value


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
