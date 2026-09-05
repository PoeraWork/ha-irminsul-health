"""Tests for integration setup and unloading."""

from unittest.mock import patch

import pytest
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

        assert await async_unload_entry(hass, entry)
        unregister.assert_called_once_with(hass, "test-webhook")
