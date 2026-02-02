"""Constants for HA Dashboard Player."""

from homeassistant.const import Platform

DOMAIN = "ha_dashboard_player"
PLATFORMS = [Platform.MEDIA_PLAYER]

CONF_NAME = "name"
CONF_ENABLE_CACHE = "enable_cache"
CONF_RESTORE_LAST_MEDIA = "restore_last_media"

DEFAULT_NAME = "Dashboard Player"
DEFAULT_ENABLE_CACHE = False
DEFAULT_RESTORE_LAST_MEDIA = True

ATTR_MEDIA_URL = "media_url"
ATTR_CACHED_MEDIA_URL = "cached_media_url"
ATTR_CACHE_ENABLED = "cache_enabled"
ATTR_LAST_ERROR = "last_error"

SERVICE_PRELOAD_MEDIA = "preload_media"
SERVICE_CLEAR_SCREEN = "clear_screen"

SERVICE_FIELD_MEDIA_URL = "media_url"
