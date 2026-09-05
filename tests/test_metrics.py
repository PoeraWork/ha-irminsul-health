"""Catalog units, validation and explicit allow/deny policies."""

import json
from pathlib import Path

import pytest

from custom_components.irminsul_health.metrics import METRICS, enabled_metrics
from custom_components.irminsul_health.models import (
    ObservationValidationError,
    parse_observation,
)


@pytest.mark.parametrize("value", [50.85, 54.09, 108])
def test_glucose_legacy_rounding(value):
    """Existing uploads must keep the same normalized value on replay."""
    assert METRICS["blood_glucose"].normalize(value, "mg/dL") == round(value / 18.0, 2)


@pytest.mark.parametrize(
    "filename", ["strings.json", "translations/en.json", "translations/zh-Hans.json"]
)
def test_catalog_has_complete_translations(filename):
    root = Path(__file__).parents[1] / "custom_components" / "irminsul_health"
    translations = json.loads((root / filename).read_text(encoding="utf-8"))
    assert set(translations["selector"]["metrics"]["options"]) == set(METRICS)
    assert set(translations["entity"]["sensor"]) == {
        f"{key}{suffix}" for key in METRICS for suffix in ("", "_measured_at")
    }


@pytest.mark.parametrize("key", METRICS)
def test_every_metric_accepts_its_canonical_unit(key) -> None:
    metric = METRICS[key]
    observation = parse_observation(
        {
            "metric": key,
            "value": 10,
            "unit": metric.unit,
            "observed_at": "2026-01-01T12:00:00+08:00",
        }
    )
    assert observation.metric == key
    assert observation.unit == metric.unit
    assert observation.value == 10


@pytest.mark.parametrize(
    ("key", "value", "unit", "expected"),
    [
        ("weight", 100, "lb", 45.36),
        ("height", 1.75, "m", 175),
        ("body_temperature", 98.6, "°F", 37),
        ("sleep_duration", 7.5, "h", 450),
        ("active_energy", 418.4, "kJ", 100),
        ("active_distance", 1000, "m", 1),
        ("hrv_sdnn", 0.05, "s", 50),
        ("blood_glucose", 108, "mg/dL", 6),
    ],
)
def test_metric_specific_unit_conversions(key, value, unit, expected) -> None:
    assert METRICS[key].normalize(value, unit) == expected


@pytest.mark.parametrize(
    ("key", "value", "unit"),
    [
        ("steps", 10.5, "steps"),
        ("oxygen_saturation", 101, "%"),
        ("body_fat", -1, "%"),
        ("heart_rate", 0, "bpm"),
        ("hba1c", 50, "mmol/mol"),
        ("total_cholesterol", 100, "mg/dL"),
        ("sleep_duration", -5, "min"),
        ("height", 1e308, "m"),
    ],
)
def test_reject_ambiguous_or_invalid_input(key, value, unit) -> None:
    with pytest.raises((ObservationValidationError, ValueError)):
        METRICS[key].normalize(value, unit)


def test_legacy_defaults_and_explicit_empty_lists() -> None:
    assert enabled_metrics({}) == {"uric_acid", "blood_glucose"}
    assert enabled_metrics({"metric_mode": "whitelist", "metrics": []}) == set()
    assert enabled_metrics({"metric_mode": "blacklist", "metrics": []}) == set(METRICS)
    assert enabled_metrics({"metric_mode": "whitelist", "metrics": ["weight"]}) == {
        "weight"
    }
    assert "weight" not in enabled_metrics(
        {"metric_mode": "blacklist", "metrics": ["weight"]}
    )


@pytest.mark.parametrize(
    "options",
    [
        {"metric_mode": "invalid", "metrics": []},
        {"metric_mode": "blacklist", "metrics": ["unknown"]},
        {"metric_mode": "blacklist", "metrics": "weight"},
        {"metric_mode": "blacklist", "metrics": [{}]},
    ],
)
def test_invalid_policy_fails_closed(options) -> None:
    assert not enabled_metrics(options)
