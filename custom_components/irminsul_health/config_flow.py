"""Config flow for Irminsul Health."""

from __future__ import annotations

import re
import secrets
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOW_REMOTE,
    CONF_INGEST_TOKEN,
    CONF_METRIC_MODE,
    CONF_METRICS,
    CONF_PERSON_ENTITY_ID,
    CONF_PERSON_REGISTRY_ID,
    CONF_ROTATE_WEBHOOK,
    CONF_SUBJECT_ID,
    CONF_SUBJECT_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
    MODE_BLACKLIST,
    MODE_WHITELIST,
)
from .metrics import DEFAULT_METRICS, LEGACY_METRICS, METRICS
from .profile import person_entity_id

SUBJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _profile_fields(defaults: dict[str, Any]) -> dict:
    """Use the same selectors in setup and options."""
    return {
        vol.Optional(CONF_PERSON_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="person")
        ),
        vol.Required(
            CONF_METRIC_MODE, default=defaults[CONF_METRIC_MODE]
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[MODE_WHITELIST, MODE_BLACKLIST], translation_key="metric_mode"
            )
        ),
        vol.Required(
            CONF_METRICS, default=list(defaults[CONF_METRICS])
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(METRICS),
                multiple=True,
                translation_key="metrics",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }


def _validate_profile(hass, user_input, entry_id=None):
    """Validate person ownership and store a stable registry link if available."""
    options = {
        CONF_METRIC_MODE: user_input.get(CONF_METRIC_MODE, MODE_WHITELIST),
        CONF_METRICS: user_input.get(CONF_METRICS, list(DEFAULT_METRICS)),
    }
    errors = {}
    if options[CONF_METRIC_MODE] not in (MODE_WHITELIST, MODE_BLACKLIST):
        errors[CONF_METRIC_MODE] = "invalid_metric_policy"
    selected = options[CONF_METRICS]
    if not isinstance(selected, list) or any(
        not isinstance(key, str) or key not in METRICS for key in selected
    ):
        errors[CONF_METRICS] = "invalid_metric_policy"
    else:
        options[CONF_METRICS] = list(dict.fromkeys(selected))
    person = user_input.get(CONF_PERSON_ENTITY_ID)
    if person:
        registered = (
            er.async_get(hass).async_get(person) if isinstance(person, str) else None
        )
        if (
            not isinstance(person, str)
            or not person.startswith("person.")
            or (registered is None and hass.states.get(person) is None)
        ):
            errors[CONF_PERSON_ENTITY_ID] = "invalid_person"
        elif any(
            entry.entry_id != entry_id
            and person_entity_id(hass, entry.options) == person
            for entry in hass.config_entries.async_entries(DOMAIN)
        ):
            errors[CONF_PERSON_ENTITY_ID] = "person_already_linked"
        else:
            options[CONF_PERSON_ENTITY_ID] = person
            if registered:
                options[CONF_PERSON_REGISTRY_ID] = registered.id
    return options, errors


class IrminsulHealthConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Irminsul Health config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Expose person and metric settings through the configure button."""
        return IrminsulHealthOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create one health profile and its private webhook."""
        errors: dict[str, str] = {}

        if user_input is not None:
            profile_options, errors = _validate_profile(self.hass, user_input)
            subject_id = user_input[CONF_SUBJECT_ID].strip().lower()
            subject_name = user_input[CONF_SUBJECT_NAME].strip()
            if not SUBJECT_ID_PATTERN.fullmatch(subject_id):
                errors[CONF_SUBJECT_ID] = "invalid_subject_id"
            elif not subject_name:
                errors[CONF_SUBJECT_NAME] = "required"
            elif not errors:
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
                    options=profile_options,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SUBJECT_ID, default="person"): str,
                vol.Required(CONF_SUBJECT_NAME, default="Person"): str,
                vol.Optional(CONF_ALLOW_REMOTE, default=False): bool,
                **_profile_fields(
                    {
                        CONF_METRIC_MODE: MODE_WHITELIST,
                        CONF_METRICS: DEFAULT_METRICS,
                    }
                ),
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


class IrminsulHealthOptionsFlow(config_entries.OptionsFlowWithReload):
    """Configure person association and metric policy without rotating credentials."""

    async def async_step_init(self, user_input=None):
        """Show per-profile settings and reload after saving changes."""
        errors = {}
        if user_input is not None:
            options, errors = _validate_profile(
                self.hass, user_input, self.config_entry.entry_id
            )
            if not errors:
                return self.async_create_entry(data=options)
        defaults = {
            CONF_METRIC_MODE: self.config_entry.options.get(
                CONF_METRIC_MODE, MODE_WHITELIST
            ),
            CONF_METRICS: self.config_entry.options.get(CONF_METRICS, LEGACY_METRICS),
        }
        if person := person_entity_id(self.hass, self.config_entry.options):
            defaults[CONF_PERSON_ENTITY_ID] = person
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(_profile_fields(defaults)), user_input or defaults
            ),
            errors=errors,
        )
