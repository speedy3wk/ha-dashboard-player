"""Media player entity for HA Dashboard Player."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.components.media_player import BrowseMedia, MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.components.media_source import (
    async_browse_media,
    async_resolve_media,
    is_media_source_id,
)
from homeassistant.components.media_player import async_process_play_media_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CACHE_ENABLED,
    ATTR_CACHED_MEDIA_URL,
    ATTR_LAST_ERROR,
    ATTR_MEDIA_URL,
    CONF_ENABLE_CACHE,
    CONF_NAME,
    CONF_RESTORE_LAST_MEDIA,
    DEFAULT_ENABLE_CACHE,
    DEFAULT_NAME,
    DEFAULT_RESTORE_LAST_MEDIA,
    DOMAIN,
    SERVICE_CLEAR_SCREEN,
    SERVICE_FIELD_MEDIA_URL,
    SERVICE_PRELOAD_MEDIA,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up HA Dashboard Player from a config entry."""
    name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, DEFAULT_NAME))
    enable_cache = entry.options.get(
        CONF_ENABLE_CACHE, entry.data.get(CONF_ENABLE_CACHE, DEFAULT_ENABLE_CACHE)
    )
    restore_last_media = entry.options.get(
        CONF_RESTORE_LAST_MEDIA,
        entry.data.get(CONF_RESTORE_LAST_MEDIA, DEFAULT_RESTORE_LAST_MEDIA),
    )

    player = HADashboardPlayer(
        hass=hass,
        name=name,
        entry_id=entry.entry_id,
        enable_cache=enable_cache,
        restore_last_media=restore_last_media,
    )

    async_add_entities([player], True)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_PRELOAD_MEDIA,
        {vol.Required(SERVICE_FIELD_MEDIA_URL): cv.string},
        "async_preload_media",
    )
    platform.async_register_entity_service(
        SERVICE_CLEAR_SCREEN,
        {},
        "async_clear_screen",
    )


class HADashboardPlayer(MediaPlayerEntity, RestoreEntity):
    """Virtual media player for driving the dashboard UI."""

    _attr_state = MediaPlayerState.IDLE
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.REPEAT_SET
        | MediaPlayerEntityFeature.SHUFFLE_SET
    )

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entry_id: str,
        enable_cache: bool,
        restore_last_media: bool,
    ) -> None:
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{entry_id}"
        self._media_url: str | None = None
        self._cached_media_url: str | None = None
        self._cache_enabled = enable_cache
        self._restore_last_media = restore_last_media
        self._last_error: str | None = None
        self._cache_map: dict[str, str] = {}
        self._cache_dir = Path(hass.config.path("www/ha-dashboard-player/cache"))

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()

        if not self._restore_last_media:
            return

        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        try:
            self._attr_state = MediaPlayerState(last_state.state)
        except ValueError:
            self._attr_state = MediaPlayerState.IDLE
        self._attr_media_content_type = last_state.attributes.get("media_content_type")
        self._attr_media_content_id = last_state.attributes.get("media_content_id")
        self._attr_media_position = last_state.attributes.get("media_position")
        self._attr_media_duration = last_state.attributes.get("media_duration")
        self._attr_volume_level = last_state.attributes.get("volume_level")
        self._attr_is_volume_muted = last_state.attributes.get("is_volume_muted")
        self._attr_repeat = last_state.attributes.get("repeat")
        self._attr_shuffle = last_state.attributes.get("shuffle")
        self._media_url = last_state.attributes.get(ATTR_MEDIA_URL)
        self._cached_media_url = last_state.attributes.get(ATTR_CACHED_MEDIA_URL)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_MEDIA_URL: self._media_url,
            ATTR_CACHED_MEDIA_URL: self._cached_media_url,
            ATTR_CACHE_ENABLED: self._cache_enabled,
            ATTR_LAST_ERROR: self._last_error,
        }

    async def async_turn_on(self) -> None:
        """Turn on the player."""
        if self._media_url:
            self._attr_state = MediaPlayerState.PLAYING
        else:
            self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off the player and clear output."""
        await self.async_clear_screen()

    async def async_play(self) -> None:
        """Resume playback."""
        if self._media_url:
            self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    def media_play(self) -> None:
        """Resume playback (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_play())

    async def async_pause(self) -> None:
        """Pause playback."""
        if self._media_url:
            self._attr_state = MediaPlayerState.PAUSED
        self.async_write_ha_state()

    def media_pause(self) -> None:
        """Pause playback (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_pause())

    async def async_stop(self) -> None:
        """Stop playback and clear the screen."""
        await self.async_clear_screen()

    def media_stop(self) -> None:
        """Stop playback (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_stop())

    async def async_media_seek(self, position: float) -> None:
        """Seek to a position."""
        self._attr_media_position = position
        self._attr_media_position_updated_at = datetime.now(timezone.utc)
        self.async_write_ha_state()

    def media_seek(self, position: float) -> None:
        """Seek to a position (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_media_seek(position))

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume."""
        self._attr_volume_level = volume
        self.async_write_ha_state()

    def set_volume_level(self, volume: float) -> None:
        """Set volume (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_set_volume_level(volume))

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the player."""
        self._attr_is_volume_muted = mute
        self.async_write_ha_state()

    def mute_volume(self, mute: bool) -> None:
        """Mute the player (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_mute_volume(mute))

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode."""
        self._attr_repeat = repeat
        self.async_write_ha_state()

    def set_repeat(self, repeat: str) -> None:
        """Set repeat mode (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_set_repeat(repeat))

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle."""
        self._attr_shuffle = shuffle
        self.async_write_ha_state()

    def set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle (sync wrapper)."""
        self._run_coroutine_threadsafe(self.async_set_shuffle(shuffle))

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Start playing media."""
        self._last_error = None
        resolved_url = await self._resolve_media_url(media_id)
        if resolved_url is None:
            self._last_error = f"Unable to resolve media: {media_id}"
            self.async_write_ha_state()
            return

        final_url = resolved_url
        cached_url = await self._maybe_cache_media(resolved_url)
        if cached_url:
            final_url = cached_url
            self._cached_media_url = cached_url
        else:
            self._cached_media_url = None

        self._media_url = final_url
        self._attr_media_content_type = media_type
        self._attr_media_content_id = media_id
        self._attr_media_position = 0
        self._attr_media_position_updated_at = datetime.now(timezone.utc)
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    def play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Start playing media (sync wrapper)."""
        self._run_coroutine_threadsafe(
            self.async_play_media(media_type, media_id, **kwargs)
        )

    def _run_coroutine_threadsafe(self, coro) -> None:
        """Schedule a coroutine from a worker thread."""
        asyncio.run_coroutine_threadsafe(coro, self.hass.loop)

    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        """Return media browser structure."""
        if media_content_id in (None, "root"):
            media_content_id = "media-source://"

        try:
            return await async_browse_media(
                self.hass, media_content_id, entity_id=self.entity_id
            )
        except TypeError:
            return await async_browse_media(self.hass, media_content_id)

    async def async_preload_media(self, media_url: str) -> None:
        """Preload a media URL into cache."""
        self._last_error = None
        cached_url = await self._maybe_cache_media(media_url)
        if cached_url:
            self._cached_media_url = cached_url
        self.async_write_ha_state()

    async def async_clear_screen(self) -> None:
        """Clear output and set state to idle."""
        self._media_url = None
        self._cached_media_url = None
        self._attr_media_content_type = None
        self._attr_media_content_id = None
        self._attr_media_position = None
        self._attr_media_duration = None
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def _resolve_media_url(self, media_id: str) -> str | None:
        """Resolve a media ID into a playable URL."""
        if is_media_source_id(media_id):
            try:
                resolved = await async_resolve_media(
                    self.hass, media_id, entity_id=self.entity_id
                )
            except TypeError:
                resolved = await async_resolve_media(self.hass, media_id)
            return async_process_play_media_url(self.hass, resolved.url)

        return media_id

    async def _maybe_cache_media(self, media_url: str) -> str | None:
        """Download media to local cache when enabled."""
        if not self._cache_enabled:
            return None

        if not media_url.startswith("http://") and not media_url.startswith("https://"):
            return None

        if media_url in self._cache_map:
            return self._cache_map[media_url]

        parsed = urlparse(media_url)
        suffix = Path(parsed.path).suffix
        digest = hashlib.sha256(media_url.encode("utf-8")).hexdigest()
        filename = f"{digest}{suffix}"
        target = self._cache_dir / filename
        target_url = f"/local/ha-dashboard-player/cache/{filename}"

        self._cache_dir.mkdir(parents=True, exist_ok=True)

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(media_url) as resp:
                resp.raise_for_status()
                data = await resp.read()
        except Exception as err:  # pylint: disable=broad-except
            self._last_error = str(err)
            return None

        await asyncio.to_thread(target.write_bytes, data)
        self._cache_map[media_url] = target_url
        return target_url

    @property
    def repeat(self) -> str | None:
        """Return repeat setting."""
        return self._attr_repeat

    @property
    def shuffle(self) -> bool | None:
        """Return shuffle setting."""
        return self._attr_shuffle

    @property
    def media_position_updated_at(self) -> datetime | None:
        """Return media position updated at."""
        return getattr(self, "_attr_media_position_updated_at", None)
