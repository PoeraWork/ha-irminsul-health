"""Config flow for Irminsul Health."""

from __future__ import annotations

import re
import secrets
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import webhook

from .const import (
    CONF_ALLOW_REMOTE,
    CONF_INGEST_TOKEN,
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
                ingest_token = secrets.token_urlsafe(32)
                allow_remote = user_input[CONF_ALLOW_REMOTE]
                webhook_url = self._generate_webhook_url(webhook_id, allow_remote)
                return self.async_create_entry(
                    title=subject_name,
                    data={
                        CONF_SUBJECT_ID: subject_id,
                        CONF_SUBJECT_NAME: subject_name,
                        CONF_WEBHOOK_ID: webhook_id,
                        CONF_INGEST_TOKEN: ingest_token,
                        CONF_ALLOW_REMOTE: allow_remote,
                    },
                    description_placeholders={
                        "webhook_url": webhook_url,
                        "ingest_token": ingest_token,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SUBJECT_ID, default="person"): str,
                vol.Required(CONF_SUBJECT_NAME, default="Person"): str,
                vol.Optional(CONF_ALLOW_REMOTE, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Rename a health profile without changing its webhook."""
        entry = self._get_reconfigure_entry()
        allow_remote = entry.data[CONF_ALLOW_REMOTE]
        webhook_url = self._generate_webhook_url(
            entry.data[CONF_WEBHOOK_ID], allow_remote
        )
        ingest_token = entry.data[CONF_INGEST_TOKEN]
        errors: dict[str, str] = {}

        if user_input is not None:
            subject_name = user_input[CONF_SUBJECT_NAME].strip()
            if not subject_name:
                errors[CONF_SUBJECT_NAME] = "required"
            else:
                webhook_id = entry.data[CONF_WEBHOOK_ID]
                allow_remote = user_input[CONF_ALLOW_REMOTE]
                if user_input[CONF_ROTATE_WEBHOOK]:
                    webhook_id = webhook.async_generate_id()
                    ingest_token = secrets.token_urlsafe(32)
                webhook_url = self._generate_webhook_url(webhook_id, allow_remote)
                changed = self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_SUBJECT_NAME: subject_name,
                        CONF_WEBHOOK_ID: webhook_id,
                        CONF_INGEST_TOKEN: ingest_token,
                        CONF_ALLOW_REMOTE: allow_remote,
                    },
                    title=subject_name,
                )
                if changed:
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(
                    reason="reconfigure_successful",
                    description_placeholders={
                        "webhook_url": webhook_url,
                        "ingest_token": ingest_token,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SUBJECT_NAME,
                        default=entry.data[CONF_SUBJECT_NAME],
                    ): str,
                    vol.Optional(
                        CONF_ALLOW_REMOTE,
                        default=entry.data[CONF_ALLOW_REMOTE],
                    ): bool,
                    vol.Optional(CONF_ROTATE_WEBHOOK, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "webhook_url": webhook_url,
                "ingest_token": ingest_token,
            },
        )

    def _generate_webhook_url(self, webhook_id: str, allow_remote: bool) -> str:
        """Generate a URL that matches the webhook access policy."""
        return webhook.async_generate_url(
            self.hass,
            webhook_id,
            allow_internal=True,
            allow_external=allow_remote,
            prefer_external=allow_remote,
        )
