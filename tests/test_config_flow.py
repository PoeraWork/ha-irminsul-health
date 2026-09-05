"""Tests for the Irminsul Health config flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irminsul_health.config_flow import _validate_profile
from custom_components.irminsul_health.const import (
    CONF_ALLOW_REMOTE,
    CONF_INGEST_TOKEN,
    CONF_METRIC_MODE,
    CONF_METRICS,
    CONF_PERSON_ENTITY_ID,
    CONF_PERSON_REGISTRY_ID,
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)
from custom_components.irminsul_health.metrics import DEFAULT_METRICS
from custom_components.irminsul_health.profile import person_entity_id


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
    assert result["options"][CONF_METRICS] == list(DEFAULT_METRICS)


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


async def test_options_link_person_and_clear_without_rotating_credentials(hass):
    """The native options flow updates only metadata and the metric policy."""
    person = er.async_get(hass).async_get_or_create("person", "person", "user")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SUBJECT_ID: "user",
            CONF_SUBJECT_NAME: "User",
            CONF_ALLOW_REMOTE: False,
            CONF_WEBHOOK_ID: "test-webhook",
            CONF_INGEST_TOKEN: "test-token",
        },
    )
    entry.add_to_hass(hass)
    original = dict(entry.data)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", return_value=True
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_PERSON_ENTITY_ID: person.entity_id,
                CONF_METRIC_MODE: "whitelist",
                CONF_METRICS: ["weight", "steps"],
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_PERSON_REGISTRY_ID] == person.id
        assert entry.options[CONF_METRICS] == ["weight", "steps"]
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_METRIC_MODE: "blacklist", CONF_METRICS: []}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PERSON_ENTITY_ID not in entry.options
    assert CONF_PERSON_REGISTRY_ID not in entry.options
    assert entry.data == original


async def test_person_link_follows_rename_not_replacement(hass):
    """A registry UUID follows a rename but does not bind a replacement person."""
    registry = er.async_get(hass)
    person = registry.async_get_or_create("person", "person", "user")
    options, errors = _validate_profile(hass, {CONF_PERSON_ENTITY_ID: person.entity_id})
    assert not errors
    registry.async_update_entity(person.entity_id, new_entity_id="person.renamed")
    assert person_entity_id(hass, options) == "person.renamed"
    registry.async_remove("person.renamed")
    registry.async_get_or_create(
        "person", "person", "replacement", suggested_object_id="renamed"
    )
    assert person_entity_id(hass, options) is None


async def test_reject_person_linked_to_other_profile(hass):
    person = er.async_get(hass).async_get_or_create("person", "person", "user")
    options, _ = _validate_profile(hass, {CONF_PERSON_ENTITY_ID: person.entity_id})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options)
    entry.add_to_hass(hass)
    _, errors = _validate_profile(hass, {CONF_PERSON_ENTITY_ID: person.entity_id})
    assert errors == {CONF_PERSON_ENTITY_ID: "person_already_linked"}
    _, errors = _validate_profile(
        hass, {CONF_PERSON_ENTITY_ID: person.entity_id}, entry.entry_id
    )
    assert not errors


@pytest.mark.parametrize(
    "person", ["sensor.temperature", "person.missing", ["person.user"]]
)
async def test_invalid_person(hass, person):
    _, errors = _validate_profile(hass, {CONF_PERSON_ENTITY_ID: person})
    assert errors == {CONF_PERSON_ENTITY_ID: "invalid_person"}
