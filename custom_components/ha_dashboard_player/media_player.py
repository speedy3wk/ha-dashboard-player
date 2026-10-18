"""Media player entity for HA Dashboard Player."""

from __future__ import annotations

from datetime import datetime
import logging
import math
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import aiohttp
from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import DashboardPlayerConfigEntry
from .cache import MediaCache, is_http_url
from .const import (
    ATTR_CACHE_ENABLED,
    ATTR_INTEGRATION,
    ATTR_LAST_ERROR,
    ATTR_MEDIA_KIND,
    ATTR_MEDIA_URL,
    DOMAIN,
    FEEDBACK_TIMEOUT_SECONDS,
    MEDIA_KIND_AUDIO,
    MEDIA_KIND_IMAGE,
    MEDIA_KIND_VIDEO,
    POSITION_DRIFT_TOLERANCE_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

_ACTIVE_STATES = (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED)
_PLAYABLE_PREFIXES = ("image/", "video/", "audio/")

_VIDEO_TYPES = {
    MediaType.VIDEO,
    MediaType.MOVIE,
    MediaType.EPISODE,
    MediaType.TVSHOW,
}
_AUDIO_TYPES = {
    MediaType.MUSIC,
    MediaType.TRACK,
    MediaType.PODCAST,
    MediaType.ALBUM,
    "audio",
}
_EXTENSION_KINDS = {
    **dict.fromkeys(
        (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".svg"),
        MEDIA_KIND_IMAGE,
    ),
    **dict.fromkeys(
        (".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav"),
        MEDIA_KIND_AUDIO,
    ),
}
_KIND_TO_CONTENT_TYPE = {
    MEDIA_KIND_IMAGE: MediaType.IMAGE,
    MEDIA_KIND_VIDEO: MediaType.VIDEO,
    MEDIA_KIND_AUDIO: MediaType.MUSIC,
}


def media_kind(media_type: str | None, mime_type: str | None, url: str | None) -> str:
    """Map a media type, MIME type or URL to image, video or audio."""
    for candidate in (mime_type, media_type):
        if not candidate:
            continue
        value = candidate.lower()
        if value.startswith("image"):
            return MEDIA_KIND_IMAGE
        if value.startswith("video") or value in _VIDEO_TYPES:
            return MEDIA_KIND_VIDEO
        if value.startswith("audio") or value in _AUDIO_TYPES:
            return MEDIA_KIND_AUDIO
    if url:
        suffix = PurePosixPath(urlparse(url).path).suffix.lower()
        if suffix in _EXTENSION_KINDS:
            return _EXTENSION_KINDS[suffix]
    # The <video> element can render audio as well, so it is the safest default.
    return MEDIA_KIND_VIDEO


def _is_playable(item: BrowseMedia) -> bool:
    return item.media_content_type.startswith(_PLAYABLE_PREFIXES)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardPlayerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up HA Dashboard Player from a config entry."""
    async_add_entities([HADashboardPlayer(entry)])


class HADashboardPlayer(MediaPlayerEntity, RestoreEntity):
    """Virtual media player that drives the dashboard card."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_media_image_remotely_accessible = False
    _unrecorded_attributes = frozenset({ATTR_MEDIA_URL, ATTR_LAST_ERROR})

    def __init__(self, entry: DashboardPlayerConfigEntry) -> None:
        """Initialize the player."""
        self._cache: MediaCache | None = entry.runtime_data.cache
        self._restore_last_media = entry.runtime_data.restore_last_media
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="HA Dashboard Player",
            model="Virtual dashboard player",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._attr_state = MediaPlayerState.IDLE
        self._media_url: str | None = None
        self._media_kind: str | None = None
        self._last_error: str | None = None
        self._feedback_unsub: CALLBACK_TYPE | None = None
        self._update_supported_features()

    async def async_added_to_hass(self) -> None:
        """Restore the last media on startup."""
        await super().async_added_to_hass()
        if not self._restore_last_media:
            return
        if (last_state := await self.async_get_last_state()) is None:
            return

        attrs = last_state.attributes
        if (volume := attrs.get("volume_level")) is not None:
            self._attr_volume_level = volume
        if (muted := attrs.get("is_volume_muted")) is not None:
            self._attr_is_volume_muted = muted

        content_id = attrs.get("media_content_id")
        source = attrs.get(ATTR_MEDIA_URL)
        if (
            content_id
            and media_source.is_media_source_id(content_id)
            and not (source and media_source.is_media_source_id(source))
        ):
            # Pre-0.2.0 stored signed URLs that expire; use the stable id.
            source = content_id
        if not source:
            return

        self._media_url = source
        self._media_kind = attrs.get(ATTR_MEDIA_KIND)
        if self._media_kind not in _KIND_TO_CONTENT_TYPE:
            self._media_kind = media_kind(attrs.get("media_content_type"), None, source)
        self._attr_media_content_id = content_id or source
        self._attr_media_content_type = _KIND_TO_CONTENT_TYPE[self._media_kind]
        if self._media_kind != MEDIA_KIND_IMAGE:
            self._attr_repeat = self._normalize_repeat(attrs.get("repeat"))
        if last_state.state in _ACTIVE_STATES:
            self._attr_state = MediaPlayerState(last_state.state)
            if self._media_kind == MEDIA_KIND_IMAGE:
                self._attr_state = MediaPlayerState.PLAYING
        self._update_supported_features()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel timers."""
        self._cancel_feedback_timer()
        await super().async_will_remove_from_hass()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the attributes used by the dashboard card."""
        return {
            ATTR_MEDIA_URL: self._media_url,
            ATTR_MEDIA_KIND: self._media_kind,
            ATTR_CACHE_ENABLED: self._cache is not None,
            ATTR_LAST_ERROR: self._last_error,
            ATTR_INTEGRATION: True,
        }

    async def async_turn_on(self) -> None:
        """Turn on the player."""
        if self._attr_state != MediaPlayerState.OFF:
            return
        self._attr_state = MediaPlayerState.IDLE
        self._async_write()

    async def async_turn_off(self) -> None:
        """Turn off the player and blank the screen."""
        self._clear_media()
        self._attr_state = MediaPlayerState.OFF
        self._async_write()

    async def async_media_play(self) -> None:
        """Resume playback."""
        if self._media_url is None or self._attr_state == MediaPlayerState.PLAYING:
            return
        self._attr_state = MediaPlayerState.PLAYING
        if self._media_kind != MEDIA_KIND_IMAGE:
            self._attr_media_position_updated_at = dt_util.utcnow()
            self._schedule_feedback_timeout()
        self._async_write()

    async def async_media_pause(self) -> None:
        """Pause playback."""
        if self._media_url is None or self._media_kind == MEDIA_KIND_IMAGE:
            return
        self._freeze_position()
        self._cancel_feedback_timer()
        self._attr_state = MediaPlayerState.PAUSED
        self._async_write()

    async def async_media_stop(self) -> None:
        """Stop playback and blank the screen."""
        await self.async_clear_screen()

    async def async_media_seek(self, position: float) -> None:
        """Seek to a position."""
        self._attr_media_position = max(0.0, position)
        self._attr_media_position_updated_at = dt_util.utcnow()
        self._async_write()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume."""
        self._attr_volume_level = volume
        self._async_write()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute."""
        self._attr_is_volume_muted = mute
        self._async_write()

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode; a single item can only repeat itself."""
        if self._media_kind in (None, MEDIA_KIND_IMAGE):
            return
        self._attr_repeat = self._normalize_repeat(repeat)
        self._async_write()

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Start playing media."""
        self._last_error = None
        if media_source.is_media_source_id(media_id):
            try:
                resolved = await media_source.async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
            except media_source.MediaSourceError as err:
                self._last_error = str(err)
                self._async_write()
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="unresolvable_media",
                    translation_placeholders={
                        "media_content_id": media_id,
                        "error": str(err),
                    },
                ) from err
            kind = media_kind(media_type, resolved.mime_type, resolved.url)
            source = media_id
        elif is_http_url(media_id) or media_id.startswith("/"):
            kind = media_kind(media_type, None, media_id)
            source = await self._async_cached_source(media_id)
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_media",
                translation_placeholders={"media_content_id": media_id},
            )

        self._media_url = source
        self._media_kind = kind
        self._attr_media_content_id = media_id
        self._attr_media_content_type = _KIND_TO_CONTENT_TYPE[kind]
        self._attr_media_duration = None
        self._attr_state = MediaPlayerState.PLAYING
        if kind == MEDIA_KIND_IMAGE:
            self._cancel_feedback_timer()
            self._attr_media_position = None
            self._attr_media_position_updated_at = None
            self._attr_repeat = None
        else:
            self._attr_media_position = 0
            self._attr_media_position_updated_at = dt_util.utcnow()
            self._attr_repeat = self._normalize_repeat(self._attr_repeat)
            self._schedule_feedback_timeout()
        self._async_write()

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse media sources, limited to images, video and audio."""
        if media_content_id in (None, "", "root"):
            media_content_id = None
        return await media_source.async_browse_media(
            self.hass, media_content_id, content_filter=_is_playable
        )

    async def async_preload_media(self, media_url: str) -> None:
        """Download a URL into the cache."""
        if self._cache is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cache_disabled"
            )
        try:
            await self._cache.async_fetch(media_url)
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            self._last_error = str(err)
            self._async_write()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cache_download_failed",
                translation_placeholders={"url": media_url, "error": str(err)},
            ) from err

    async def async_clear_screen(self) -> None:
        """Clear the output and go idle."""
        self._clear_media()
        self._attr_state = MediaPlayerState.IDLE
        self._async_write()

    async def async_report_state(
        self,
        state: str | None = None,
        media_position: float | None = None,
        media_duration: float | None = None,
        volume_level: float | None = None,
        is_volume_muted: bool | None = None,
        repeat: RepeatMode | str | None = None,
        shuffle: bool | None = None,
    ) -> None:
        """Apply playback feedback from the dashboard card."""
        if self._attr_state not in _ACTIVE_STATES or self._media_kind in (
            None,
            MEDIA_KIND_IMAGE,
        ):
            return

        now = dt_util.utcnow()
        changed = False

        if state is not None and state != self._attr_state:
            if state == MediaPlayerState.PAUSED:
                self._freeze_position(now)
            self._attr_state = MediaPlayerState(state)
            changed = True

        if (
            media_duration is not None
            and math.isfinite(media_duration)
            and (
                self._attr_media_duration is None
                or abs(self._attr_media_duration - media_duration) > 0.5
            )
        ):
            self._attr_media_duration = media_duration
            changed = True

        if media_position is not None and math.isfinite(media_position):
            expected = self._expected_position(now)
            if (
                changed
                or expected is None
                or abs(expected - media_position) > POSITION_DRIFT_TOLERANCE_SECONDS
            ):
                self._attr_media_position = media_position
                self._attr_media_position_updated_at = now
                changed = True

        if volume_level is not None and volume_level != self._attr_volume_level:
            self._attr_volume_level = volume_level
            changed = True

        if (
            is_volume_muted is not None
            and is_volume_muted != self._attr_is_volume_muted
        ):
            self._attr_is_volume_muted = is_volume_muted
            changed = True

        if repeat is not None:
            normalized = self._normalize_repeat(repeat)
            if normalized != self._attr_repeat:
                self._attr_repeat = normalized
                changed = True

        if self._attr_state == MediaPlayerState.PLAYING:
            self._schedule_feedback_timeout()
        else:
            self._cancel_feedback_timer()

        if changed:
            self._async_write()

    @callback
    def _async_write(self) -> None:
        self._update_supported_features()
        self.async_write_ha_state()

    def _update_supported_features(self) -> None:
        features = (
            MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
        )
        if self._media_url is not None:
            features |= MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.STOP
            if self._media_kind != MEDIA_KIND_IMAGE:
                features |= (
                    MediaPlayerEntityFeature.PAUSE
                    | MediaPlayerEntityFeature.SEEK
                    | MediaPlayerEntityFeature.REPEAT_SET
                )
        self._attr_supported_features = features

    def _clear_media(self) -> None:
        self._cancel_feedback_timer()
        self._media_url = None
        self._media_kind = None
        self._attr_media_content_id = None
        self._attr_media_content_type = None
        self._attr_media_position = None
        self._attr_media_duration = None
        self._attr_media_position_updated_at = None

    async def _async_cached_source(self, url: str) -> str:
        """Return the cached media-source id for a URL, caching it on first use."""
        if self._cache is None or not is_http_url(url):
            return url
        if (cached := await self._cache.async_lookup(url)) is not None:
            return cached
        self._cache.async_fetch_in_background(url, self._async_cache_failed)
        return url

    @callback
    def _async_cache_failed(self, err: Exception) -> None:
        self._last_error = str(err)
        if self.hass is not None:
            self.async_write_ha_state()

    @staticmethod
    def _normalize_repeat(repeat: RepeatMode | str | None) -> RepeatMode:
        if repeat in (RepeatMode.ONE, RepeatMode.ALL):
            return RepeatMode.ONE
        return RepeatMode.OFF

    def _expected_position(self, now: datetime) -> float | None:
        position = self._attr_media_position
        updated_at = self._attr_media_position_updated_at
        if position is None:
            return None
        if self._attr_state == MediaPlayerState.PLAYING and updated_at is not None:
            return position + (now - updated_at).total_seconds()
        return position

    def _freeze_position(self, now: datetime | None = None) -> None:
        now = now or dt_util.utcnow()
        position = self._expected_position(now)
        if position is not None:
            if self._attr_media_duration:
                position = min(position, self._attr_media_duration)
            self._attr_media_position = position
            self._attr_media_position_updated_at = now

    def _schedule_feedback_timeout(self) -> None:
        self._cancel_feedback_timer()
        self._feedback_unsub = async_call_later(
            self.hass, FEEDBACK_TIMEOUT_SECONDS, self._async_feedback_timeout
        )

    def _cancel_feedback_timer(self) -> None:
        if self._feedback_unsub is not None:
            self._feedback_unsub()
            self._feedback_unsub = None

    @callback
    def _async_feedback_timeout(self, _now: datetime) -> None:
        """No card reported while playing: progress is unknown."""
        self._feedback_unsub = None
        if self._attr_state != MediaPlayerState.PLAYING:
            return
        self._attr_media_position = None
        self._attr_media_duration = None
        self._attr_media_position_updated_at = None
        self._async_write()
