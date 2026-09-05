"""Tests for the Irminsul Health config flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.irminsul_health.const import (
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)


async def test_create_health_profile(hass) -> None:
    """Create a health profile and private webhook."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SUBJECT_ID: "poera", CONF_SUBJECT_NAME: "Poera"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Poera"
    assert result["data"][CONF_SUBJECT_ID] == "poera"
    assert len(result["data"][CONF_WEBHOOK_ID]) == 64
    assert "webhook_url" in result["description_placeholders"]


async def test_reject_duplicate_profile(hass) -> None:
    """Prevent two config entries from owning the same person ID."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        first["flow_id"],
        {CONF_SUBJECT_ID: "poera", CONF_SUBJECT_NAME: "Poera"},
    )

    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        second["flow_id"],
        {CONF_SUBJECT_ID: "poera", CONF_SUBJECT_NAME: "Poera 2"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
