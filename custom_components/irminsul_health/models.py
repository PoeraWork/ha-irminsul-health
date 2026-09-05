"""Data models and validation for Irminsul Health."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from .const import METRIC_URIC_ACID, UNIT_URIC_ACID

MG_DL_TO_UMOL_L = 59.48
MAX_NOTE_LENGTH = 500
MAX_EXTERNAL_ID_LENGTH = 200


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

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to observation changes."""
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    def notify(self) -> None:
        """Notify entities that stored observations changed."""
        for listener in tuple(self.listeners):
            listener()


def parse_observation(payload: Any) -> Observation:
    """Validate and normalize one observation payload."""
    if not isinstance(payload, dict):
        raise ObservationValidationError("observation must be an object")

    metric = payload.get("metric")
    if metric != METRIC_URIC_ACID:
        raise ObservationValidationError("metric must be uric_acid")

    value = _parse_number(payload.get("value"))
    unit = payload.get("unit")
    value = _normalize_uric_acid(value, unit)

    observed_at = _parse_timestamp(payload.get("observed_at"))
    external_id = _parse_optional_text(
        payload.get("external_id"), "external_id", MAX_EXTERNAL_ID_LENGTH
    )
    note = _parse_optional_text(payload.get("note"), "note", MAX_NOTE_LENGTH)

    identity = external_id or f"{metric}|{value:.6f}|{observed_at}"
    observation_id = sha256(identity.encode()).hexdigest()

    return Observation(
        observation_id=observation_id,
        metric=metric,
        value=value,
        unit=UNIT_URIC_ACID,
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


def _parse_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ObservationValidationError("observed_at is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ObservationValidationError("observed_at must be ISO 8601") from err
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservationValidationError("observed_at must include a time-zone offset")
    return parsed.astimezone(UTC).isoformat()


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
