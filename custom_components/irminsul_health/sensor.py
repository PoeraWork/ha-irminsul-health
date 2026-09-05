"""Sensor entities for Irminsul Health."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    DOMAIN,
    METRIC_BLOOD_GLUCOSE,
    METRIC_URIC_ACID,
    UNIT_BLOOD_GLUCOSE,
    UNIT_URIC_ACID,
)
from .models import IrminsulRuntimeData, Observation


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IrminsulRuntimeData],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Irminsul Health sensors."""
    async_add_entities(
        [
            UricAcidSensor(entry),
            UricAcidMeasuredAtSensor(entry),
            BloodGlucoseSensor(entry),
            BloodGlucoseMeasuredAtSensor(entry),
        ]
    )


class IrminsulSensorEntity(SensorEntity):
    """Base entity backed by the observation store."""

    _attr_has_entity_name = True
    _metric = METRIC_URIC_ACID

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData]) -> None:
        """Initialize the entity."""
        self._runtime_data = entry.runtime_data
        self._subject_id = entry.data[CONF_SUBJECT_ID]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._subject_id)},
            manufacturer="Irminsul",
            model="Health profile",
            name=entry.data[CONF_SUBJECT_NAME],
        )

    async def async_added_to_hass(self) -> None:
        """Start listening for new observations."""
        self.async_on_remove(self._runtime_data.subscribe(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _latest(self) -> Observation | None:
        return self._runtime_data.store.latest(self._metric)


class UricAcidSensor(IrminsulSensorEntity):
    """Latest uric acid measurement."""

    _attr_translation_key = "uric_acid"
    _attr_native_unit_of_measurement = UNIT_URIC_ACID
    _attr_icon = "mdi:test-tube"
    _attr_suggested_display_precision = 0

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData]) -> None:
        """Initialize the latest value sensor."""
        super().__init__(entry)
        self._attr_unique_id = f"{self._subject_id}_uric_acid"

    @property
    def native_value(self) -> float | None:
        """Return the newest uric acid value."""
        observation = self._latest()
        return observation.value if observation else None


class UricAcidMeasuredAtSensor(IrminsulSensorEntity):
    """Timestamp of the latest uric acid measurement."""

    _attr_translation_key = "uric_acid_measured_at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData]) -> None:
        """Initialize the measurement timestamp sensor."""
        super().__init__(entry)
        self._attr_unique_id = f"{self._subject_id}_uric_acid_measured_at"

    @property
    def native_value(self) -> datetime | None:
        """Return when the newest uric acid value was measured."""
        observation = self._latest()
        return datetime.fromisoformat(observation.observed_at) if observation else None


class BloodGlucoseSensor(IrminsulSensorEntity):
    """Latest manually classified blood glucose measurement."""

    _metric = METRIC_BLOOD_GLUCOSE
    _attr_translation_key = "blood_glucose"
    _attr_native_unit_of_measurement = UNIT_BLOOD_GLUCOSE
    _attr_icon = "mdi:water"
    _attr_suggested_display_precision = 2

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData]) -> None:
        """Initialize the latest value sensor."""
        super().__init__(entry)
        self._attr_unique_id = f"{self._subject_id}_blood_glucose"

    @property
    def native_value(self) -> float | None:
        """Return the newest glucose value."""
        observation = self._latest()
        return observation.value if observation else None


class BloodGlucoseMeasuredAtSensor(IrminsulSensorEntity):
    """Timestamp of the latest blood glucose measurement."""

    _metric = METRIC_BLOOD_GLUCOSE
    _attr_translation_key = "blood_glucose_measured_at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData]) -> None:
        """Initialize the measurement timestamp sensor."""
        super().__init__(entry)
        self._attr_unique_id = f"{self._subject_id}_blood_glucose_measured_at"

    @property
    def native_value(self) -> datetime | None:
        """Return when the newest glucose value was measured."""
        observation = self._latest()
        return datetime.fromisoformat(observation.observed_at) if observation else None
