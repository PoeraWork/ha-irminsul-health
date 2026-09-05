"""Tests for independent metric sensors and stable existing entity IDs."""

from types import SimpleNamespace

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irminsul_health.const import (
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    DOMAIN,
)
from custom_components.irminsul_health.metrics import METRICS
from custom_components.irminsul_health.models import (
    IrminsulRuntimeData,
    parse_observation,
)
from custom_components.irminsul_health.sensor import (
    FILTER_DISABLED,
    HealthMeasuredAtSensor,
    HealthValueSensor,
    async_setup_entry,
    sync_metric_registry,
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
        entry_id="test-entry",
        options={},
        data={CONF_SUBJECT_ID: "user", CONF_SUBJECT_NAME: "User"},
        runtime_data=IrminsulRuntimeData(store=SimpleNamespace(latest=readings.get)),
    )


def test_metric_values_and_existing_unique_ids() -> None:
    """Adding glucose must not rename or repurpose existing uric acid entities."""
    entry = make_entry()
    acid = HealthValueSensor(entry, METRICS["uric_acid"])
    glucose = HealthValueSensor(entry, METRICS["blood_glucose"])
    assert acid.unique_id == "user_uric_acid"
    assert glucose.unique_id == "user_blood_glucose"
    assert acid.native_value == 400
    assert glucose.native_value == 5.6
    assert acid.native_unit_of_measurement == "µmol/L"
    assert glucose.native_unit_of_measurement == "mmol/L"
    assert (
        HealthMeasuredAtSensor(entry, METRICS["uric_acid"]).unique_id
        == "user_uric_acid_measured_at"
    )
    assert (
        HealthMeasuredAtSensor(entry, METRICS["blood_glucose"]).unique_id
        == "user_blood_glucose_measured_at"
    )
    assert (
        HealthMeasuredAtSensor(entry, METRICS["blood_glucose"]).native_value.isoformat()
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
    assert HealthValueSensor(entry, METRICS["blood_glucose"]).native_value is None
    assert HealthMeasuredAtSensor(entry, METRICS["blood_glucose"]).native_value is None


async def test_filter_preserves_registry_id_and_history(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SUBJECT_ID: "user", CONF_SUBJECT_NAME: "User"},
        options={"metric_mode": "whitelist", "metrics": []},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "sensor", DOMAIN, "user_uric_acid", config_entry=entry
    )
    sync_metric_registry(hass, entry)
    disabled = registry.async_get(entity.entity_id)
    assert disabled.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert disabled.options[DOMAIN][FILTER_DISABLED]
    sync_metric_registry(hass, entry)
    hass.config_entries.async_update_entry(
        entry, options={"metric_mode": "whitelist", "metrics": ["uric_acid"]}
    )
    sync_metric_registry(hass, entry)
    restored = registry.async_get(entity.entity_id)
    assert restored.disabled_by is None
    assert restored.id == entity.id
    assert FILTER_DISABLED not in restored.options.get(DOMAIN, {})


@pytest.mark.parametrize(
    "reason", [er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.INTEGRATION]
)
async def test_filter_does_not_reenable_existing_disabled_entities(hass, reason):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_SUBJECT_ID: "user"},
        options={"metric_mode": "whitelist", "metrics": []},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "sensor", DOMAIN, "user_weight", config_entry=entry, disabled_by=reason
    )
    sync_metric_registry(hass, entry)
    hass.config_entries.async_update_entry(
        entry, options={"metric_mode": "blacklist", "metrics": []}
    )
    sync_metric_registry(hass, entry)
    assert registry.async_get(entity.entity_id).disabled_by is reason


async def test_only_selected_metrics_create_sensors(hass):
    entry = make_entry()
    entry.options = {"metric_mode": "whitelist", "metrics": ["weight", "steps"]}
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert {entity.unique_id for entity in entities} == {
        "user_weight",
        "user_weight_measured_at",
        "user_steps",
        "user_steps_measured_at",
    }
    assert all(entity.state_class is None for entity in entities)
    entry.options["metrics"] = []
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert not entities
