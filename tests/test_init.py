"""Tests for integration setup and unloading."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irminsul_health import async_setup_entry, async_unload_entry
from custom_components.irminsul_health.const import (
    CONF_ALLOW_REMOTE,
    CONF_INGEST_TOKEN,
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)
from custom_components.irminsul_health.models import parse_observation


@pytest.mark.parametrize("allow_remote", [False, True])
async def test_webhook_registration_and_unload(hass, allow_remote) -> None:
    """Use HA's webhook registry even after importing our webhook module."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SUBJECT_ID: "user",
            CONF_SUBJECT_NAME: "User",
            CONF_WEBHOOK_ID: "test-webhook",
            CONF_INGEST_TOKEN: "test-token",
            CONF_ALLOW_REMOTE: allow_remote,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.irminsul_health.ObservationStore", autospec=True
        ) as store,
        patch("homeassistant.components.webhook.async_register") as register,
        patch("homeassistant.components.webhook.async_unregister") as unregister,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
        ) as forward,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ),
    ):
        assert await async_setup_entry(hass, entry)
        store.return_value.async_load.assert_awaited_once()
        register.assert_called_once()
        assert register.call_args.args[:4] == (
            hass,
            DOMAIN,
            "Irminsul Health: User",
            "test-webhook",
        )
        assert callable(register.call_args.args[4])
        assert register.call_args.kwargs == {
            "local_only": not allow_remote,
            "allowed_methods": {"POST"},
        }
        forward.assert_awaited_once()

        # Reconfigure updates entry data before the old runtime is unloaded.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_WEBHOOK_ID: "new-webhook"}
        )
        assert await async_unload_entry(hass, entry)
        assert entry.runtime_data.accepting is False
        store.return_value.async_flush.assert_awaited_once()
        unregister.assert_called_once_with(hass, "test-webhook")


async def test_metric_toggle_reloads_preserves_value_and_entity_id(hass):
    """Exercise real HA setup, delayed storage flush, disable and reenable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="User",
        data={
            CONF_SUBJECT_ID: "user",
            CONF_SUBJECT_NAME: "User",
            CONF_WEBHOOK_ID: "test-webhook",
            CONF_INGEST_TOKEN: "test-token",
            CONF_ALLOW_REMOTE: False,
        },
        options={"metric_mode": "whitelist", "metrics": ["weight"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, "user_weight")
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unknown"
    observation = parse_observation(
        {
            "metric": "weight",
            "value": 60.5,
            "unit": "kg",
            "observed_at": "2025-01-01T00:00:00Z",
        }
    )
    await entry.runtime_data.store.async_add_many([observation])
    entry.runtime_data.notify()
    assert hass.states.get(entity_id).state == "60.5"
    old_runtime = entry.runtime_data
    hass.config_entries.async_update_entry(
        entry, options={"metric_mode": "whitelist", "metrics": []}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert not old_runtime.accepting
    assert (
        registry.async_get(entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert entry.runtime_data.store.latest("weight") == observation
    hass.config_entries.async_update_entry(
        entry, options={"metric_mode": "whitelist", "metrics": ["weight"]}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, "user_weight") == entity_id
    assert registry.async_get(entity_id).disabled_by is None
    assert hass.states.get(entity_id).state == "60.5"
    assert await hass.config_entries.async_unload(entry.entry_id)
