"""The Irminsul Health integration."""

from __future__ import annotations

from aiohttp.web import Request, Response
from homeassistant.components import webhook as ha_webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ALLOW_REMOTE,
    CONF_INGEST_TOKEN,
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)
from .metrics import enabled_metrics
from .models import IrminsulRuntimeData
from .storage import ObservationStore
from .webhook import async_handle_webhook

PLATFORMS = [Platform.SENSOR]
type IrminsulConfigEntry = ConfigEntry[IrminsulRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: IrminsulConfigEntry) -> bool:
    """Set up Irminsul Health from a config entry."""
    store = ObservationStore(hass, entry.entry_id)
    await store.async_load()
    runtime = entry.runtime_data = IrminsulRuntimeData(
        store=store,
        metric_policy=lambda: enabled_metrics(entry.options),
        webhook_id=entry.data[CONF_WEBHOOK_ID],
    )

    async def handle_webhook(
        webhook_hass: HomeAssistant, _webhook_id: str, request: Request
    ) -> Response:
        return await async_handle_webhook(
            webhook_hass,
            runtime,
            entry.data[CONF_SUBJECT_ID],
            entry.data[CONF_INGEST_TOKEN],
            request,
        )

    ha_webhook.async_register(
        hass,
        DOMAIN,
        f"Irminsul Health: {entry.data[CONF_SUBJECT_NAME]}",
        entry.data[CONF_WEBHOOK_ID],
        handle_webhook,
        local_only=not entry.data[CONF_ALLOW_REMOTE],
        allowed_methods={"POST"},
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IrminsulConfigEntry) -> bool:
    """Unload a config entry."""
    entry.runtime_data.accepting = False
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.accepting = True
        return False
    await entry.runtime_data.store.async_flush()
    ha_webhook.async_unregister(hass, entry.runtime_data.webhook_id)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove private observations after deleting the config entry."""
    await ObservationStore(hass, entry.entry_id).async_remove()
