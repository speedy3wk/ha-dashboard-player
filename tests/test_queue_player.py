"""Play queue (playlist) tests of the media player entity."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_ENQUEUE,
    ATTR_MEDIA_PLAYLIST,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_TITLE,
    DOMAIN as MP_DOMAIN,
    SERVICE_CLEAR_PLAYLIST,
    SERVICE_PLAY_MEDIA,
    MediaPlayerEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_REPEAT_SET,
    SERVICE_SHUFFLE_SET,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.ha_dashboard_player.const import DOMAIN

from .conftest import ENTITY_ID

A = "https://example.com/a.mp4"
B = "https://example.com/b.mp4"
C = "https://example.com/c.mp4"
IMG_A = "https://example.com/a.jpg"
IMG_B = "https://example.com/b.jpg"
IMG_C = "https://example.com/c.jpg"
FOLDER = "media-source://media_source/local/show"


async def _play(
    hass: HomeAssistant,
    media_id: str,
    enqueue: str | None = None,
    media_type: str = "url",
) -> None:
    data = {
        ATTR_ENTITY_ID: ENTITY_ID,
        ATTR_MEDIA_CONTENT_ID: media_id,
        ATTR_MEDIA_CONTENT_TYPE: media_type,
    }
    if enqueue:
        data[ATTR_MEDIA_ENQUEUE] = enqueue
    await hass.services.async_call(MP_DOMAIN, SERVICE_PLAY_MEDIA, data, blocking=True)


async def _call(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(
        MP_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )


async def _ended(hass: HomeAssistant, media_content_id: str | None = None) -> None:
    data = {ATTR_ENTITY_ID: ENTITY_ID}
    if media_content_id is not None:
        data["media_content_id"] = media_content_id
    await hass.services.async_call(DOMAIN, "media_ended", data, blocking=True)


def _current(hass: HomeAssistant) -> str:
    return hass.states.get(ENTITY_ID).attributes[ATTR_MEDIA_CONTENT_ID]


def _features(hass: HomeAssistant) -> int:
    return hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES]


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("setup_integration")
async def test_enqueue_modes(hass: HomeAssistant) -> None:
    """add, next, play and replace follow the HA enqueue semantics."""
    assert _features(hass) & MediaPlayerEntityFeature.MEDIA_ENQUEUE

    await _play(hass, A, "add")
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert _current(hass) == A
    assert state.attributes["queue_size"] == 1
    assert state.attributes["queue_position"] == 1
    assert state.attributes[ATTR_MEDIA_TITLE] == "a.mp4"
    assert not _features(hass) & MediaPlayerEntityFeature.NEXT_TRACK

    await _play(hass, C, "add")
    await _play(hass, B, "next")
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == A
    assert state.attributes["queue_size"] == 3
    features = _features(hass)
    assert features & MediaPlayerEntityFeature.NEXT_TRACK
    assert features & MediaPlayerEntityFeature.PREVIOUS_TRACK
    assert features & MediaPlayerEntityFeature.CLEAR_PLAYLIST
    assert features & MediaPlayerEntityFeature.SHUFFLE_SET

    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    assert _current(hass) == B
    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    assert _current(hass) == C

    await _play(hass, IMG_A, "play")
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == IMG_A
    assert state.attributes["queue_position"] == 4

    await _play(hass, B)
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == B
    assert state.attributes["queue_size"] == 1


@pytest.mark.usefixtures("setup_integration")
async def test_next_previous_and_repeat(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Navigation stops at the end unless repeat all; previous restarts first."""
    await _play(hass, A)
    await _play(hass, B, "add")

    await _call(hass, SERVICE_MEDIA_PREVIOUS_TRACK)
    assert _current(hass) == A

    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    assert _current(hass) == B

    await _call(hass, SERVICE_REPEAT_SET, **{ATTR_MEDIA_REPEAT: "all"})
    assert hass.states.get(ENTITY_ID).attributes[ATTR_MEDIA_REPEAT] == "all"
    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    assert _current(hass) == A

    freezer.tick(timedelta(seconds=10))
    await _call(hass, SERVICE_MEDIA_PREVIOUS_TRACK)
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == A
    assert state.attributes["media_position"] == 0

    await _call(hass, SERVICE_MEDIA_PREVIOUS_TRACK)
    assert _current(hass) == B


@pytest.mark.usefixtures("setup_integration")
async def test_media_ended(hass: HomeAssistant) -> None:
    """An end report advances once, even when several cards report it."""
    await _play(hass, A)
    await _play(hass, B, "add")

    await _ended(hass, A)
    assert _current(hass) == B
    # A second card reporting the same end must not skip B.
    await _ended(hass, A)
    assert _current(hass) == B

    await _call(hass, SERVICE_REPEAT_SET, **{ATTR_MEDIA_REPEAT: "one"})
    await _ended(hass, B)
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == B
    assert state.attributes["media_position"] == 0

    await _call(hass, SERVICE_REPEAT_SET, **{ATTR_MEDIA_REPEAT: "off"})
    await _ended(hass)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "idle"
    assert state.attributes["media_url"] is None
    assert state.attributes["queue_size"] == 0

    # Late reports for an idle player are ignored.
    await _ended(hass, B)
    assert hass.states.get(ENTITY_ID).state == "idle"


@pytest.mark.usefixtures("setup_integration")
async def test_media_ended_single_item(hass: HomeAssistant) -> None:
    """Without a queue the end of the media stops playback, as before."""
    await _play(hass, A)
    await _ended(hass, A)
    assert hass.states.get(ENTITY_ID).state == "idle"


@pytest.mark.usefixtures("setup_integration")
async def test_shuffle_and_clear_playlist(hass: HomeAssistant) -> None:
    """Shuffle keeps the current item, clear_playlist keeps only it."""
    await _play(hass, A)
    await _play(hass, B, "add")
    await _play(hass, C, "add")

    await _call(hass, SERVICE_SHUFFLE_SET, **{ATTR_MEDIA_SHUFFLE: True})
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_MEDIA_SHUFFLE] is True
    assert state.attributes["queue_position"] == 1
    assert _current(hass) == A

    await _call(hass, SERVICE_SHUFFLE_SET, **{ATTR_MEDIA_SHUFFLE: False})
    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    assert _current(hass) == B

    await _call(hass, SERVICE_CLEAR_PLAYLIST)
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == B
    assert state.attributes["queue_size"] == 1
    assert not _features(hass) & MediaPlayerEntityFeature.NEXT_TRACK


@pytest.mark.parametrize(
    "entry_options",
    [{"enable_cache": False, "restore_last_media": True, "image_duration": 5}],
)
@pytest.mark.usefixtures("setup_integration")
async def test_image_slideshow(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Queued images advance after the configured duration and can be paused."""
    await _play(hass, IMG_A)
    await _tick(hass, freezer, 6)
    assert _current(hass) == IMG_A

    await _play(hass, IMG_B, "add")
    await _play(hass, IMG_C, "add")
    assert _features(hass) & MediaPlayerEntityFeature.PAUSE
    assert not _features(hass) & MediaPlayerEntityFeature.SEEK
    await _tick(hass, freezer, 5)
    assert _current(hass) == IMG_B

    await _call(hass, SERVICE_MEDIA_PAUSE)
    assert hass.states.get(ENTITY_ID).state == "paused"
    await _tick(hass, freezer, 20)
    assert _current(hass) == IMG_B

    await _call(hass, SERVICE_MEDIA_PLAY)
    await _tick(hass, freezer, 5)
    assert _current(hass) == IMG_C

    # The last image stays on screen without repeat.
    await _tick(hass, freezer, 20)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert _current(hass) == IMG_C

    await _call(hass, SERVICE_REPEAT_SET, **{ATTR_MEDIA_REPEAT: "all"})
    await _tick(hass, freezer, 5)
    assert _current(hass) == IMG_A

    await _call(hass, SERVICE_REPEAT_SET, **{ATTR_MEDIA_REPEAT: "one"})
    await _tick(hass, freezer, 20)
    assert _current(hass) == IMG_A


@pytest.fixture
def show_folder(media_dir: Path) -> Path:
    """Create a local media folder with media, a subfolder and other files."""
    folder = media_dir / "show"
    (folder / "extras").mkdir(parents=True)
    (folder / "extras" / "z.mp4").write_bytes(b"x")
    (folder / "b.jpg").write_bytes(b"x")
    (folder / "a.mp4").write_bytes(b"x")
    (folder / "notes.txt").write_text("x")
    (media_dir / "empty").mkdir()
    return folder


@pytest.mark.usefixtures("setup_integration", "show_folder")
async def test_browse_marks_folders_playable(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Local folders get a play button in the media browser."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "media_player/browse_media",
            "entity_id": ENTITY_ID,
            "media_content_id": FOLDER,
            "media_content_type": "directory",
        }
    )
    response = await client.receive_json()
    assert response["success"]
    result = response["result"]
    assert result["can_play"] is True
    assert result["media_content_type"] == "directory"
    children = {child["title"]: child for child in result["children"]}
    assert set(children) == {"extras", "a.mp4", "b.jpg"}
    assert children["extras"]["can_play"] is True
    assert children["a.mp4"]["media_content_type"] == "video/mp4"


@pytest.mark.parametrize("media_type", ["directory", "video"])
@pytest.mark.usefixtures("setup_integration", "show_folder")
async def test_play_folder(hass: HomeAssistant, media_type: str) -> None:
    """A folder is played as a playlist of its playable files."""
    await _play(hass, FOLDER, media_type=media_type)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "playing"
    assert state.attributes["queue_size"] == 2
    assert state.attributes[ATTR_MEDIA_PLAYLIST] == "show"
    assert state.attributes[ATTR_MEDIA_TITLE] == "a.mp4"
    assert state.attributes["media_url"] == f"{FOLDER}/a.mp4"
    assert state.attributes["media_kind"] == "video"

    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["media_url"] == f"{FOLDER}/b.jpg"
    assert state.attributes["media_kind"] == "image"

    await _call(hass, SERVICE_CLEAR_PLAYLIST)
    assert ATTR_MEDIA_PLAYLIST not in hass.states.get(ENTITY_ID).attributes


@pytest.mark.usefixtures("setup_integration", "show_folder")
async def test_enqueue_folder(hass: HomeAssistant) -> None:
    """A folder can be added to an existing queue."""
    await _play(hass, A)
    await _play(hass, FOLDER, "add", "directory")
    state = hass.states.get(ENTITY_ID)
    assert _current(hass) == A
    assert state.attributes["queue_size"] == 3
    assert ATTR_MEDIA_PLAYLIST not in state.attributes


@pytest.mark.usefixtures("setup_integration", "show_folder")
async def test_play_empty_folder(hass: HomeAssistant) -> None:
    """A folder without playable files raises a translated error."""
    with pytest.raises(ServiceValidationError) as err:
        await _play(hass, "media-source://media_source/local/empty", None, "directory")
    assert err.value.translation_key == "empty_folder"
    assert hass.states.get(ENTITY_ID).state == "idle"


async def test_restore_queue(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path
) -> None:
    """Queue, position, shuffle, repeat and playlist survive a restart."""
    items = [
        {"media_content_id": url, "source": url, "kind": "video", "title": title}
        for url, title in ((A, "a.mp4"), (B, "b.mp4"), (C, "c.mp4"))
    ]
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY_ID, "paused", {"volume_level": 0.5}),
                {
                    "queue": {"items": items, "index": 1, "unshuffled": [2, 1, 0]},
                    "repeat": "all",
                    "playlist": "Mix",
                },
            )
        ],
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "paused"
    assert state.attributes["media_url"] == B
    assert state.attributes["queue_position"] == 2
    assert state.attributes["queue_size"] == 3
    assert state.attributes[ATTR_MEDIA_REPEAT] == "all"
    assert state.attributes[ATTR_MEDIA_SHUFFLE] is True
    assert state.attributes[ATTR_MEDIA_PLAYLIST] == "Mix"
    assert state.attributes[ATTR_MEDIA_TITLE] == "b.mp4"
    assert state.attributes["volume_level"] == 0.5

    await _call(hass, SERVICE_SHUFFLE_SET, **{ATTR_MEDIA_SHUFFLE: False})
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["queue_position"] == 2
    await _call(hass, SERVICE_MEDIA_NEXT_TRACK)
    assert _current(hass) == A
