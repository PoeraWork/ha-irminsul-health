"""Config flow for Irminsul Health."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import webhook

from .const import (
    CONF_ROTATE_WEBHOOK,
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)

SUBJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class IrminsulHealthConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Irminsul Health config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create one health profile and its private webhook."""
        errors: dict[str, str] = {}

        if user_input is not None:
            subject_id = user_input[CONF_SUBJECT_ID].strip().lower()
            subject_name = user_input[CONF_SUBJECT_NAME].strip()
            if not SUBJECT_ID_PATTERN.fullmatch(subject_id):
                errors[CONF_SUBJECT_ID] = "invalid_subject_id"
            elif not subject_name:
                errors[CONF_SUBJECT_NAME] = "required"
            else:
                await self.async_set_unique_id(subject_id)
                self._abort_if_unique_id_configured()
                webhook_id = webhook.async_generate_id()
                webhook_url = webhook.async_generate_url(self.hass, webhook_id)
                return self.async_create_entry(
                    title=subject_name,
                    data={
                        CONF_SUBJECT_ID: subject_id,
                        CONF_SUBJECT_NAME: subject_name,
                        CONF_WEBHOOK_ID: webhook_id,
                    },
                    description_placeholders={"webhook_url": webhook_url},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SUBJECT_ID, default="person"): str,
                vol.Required(CONF_SUBJECT_NAME, default="Person"): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Rename a health profile without changing its webhook."""
        entry = self._get_reconfigure_entry()
        webhook_url = webhook.async_generate_url(self.hass, entry.data[CONF_WEBHOOK_ID])
        errors: dict[str, str] = {}

        if user_input is not None:
            subject_name = user_input[CONF_SUBJECT_NAME].strip()
            if not subject_name:
                errors[CONF_SUBJECT_NAME] = "required"
            else:
                webhook_id = entry.data[CONF_WEBHOOK_ID]
                if user_input[CONF_ROTATE_WEBHOOK]:
                    webhook_id = webhook.async_generate_id()
                    webhook_url = webhook.async_generate_url(self.hass, webhook_id)
                changed = self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_SUBJECT_NAME: subject_name,
                        CONF_WEBHOOK_ID: webhook_id,
                    },
                    title=subject_name,
                )
                if changed:
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(
                    reason="reconfigure_successful",
                    description_placeholders={"webhook_url": webhook_url},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SUBJECT_NAME,
                        default=entry.data[CONF_SUBJECT_NAME],
                    ): str,
                    vol.Optional(CONF_ROTATE_WEBHOOK, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={"webhook_url": webhook_url},
        )
