"""Config flow for HA Dashboard Player."""

import logging
import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_ENABLE_CACHE,
    DEFAULT_NAME,
    DEFAULT_RESTORE_LAST_MEDIA,
    DOMAIN,
    CONF_ENABLE_CACHE,
    CONF_RESTORE_LAST_MEDIA,
)


class HADashboardPlayerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            raw_name = user_input[CONF_NAME]
            sanitized_name = _sanitize_name(raw_name)
            if raw_name != sanitized_name:
                _LOGGER.info(
                    "Sanitized dashboard player name from '%s' to '%s'",
                    raw_name,
                    sanitized_name,
                )
            return self.async_create_entry(
                title=sanitized_name,
                data={
                    CONF_NAME: sanitized_name,
                    CONF_ENABLE_CACHE: user_input[CONF_ENABLE_CACHE],
                    CONF_RESTORE_LAST_MEDIA: user_input[CONF_RESTORE_LAST_MEDIA],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_ENABLE_CACHE, default=DEFAULT_ENABLE_CACHE): cv.boolean,
                vol.Optional(
                    CONF_RESTORE_LAST_MEDIA, default=DEFAULT_RESTORE_LAST_MEDIA
                ): cv.boolean,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HADashboardPlayerOptionsFlow(config_entry)


class HADashboardPlayerOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_CACHE,
                    default=self._config_entry.options.get(
                        CONF_ENABLE_CACHE,
                        self._config_entry.data.get(
                            CONF_ENABLE_CACHE, DEFAULT_ENABLE_CACHE
                        ),
                    ),
                ): cv.boolean,
                vol.Optional(
                    CONF_RESTORE_LAST_MEDIA,
                    default=self._config_entry.options.get(
                        CONF_RESTORE_LAST_MEDIA,
                        self._config_entry.data.get(
                            CONF_RESTORE_LAST_MEDIA, DEFAULT_RESTORE_LAST_MEDIA
                        ),
                    ),
                ): cv.boolean,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


_LOGGER = logging.getLogger(__name__)


def _sanitize_name(raw_name: str) -> str:
    """Sanitize the entity name to match HA 2026.2+ entity_id rules."""
    name = raw_name.strip().lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "dashboard_player"
