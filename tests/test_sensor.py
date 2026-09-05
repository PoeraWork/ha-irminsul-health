"""Tests for independent metric sensors and stable existing entity IDs."""

from types import SimpleNamespace

from custom_components.irminsul_health.const import CONF_SUBJECT_ID, CONF_SUBJECT_NAME
from custom_components.irminsul_health.models import (
    IrminsulRuntimeData,
    parse_observation,
)
from custom_components.irminsul_health.sensor import (
    BloodGlucoseMeasuredAtSensor,
    BloodGlucoseSensor,
    UricAcidMeasuredAtSensor,
    UricAcidSensor,
    async_setup_entry,
)


def make_entry():
    """Create an entry without requiring a running integration."""
    readings = {
        metric: parse_observation(
            {
                "metric": metric,
                "value": value,
                "unit": unit,
                "observed_at": "2026-01-01T00:00:00Z",
            }
        )
        for metric, value, unit in (
            ("uric_acid", 400, "µmol/L"),
            ("blood_glucose", 5.6, "mmol/L"),
        )
    }
    return SimpleNamespace(
        data={CONF_SUBJECT_ID: "user", CONF_SUBJECT_NAME: "User"},
        runtime_data=IrminsulRuntimeData(store=SimpleNamespace(latest=readings.get)),
    )


def test_metric_values_and_existing_unique_ids() -> None:
    """Adding glucose must not rename or repurpose existing uric acid entities."""
    entry = make_entry()
    acid = UricAcidSensor(entry)
    glucose = BloodGlucoseSensor(entry)
    assert acid.unique_id == "user_uric_acid"
    assert glucose.unique_id == "user_blood_glucose"
    assert acid.native_value == 400
    assert glucose.native_value == 5.6
    assert acid.native_unit_of_measurement == "µmol/L"
    assert glucose.native_unit_of_measurement == "mmol/L"
    assert UricAcidMeasuredAtSensor(entry).unique_id == "user_uric_acid_measured_at"
    assert (
        BloodGlucoseMeasuredAtSensor(entry).unique_id
        == "user_blood_glucose_measured_at"
    )
    assert (
        BloodGlucoseMeasuredAtSensor(entry).native_value.isoformat()
        == "2026-01-01T00:00:00+00:00"
    )


async def test_setup_adds_both_metrics(hass) -> None:
    """Set up value and measurement-time sensors for each supported metric."""
    entities = []
    await async_setup_entry(hass, make_entry(), entities.extend)
    assert len(entities) == 4


def test_new_metric_without_observations_is_unknown() -> None:
    """An existing uric-acid-only profile must not display a glucose value."""
    entry = make_entry()
    entry.runtime_data.store.latest = lambda metric: None
    assert BloodGlucoseSensor(entry).native_value is None
    assert BloodGlucoseMeasuredAtSensor(entry).native_value is None
