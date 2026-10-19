"""Entity services for HA Dashboard Player."""

from __future__ import annotations

from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    MediaPlayerState,
    RepeatMode,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, service
import probatio

from .const import (
    DOMAIN,
    SERVICE_CLEAR_SCREEN,
    SERVICE_FIELD_IS_VOLUME_MUTED,
    SERVICE_FIELD_MEDIA_CONTENT_ID,
    SERVICE_FIELD_MEDIA_DURATION,
    SERVICE_FIELD_MEDIA_POSITION,
    SERVICE_FIELD_MEDIA_URL,
    SERVICE_FIELD_REPEAT,
    SERVICE_FIELD_SHUFFLE,
    SERVICE_FIELD_STATE,
    SERVICE_FIELD_VOLUME_LEVEL,
    SERVICE_MEDIA_ENDED,
    SERVICE_PRELOAD_MEDIA,
    SERVICE_REPORT_STATE,
)

REPORTABLE_STATES = (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's entity services."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_PRELOAD_MEDIA,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={probatio.Required(SERVICE_FIELD_MEDIA_URL): cv.url},
        func="async_preload_media",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CLEAR_SCREEN,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema=None,
        func="async_clear_screen",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_REPORT_STATE,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={
            probatio.Optional(SERVICE_FIELD_STATE): probatio.In(
                [state.value for state in REPORTABLE_STATES]
            ),
            probatio.Optional(SERVICE_FIELD_MEDIA_POSITION): probatio.All(
                probatio.Coerce(float), probatio.Range(min=0)
            ),
            probatio.Optional(SERVICE_FIELD_MEDIA_DURATION): probatio.All(
                probatio.Coerce(float), probatio.Range(min=0)
            ),
            probatio.Optional(SERVICE_FIELD_VOLUME_LEVEL): cv.small_float,
            probatio.Optional(SERVICE_FIELD_IS_VOLUME_MUTED): cv.boolean,
            probatio.Optional(SERVICE_FIELD_REPEAT): probatio.Coerce(RepeatMode),
            # Accepted for compatibility with cards < 0.2.0, ignored.
            probatio.Optional(SERVICE_FIELD_SHUFFLE): cv.boolean,
        },
        func="async_report_state",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_MEDIA_ENDED,
        entity_domain=MEDIA_PLAYER_DOMAIN,
        schema={probatio.Optional(SERVICE_FIELD_MEDIA_CONTENT_ID): cv.string},
        func="async_media_ended",
    )
