"""Link a health profile to a person without changing the person's state."""

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_PERSON_ENTITY_ID, CONF_PERSON_REGISTRY_ID


def person_entity_id(hass: HomeAssistant, options: Mapping[str, Any]) -> str | None:
    """Follow a registry rename and avoid rebinding a deleted person by name."""
    registry_id = options.get(CONF_PERSON_REGISTRY_ID)
    if registry_id:
        entity = er.async_get(hass).async_get(registry_id)
        return entity.entity_id if entity and entity.domain == "person" else None
    return options.get(CONF_PERSON_ENTITY_ID) or None
