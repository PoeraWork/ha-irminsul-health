"""Catalog-backed sensors selected independently for each health profile."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_SUBJECT_ID, CONF_SUBJECT_NAME, DOMAIN
from .metrics import METRICS, Metric, enabled_metrics
from .models import IrminsulRuntimeData, Observation
from .profile import person_entity_id

FILTER_DISABLED = "metric_filter_disabled"


@callback
def sync_metric_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Preserve registry IDs and only undo disables owned by this filter."""
    registry = er.async_get(hass)
    allowed = enabled_metrics(entry.options)
    keys = {
        f"{entry.data[CONF_SUBJECT_ID]}_{key}{suffix}": key
        for key in METRICS
        for suffix in ("", "_measured_at")
    }
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform != DOMAIN or entity.unique_id not in keys:
            continue
        settings = dict(entity.options.get(DOMAIN, {}))
        if keys[entity.unique_id] not in allowed:
            if entity.disabled_by is None:
                settings[FILTER_DISABLED] = True
                registry.async_update_entity_options(entity.entity_id, DOMAIN, settings)
                registry.async_update_entity(
                    entity.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                )
        elif settings.pop(FILTER_DISABLED, False):
            if entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(entity.entity_id, disabled_by=None)
            registry.async_update_entity_options(
                entity.entity_id, DOMAIN, settings or None
            )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[IrminsulRuntimeData],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add only selected metrics; disabled historical registry entries remain."""
    sync_metric_registry(hass, entry)
    allowed = enabled_metrics(entry.options)
    async_add_entities(
        [
            sensor_type(entry, metric)
            for key, metric in METRICS.items()
            if key in allowed
            for sensor_type in (HealthValueSensor, HealthMeasuredAtSensor)
        ]
    )


class IrminsulSensorEntity(SensorEntity):
    """Base entity backed by one metric in a profile's observation store."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData], metric: Metric) -> None:
        """Keep stable subject IDs independent of the linked HA person."""
        self._entry = entry
        self._runtime_data = entry.runtime_data
        self._subject_id = entry.data[CONF_SUBJECT_ID]
        self._metric = metric
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._subject_id)},
            manufacturer="Irminsul",
            model="Health profile",
            name=entry.data[CONF_SUBJECT_NAME],
        )

    async def async_added_to_hass(self) -> None:
        """Listen for observations and changes to linked person registry entries."""
        self.async_on_remove(self._runtime_data.subscribe(self._handle_update))
        self.async_on_remove(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._person_updated
            )
        )

    @callback
    def _person_updated(self, event) -> None:
        if event.data.get("entity_id", "").startswith("person."):
            self.async_write_ha_state()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _latest(self) -> Observation | None:
        return self._runtime_data.store.latest(self._metric.key)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose ownership metadata, never credentials or private notes."""
        attributes = {
            "subject_id": self._subject_id,
            "metric": self._metric.key,
            "time_kind": self._metric.time_kind,
        }
        if self.hass and (person := person_entity_id(self.hass, self._entry.options)):
            attributes["person_entity_id"] = person
        return attributes


class HealthValueSensor(IrminsulSensorEntity):
    """Latest value for a selected metric, without treating samples as totals."""

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData], metric: Metric) -> None:
        super().__init__(entry, metric)
        self._attr_translation_key = metric.key
        self._attr_native_unit_of_measurement = metric.unit
        self._attr_icon = metric.icon
        self._attr_suggested_display_precision = metric.precision
        self._attr_unique_id = f"{self._subject_id}_{metric.key}"

    @property
    def native_value(self) -> float | None:
        observation = self._latest()
        return observation.value if observation else None


class HealthMeasuredAtSensor(IrminsulSensorEntity):
    """Actual measurement time rather than the webhook arrival time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, entry: ConfigEntry[IrminsulRuntimeData], metric: Metric) -> None:
        super().__init__(entry, metric)
        self._attr_translation_key = f"{metric.key}_measured_at"
        self._attr_unique_id = f"{self._subject_id}_{metric.key}_measured_at"

    @property
    def native_value(self) -> datetime | None:
        observation = self._latest()
        return datetime.fromisoformat(observation.observed_at) if observation else None
