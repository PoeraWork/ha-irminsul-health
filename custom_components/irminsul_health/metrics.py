"""Supported scalar measurements and per-profile metric policies."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .const import CONF_METRIC_MODE, CONF_METRICS, MODE_BLACKLIST, MODE_WHITELIST


@dataclass(frozen=True, slots=True)
class Metric:
    """Describe input units and technical bounds, not clinical reference ranges."""

    key: str
    unit: str
    icon: str
    precision: int = 2
    zero_allowed: bool = False
    maximum: float | None = None
    integer: bool = False
    time_kind: str = "instant"
    conversions: dict[str, tuple[float, float]] = field(default_factory=dict)

    def normalize(self, value: float, unit: Any) -> float:
        """Validate the explicit unit and convert without inferring a metric."""
        if not isinstance(unit, str):
            raise ValueError("unit is required")
        unit_key = unit.strip().replace("μ", "µ").lower()
        canonical = self.unit.lower()
        if unit_key == canonical:
            converted = value
        elif self.key == "blood_glucose" and unit_key == "mg/dl":
            # Keep legacy rounding and replay identities exactly unchanged.
            converted = value / 18.0
        elif unit_key in self.conversions:
            factor, offset = self.conversions[unit_key]
            converted = value * factor + offset
        else:
            raise ValueError(f"unsupported unit for {self.key}; expected {self.unit}")
        if not math.isfinite(converted):
            raise ValueError("converted value must be finite")
        if converted < 0 or (converted == 0 and not self.zero_allowed):
            raise ValueError("value is outside the supported numeric range")
        if self.maximum is not None and converted > self.maximum:
            raise ValueError("value is outside the supported numeric range")
        if self.integer and not float(converted).is_integer():
            raise ValueError(f"{self.key} must be an integer")
        # Preserve the precision of the existing uric acid storage contract.
        converted = round(converted, 2)
        if converted == 0 and not self.zero_allowed:
            raise ValueError("value must remain positive after rounding")
        return converted


_LENGTH = {"m": (100.0, 0.0), "in": (2.54, 0.0)}
_DURATION = {"s": (1 / 60, 0.0), "h": (60.0, 0.0)}
_DEFINITIONS = (
    Metric(
        "uric_acid",
        "µmol/L",
        "mdi:test-tube",
        precision=0,
        maximum=3000,
        conversions={"umol/l": (1.0, 0.0), "mg/dl": (59.48, 0.0)},
    ),
    Metric(
        "blood_glucose", "mmol/L", "mdi:water", conversions={"mg/dl": (1 / 18.0, 0.0)}
    ),
    Metric("height", "cm", "mdi:human-male-height", conversions=_LENGTH),
    Metric(
        "weight",
        "kg",
        "mdi:scale-bathroom",
        conversions={"g": (0.001, 0.0), "lb": (0.45359237, 0.0)},
    ),
    Metric("bmi", "kg/m²", "mdi:human", conversions={"kg/m2": (1.0, 0.0)}),
    Metric("body_fat", "%", "mdi:percent", zero_allowed=True, maximum=100),
    Metric("waist", "cm", "mdi:tape-measure", conversions=_LENGTH),
    Metric(
        "body_temperature",
        "°C",
        "mdi:thermometer",
        conversions={"°f": (5 / 9, -32 * 5 / 9)},
    ),
    Metric("heart_rate", "bpm", "mdi:heart-pulse", precision=0),
    Metric("resting_heart_rate", "bpm", "mdi:heart", precision=0),
    Metric(
        "hrv_sdnn",
        "ms",
        "mdi:heart-flash",
        zero_allowed=True,
        conversions={"s": (1000.0, 0.0)},
    ),
    Metric(
        "oxygen_saturation", "%", "mdi:water-percent", maximum=100, zero_allowed=True
    ),
    Metric("respiratory_rate", "breaths/min", "mdi:lungs"),
    Metric("blood_pressure_systolic", "mmHg", "mdi:heart-pulse", precision=0),
    Metric("blood_pressure_diastolic", "mmHg", "mdi:heart-pulse", precision=0),
    Metric("hba1c", "%", "mdi:test-tube", maximum=100),
    Metric("total_cholesterol", "mmol/L", "mdi:test-tube"),
    Metric("triglycerides", "mmol/L", "mdi:test-tube"),
    Metric("hdl_cholesterol", "mmol/L", "mdi:test-tube"),
    Metric("ldl_cholesterol", "mmol/L", "mdi:test-tube"),
    Metric(
        "steps",
        "steps",
        "mdi:walk",
        precision=0,
        zero_allowed=True,
        integer=True,
        time_kind="daily_snapshot",
    ),
    Metric(
        "active_distance",
        "km",
        "mdi:map-marker-distance",
        zero_allowed=True,
        time_kind="daily_snapshot",
        conversions={"m": (0.001, 0.0), "mi": (1.609344, 0.0)},
    ),
    Metric(
        "active_energy",
        "kcal",
        "mdi:fire",
        zero_allowed=True,
        time_kind="daily_snapshot",
        conversions={"kj": (1 / 4.184, 0.0)},
    ),
    Metric(
        "exercise_duration",
        "min",
        "mdi:run",
        zero_allowed=True,
        time_kind="daily_snapshot",
        conversions=_DURATION,
    ),
    Metric(
        "sleep_duration",
        "min",
        "mdi:sleep",
        zero_allowed=True,
        time_kind="sleep_session",
        conversions=_DURATION,
    ),
    Metric(
        "sleep_deep",
        "min",
        "mdi:sleep",
        zero_allowed=True,
        time_kind="sleep_session",
        conversions=_DURATION,
    ),
    Metric(
        "sleep_light",
        "min",
        "mdi:sleep",
        zero_allowed=True,
        time_kind="sleep_session",
        conversions=_DURATION,
    ),
    Metric(
        "sleep_rem",
        "min",
        "mdi:sleep",
        zero_allowed=True,
        time_kind="sleep_session",
        conversions=_DURATION,
    ),
)
METRICS = {metric.key: metric for metric in _DEFINITIONS}
LEGACY_METRICS = ("uric_acid", "blood_glucose")
DEFAULT_METRICS = ("weight", "heart_rate", "steps", "sleep_duration")


def enabled_metrics(options: Mapping[str, Any]) -> frozenset[str]:
    """Use legacy defaults for old entries and fail closed for invalid policies."""
    mode = options.get(CONF_METRIC_MODE, MODE_WHITELIST)
    selected = options.get(CONF_METRICS, LEGACY_METRICS)
    if not isinstance(selected, (list, tuple)) or any(
        not isinstance(key, str) or key not in METRICS for key in selected
    ):
        return frozenset()
    if mode == MODE_WHITELIST:
        return frozenset(selected)
    if mode == MODE_BLACKLIST:
        return frozenset(METRICS).difference(selected)
    return frozenset()
