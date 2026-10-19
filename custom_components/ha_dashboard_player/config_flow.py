"""Config flow for HA Dashboard Player."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import probatio

from .const import (
    CONF_ENABLE_CACHE,
    CONF_IMAGE_DURATION,
    CONF_RESTORE_LAST_MEDIA,
    DEFAULT_ENABLE_CACHE,
    DEFAULT_IMAGE_DURATION,
    DEFAULT_NAME,
    DEFAULT_RESTORE_LAST_MEDIA,
    DOMAIN,
    MAX_IMAGE_DURATION,
    MIN_IMAGE_DURATION,
)

OPTIONS_SCHEMA = probatio.Schema(
    {
        probatio.Required(
            CONF_ENABLE_CACHE, default=DEFAULT_ENABLE_CACHE
        ): selector.BooleanSelector(),
        probatio.Required(
            CONF_RESTORE_LAST_MEDIA, default=DEFAULT_RESTORE_LAST_MEDIA
        ): selector.BooleanSelector(),
        probatio.Required(
            CONF_IMAGE_DURATION, default=DEFAULT_IMAGE_DURATION
        ): probatio.All(
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_IMAGE_DURATION,
                    max=MAX_IMAGE_DURATION,
                    step=1,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            probatio.Coerce(int),
        ),
    }
)

USER_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector()}
).extend(OPTIONS_SCHEMA.schema)


class HADashboardPlayerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                self._async_abort_entries_match({CONF_NAME: name})
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name},
                    options={
                        CONF_ENABLE_CACHE: user_input[CONF_ENABLE_CACHE],
                        CONF_RESTORE_LAST_MEDIA: user_input[CONF_RESTORE_LAST_MEDIA],
                        CONF_IMAGE_DURATION: user_input[CONF_IMAGE_DURATION],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> HADashboardPlayerOptionsFlow:
        """Return the options flow."""
        return HADashboardPlayerOptionsFlow()


class HADashboardPlayerOptionsFlow(OptionsFlowWithReload):
    """Handle options; the entry is reloaded automatically on change."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry = self.config_entry
        current = {
            key: entry.options.get(key, entry.data.get(key, default))
            for key, default in (
                (CONF_ENABLE_CACHE, DEFAULT_ENABLE_CACHE),
                (CONF_RESTORE_LAST_MEDIA, DEFAULT_RESTORE_LAST_MEDIA),
                (CONF_IMAGE_DURATION, DEFAULT_IMAGE_DURATION),
            )
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, current),
        )
