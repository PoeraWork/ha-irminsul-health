"""Tests for the Irminsul Health config flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.irminsul_health.const import (
    CONF_ALLOW_REMOTE,
    CONF_INGEST_TOKEN,
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
        {
            CONF_SUBJECT_ID: "user",
            CONF_SUBJECT_NAME: "User",
            CONF_ALLOW_REMOTE: False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "User"
    assert result["data"][CONF_SUBJECT_ID] == "user"
    assert len(result["data"][CONF_WEBHOOK_ID]) == 64
    assert len(result["data"][CONF_INGEST_TOKEN]) >= 43
    assert result["data"][CONF_ALLOW_REMOTE] is False
    assert "webhook_url" in result["description_placeholders"]


async def test_reject_duplicate_profile(hass) -> None:
    """Prevent two config entries from owning the same person ID."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        first["flow_id"],
        {
            CONF_SUBJECT_ID: "user",
            CONF_SUBJECT_NAME: "User",
            CONF_ALLOW_REMOTE: False,
        },
    )

    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        second["flow_id"],
        {
            CONF_SUBJECT_ID: "user",
            CONF_SUBJECT_NAME: "User 2",
            CONF_ALLOW_REMOTE: False,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
