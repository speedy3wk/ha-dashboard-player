"""HA Dashboard Player integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .cache import MediaCache
from .card import async_register_frontend
from .const import (
    CONF_ENABLE_CACHE,
    CONF_IMAGE_DURATION,
    CONF_RESTORE_LAST_MEDIA,
    DEFAULT_ENABLE_CACHE,
    DEFAULT_IMAGE_DURATION,
    DEFAULT_RESTORE_LAST_MEDIA,
    DOMAIN,
    PLATFORMS,
)
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class DashboardPlayerData:
    """Runtime data of a dashboard player config entry."""

    restore_last_media: bool
    cache: MediaCache | None
    image_duration: float = DEFAULT_IMAGE_DURATION


type DashboardPlayerConfigEntry = ConfigEntry[DashboardPlayerData]


def get_entry_option(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Return an option, falling back to the initial config entry data."""
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration: services and the Lovelace card."""
    async_setup_services(hass)
    await async_register_frontend(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: DashboardPlayerConfigEntry
) -> bool:
    """Set up HA Dashboard Player from a config entry."""
    cache = None
    if get_entry_option(entry, CONF_ENABLE_CACHE, DEFAULT_ENABLE_CACHE):
        cache = MediaCache.from_hass(hass)

    entry.runtime_data = DashboardPlayerData(
        restore_last_media=get_entry_option(
            entry, CONF_RESTORE_LAST_MEDIA, DEFAULT_RESTORE_LAST_MEDIA
        ),
        cache=cache,
        image_duration=float(
            get_entry_option(entry, CONF_IMAGE_DURATION, DEFAULT_IMAGE_DURATION)
        ),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: DashboardPlayerConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data.cache is not None:
        await entry.runtime_data.cache.async_shutdown()
    return unloaded
