"""Media player entity tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components import media_source
from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SEEK_POSITION,
    DOMAIN as MP_DOMAIN,
    SERVICE_PLAY_MEDIA,
    MediaPlayerEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_SEEK,
    SERVICE_MEDIA_STOP,
    SERVICE_REPEAT_SET,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.ha_dashboard_player.const import (
    CACHE_SUBDIR,
    DOMAIN,
    FEEDBACK_TIMEOUT_SECONDS,
)
from custom_components.ha_dashboard_player.media_player import media_kind

from .conftest import ENTITY_ID

VIDEO_URL = "https://example.com/clips/intro.mp4"
MEDIA_ID = "media-source://media_source/local/clips/intro.mp4"


async def _play(hass: HomeAssistant, media_id: str, media_type: str = "video") -> None:
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_PLAY_MEDIA,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_MEDIA_CONTENT_ID: media_id,
            ATTR_MEDIA_CONTENT_TYPE: media_type,
        },
        blocking=True,
    )


async def _report(hass: HomeAssistant, **data) -> None:
    await hass.services.async_call(
        DOMAIN, "report_state", {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )


@pytest.mark.parametrize(
    ("media_type", "mime_type", "url", "expected"),
    [
        ("image/jpeg", None, None, "image"),
        ("video", None, None, "video"),
        ("music", None, None, "audio"),
        ("audio/mpeg", None, None, "audio"),
        ("video", "image/png", None, "image"),
        ("url", None, "https://x/y/photo.JPG?size=1", "image"),
        ("url", None, "https://x/song.mp3", "audio"),
        ("url", None, "https://x/stream", "video"),
        (None, None, None, "video"),
    ],
)
def test_media_kind(
    media_type: str | None, mime_type: str | None, url: str | None, expected: str
) -> None:
    """MIME type wins over media type, the extension is the fallback."""
    assert media_kind(media_type, mime_type, url) == expected


@pytest.mark.usefixtures("setup_integration")
async def test_initial_state(hass: HomeAssistant) -> None:
    """The player starts idle with card attributes."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "idle"
    assert state.name == "Living Room"
    assert state.attributes["ha_dashboard_player"] is True
    assert state.attributes["media_url"] is None
    assert state.attributes["cache_enabled"] is False
    features = state.attributes[ATTR_SUPPORTED_FEATURES]
    assert features & MediaPlayerEntityFeature.PLAY_MEDIA
    assert not features & MediaPlayerEntityFeature.PAUSE
    assert not features & MediaPlayerEntityFeature.SHUFFLE_SET


@pytest.mark.usefixtures("setup_integration")
async def test_play_url(hass: HomeAssistant) -> None:
    """Plain URLs are passed to the card unchanged when caching is off."""
    await _play(hass, VIDEO_URL, "url")
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["media_url"] == VIDEO_URL
    assert state.attributes["media_kind"] == "video"
    assert state.attributes[ATTR_MEDIA_CONTENT_TYPE] == "video"
    assert state.attributes["media_position"] == 0
    features = state.attributes[ATTR_SUPPORTED_FEATURES]
    assert features & MediaPlayerEntityFeature.PAUSE
    assert features & MediaPlayerEntityFeature.SEEK
    assert features & MediaPlayerEntityFeature.REPEAT_SET


@pytest.mark.usefixtures("setup_integration")
async def test_play_image(hass: HomeAssistant) -> None:
    """Images cannot be paused, seeked or repeated."""
    await _play(hass, "https://example.com/photo.png", "image/png")
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["media_kind"] == "image"
    assert "media_position" not in state.attributes
    features = state.attributes[ATTR_SUPPORTED_FEATURES]
    assert features & MediaPlayerEntityFeature.STOP
    assert not features & MediaPlayerEntityFeature.PAUSE
    assert not features & MediaPlayerEntityFeature.REPEAT_SET


@pytest.mark.usefixtures("setup_integration")
async def test_play_media_source(hass: HomeAssistant) -> None:
    """Media source ids are validated and kept so the card can sign them."""
    resolved = media_source.PlayMedia(
        url="/media/local/clips/intro.mp4?authSig=x", mime_type="audio/mp4"
    )
    with patch(
        "homeassistant.components.media_source.async_resolve_media",
        return_value=resolved,
    ) as mock_resolve:
        await _play(hass, MEDIA_ID, "video")

    assert mock_resolve.call_args.args[1] == MEDIA_ID
    assert mock_resolve.call_args.args[2] == ENTITY_ID
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["media_url"] == MEDIA_ID
    assert state.attributes["media_kind"] == "audio"
    assert state.attributes[ATTR_MEDIA_CONTENT_TYPE] == "music"


@pytest.mark.usefixtures("setup_integration")
async def test_play_media_source_unresolvable(hass: HomeAssistant) -> None:
    """Resolve errors are raised and recorded."""
    with (
        patch(
            "homeassistant.components.media_source.async_resolve_media",
            side_effect=media_source.Unresolvable("missing"),
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await _play(hass, MEDIA_ID)
    assert err.value.translation_key == "unresolvable_media"
    state = hass.states.get(ENTITY_ID)
    assert state.state == "idle"
    assert state.attributes["last_error"] == "missing"


@pytest.mark.usefixtures("setup_integration")
async def test_play_unsupported(hass: HomeAssistant) -> None:
    """Only URLs, paths and media source ids are accepted."""
    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, "ftp://example.com/video.mp4")
    assert err.value.translation_key == "unsupported_media"


@pytest.mark.usefixtures("setup_integration")
async def test_pause_play_freezes_position(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Pausing stores the extrapolated position."""
    await _play(hass, VIDEO_URL)
    freezer.tick(timedelta(seconds=10))
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_MEDIA_PAUSE, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == "paused"
    assert state.attributes["media_position"] == pytest.approx(10)

    freezer.tick(timedelta(seconds=30))
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_MEDIA_PLAY, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["media_position"] == pytest.approx(10)


@pytest.mark.usefixtures("setup_integration")
async def test_seek_and_repeat(hass: HomeAssistant) -> None:
    """Seek sets the position, repeat all is coerced to one."""
    await _play(hass, VIDEO_URL)
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_MEDIA_SEEK,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MEDIA_SEEK_POSITION: 42},
        blocking=True,
    )
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_REPEAT_SET,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MEDIA_REPEAT: "all"},
        blocking=True,
    )
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["media_position"] == 42
    assert state.attributes[ATTR_MEDIA_REPEAT] == "one"


@pytest.mark.usefixtures("setup_integration")
async def test_stop_and_turn_off(hass: HomeAssistant) -> None:
    """Stop clears the screen, turn off switches the player off."""
    await _play(hass, VIDEO_URL)
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_MEDIA_STOP, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == "idle"
    assert state.attributes["media_url"] is None

    await _play(hass, VIDEO_URL)
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == "off"


@pytest.mark.usefixtures("setup_integration")
async def test_turn_on_keeps_paused(hass: HomeAssistant) -> None:
    """turn_on only leaves the off state and never resumes playback."""
    await _play(hass, VIDEO_URL)
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_MEDIA_PAUSE, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).state == "paused"

    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).state == "idle"


@pytest.mark.usefixtures("setup_integration")
async def test_report_state(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Card feedback updates position, duration, volume and state."""
    await _play(hass, VIDEO_URL)
    await _report(
        hass,
        state="playing",
        media_position=3.2,
        media_duration=120,
        volume_level=0.4,
        is_volume_muted=True,
        shuffle=False,
    )
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["media_position"] == 3.2
    assert state.attributes["media_duration"] == 120
    assert state.attributes["volume_level"] == 0.4
    assert state.attributes["is_volume_muted"] is True

    # Small drift is ignored to avoid state writes on every heartbeat.
    freezer.tick(timedelta(seconds=5))
    updated_at = state.attributes["media_position_updated_at"]
    await _report(hass, media_position=8.5)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["media_position_updated_at"] == updated_at

    await _report(hass, state="paused", media_position=9)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "paused"
    assert state.attributes["media_position"] == 9


@pytest.mark.usefixtures("setup_integration")
async def test_report_state_ignored_when_idle(hass: HomeAssistant) -> None:
    """A stale card cannot resurrect a stopped player."""
    await _report(hass, state="playing", media_position=5)
    assert hass.states.get(ENTITY_ID).state == "idle"


@pytest.mark.usefixtures("setup_integration")
async def test_report_state_validation(hass: HomeAssistant) -> None:
    """Invalid feedback is rejected."""
    await _play(hass, VIDEO_URL)
    with pytest.raises(Exception, match="state"):
        await _report(hass, state="buffering")


@pytest.mark.usefixtures("setup_integration")
async def test_feedback_timeout(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Without card feedback the position becomes unknown."""
    await _play(hass, VIDEO_URL)
    await _report(hass, media_position=1, media_duration=60)
    freezer.tick(timedelta(seconds=FEEDBACK_TIMEOUT_SECONDS + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert "media_position" not in state.attributes
    assert "media_duration" not in state.attributes


@pytest.mark.usefixtures("setup_integration")
async def test_clear_screen(hass: HomeAssistant) -> None:
    """clear_screen blanks the card."""
    await _play(hass, VIDEO_URL)
    await hass.services.async_call(
        DOMAIN, "clear_screen", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    state = hass.states.get(ENTITY_ID)
    assert state.state == "idle"
    assert state.attributes["media_url"] is None


@pytest.mark.usefixtures("setup_integration")
async def test_preload_without_cache(hass: HomeAssistant) -> None:
    """Preloading needs the cache option."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "preload_media",
            {ATTR_ENTITY_ID: ENTITY_ID, "media_url": VIDEO_URL},
            blocking=True,
        )
    assert err.value.translation_key == "cache_disabled"


@pytest.mark.parametrize(
    "entry_options", [{"enable_cache": True, "restore_last_media": True}]
)
@pytest.mark.usefixtures("setup_integration")
async def test_preload_and_play_cached(
    hass: HomeAssistant, media_dir: Path, aioclient_mock
) -> None:
    """Preloaded media is played from the authenticated media source."""
    aioclient_mock.get(VIDEO_URL, content=b"0123456789")
    await hass.services.async_call(
        DOMAIN,
        "preload_media",
        {ATTR_ENTITY_ID: ENTITY_ID, "media_url": VIDEO_URL},
        blocking=True,
    )
    files = list((media_dir / CACHE_SUBDIR).iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == b"0123456789"
    assert files[0].suffix == ".mp4"

    await _play(hass, VIDEO_URL)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["cache_enabled"] is True
    assert state.attributes["media_url"] == (
        f"media-source://media_source/local/{CACHE_SUBDIR}/{files[0].name}"
    )
    assert state.attributes[ATTR_MEDIA_CONTENT_ID] == VIDEO_URL


@pytest.mark.parametrize(
    "entry_options", [{"enable_cache": True, "restore_last_media": True}]
)
@pytest.mark.usefixtures("setup_integration")
async def test_play_caches_in_background(
    hass: HomeAssistant, media_dir: Path, aioclient_mock
) -> None:
    """The first play streams the URL and caches it for the next time."""
    aioclient_mock.get(VIDEO_URL, content=b"data")
    await _play(hass, VIDEO_URL)
    assert hass.states.get(ENTITY_ID).attributes["media_url"] == VIDEO_URL
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(list((media_dir / CACHE_SUBDIR).iterdir())) == 1


@pytest.mark.parametrize(
    "entry_options", [{"enable_cache": True, "restore_last_media": True}]
)
@pytest.mark.usefixtures("setup_integration")
async def test_preload_failure(hass: HomeAssistant, aioclient_mock) -> None:
    """Download errors are reported to the caller."""
    aioclient_mock.get(VIDEO_URL, status=404)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "preload_media",
            {ATTR_ENTITY_ID: ENTITY_ID, "media_url": VIDEO_URL},
            blocking=True,
        )
    assert err.value.translation_key == "cache_download_failed"
    assert hass.states.get(ENTITY_ID).attributes["last_error"]


async def test_restore_migrates_signed_url(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    """Expiring signed URLs from older versions are replaced by the media id."""
    mock_restore_cache(
        hass,
        [
            State(
                ENTITY_ID,
                "playing",
                {
                    "media_url": "http://ha.local:8123/media/local/a.mp4?authSig=old",
                    ATTR_MEDIA_CONTENT_ID: "media-source://media_source/local/a.mp4",
                    ATTR_MEDIA_CONTENT_TYPE: "video",
                    "volume_level": 0.3,
                    "repeat": "all",
                },
            )
        ],
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["media_url"] == "media-source://media_source/local/a.mp4"
    assert state.attributes["media_kind"] == "video"
    assert state.attributes["volume_level"] == 0.3
    assert state.attributes[ATTR_MEDIA_REPEAT] == "one"


@pytest.mark.parametrize(
    "entry_options", [{"enable_cache": False, "restore_last_media": False}]
)
async def test_restore_disabled(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    """Nothing is restored when the option is off."""
    mock_restore_cache(hass, [State(ENTITY_ID, "playing", {"media_url": VIDEO_URL})])
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "idle"


async def test_unload(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "unavailable"
