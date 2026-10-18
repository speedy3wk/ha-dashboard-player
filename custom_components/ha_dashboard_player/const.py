"""Constants for HA Dashboard Player."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ha_dashboard_player"
PLATFORMS: Final = [Platform.MEDIA_PLAYER]

CONF_ENABLE_CACHE: Final = "enable_cache"
CONF_RESTORE_LAST_MEDIA: Final = "restore_last_media"

DEFAULT_NAME: Final = "Dashboard Player"
DEFAULT_ENABLE_CACHE: Final = False
DEFAULT_RESTORE_LAST_MEDIA: Final = True

FRONTEND_URL_BASE: Final = f"/{DOMAIN}_static"
FRONTEND_SCRIPT: Final = "ha-dashboard-player.js"

CACHE_SUBDIR: Final = "ha_dashboard_player_cache"
CACHE_MAX_FILE_BYTES: Final = 2 * 1024**3
CACHE_MAX_TOTAL_BYTES: Final = 10 * 1024**3
CACHE_DOWNLOAD_CHUNK_BYTES: Final = 1024**2
CACHE_READ_TIMEOUT_SECONDS: Final = 60

FEEDBACK_TIMEOUT_SECONDS: Final = 15.0
POSITION_DRIFT_TOLERANCE_SECONDS: Final = 1.5

MEDIA_KIND_IMAGE: Final = "image"
MEDIA_KIND_VIDEO: Final = "video"
MEDIA_KIND_AUDIO: Final = "audio"

ATTR_MEDIA_URL: Final = "media_url"
ATTR_MEDIA_KIND: Final = "media_kind"
ATTR_CACHE_ENABLED: Final = "cache_enabled"
ATTR_LAST_ERROR: Final = "last_error"
ATTR_INTEGRATION: Final = "ha_dashboard_player"

SERVICE_PRELOAD_MEDIA: Final = "preload_media"
SERVICE_CLEAR_SCREEN: Final = "clear_screen"
SERVICE_REPORT_STATE: Final = "report_state"

SERVICE_FIELD_MEDIA_URL: Final = "media_url"
SERVICE_FIELD_STATE: Final = "state"
SERVICE_FIELD_MEDIA_POSITION: Final = "media_position"
SERVICE_FIELD_MEDIA_DURATION: Final = "media_duration"
SERVICE_FIELD_VOLUME_LEVEL: Final = "volume_level"
SERVICE_FIELD_IS_VOLUME_MUTED: Final = "is_volume_muted"
SERVICE_FIELD_REPEAT: Final = "repeat"
SERVICE_FIELD_SHUFFLE: Final = "shuffle"
