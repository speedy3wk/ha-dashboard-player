"""Media cache tests."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from homeassistant.core import HomeAssistant
import pytest

from custom_components.ha_dashboard_player.cache import CacheError, MediaCache

URL = "https://example.com/media/clip.MP4?token=1"


def test_filename_for() -> None:
    """Filenames are stable and keep a sane extension."""
    name = MediaCache.filename_for(URL)
    assert name == MediaCache.filename_for(URL)
    assert name.endswith(".mp4")
    assert len(name) == 36
    assert MediaCache.filename_for("https://x/a.weird-ext!").count(".") == 0


async def test_invalid_url(hass: HomeAssistant, tmp_path: Path) -> None:
    """Only http(s) URLs can be cached."""
    cache = MediaCache(hass, tmp_path)
    with pytest.raises(CacheError) as err:
        await cache.async_fetch("/local/video.mp4")
    assert err.value.translation_key == "invalid_cache_url"


async def test_fetch_dedup_and_lookup(
    hass: HomeAssistant, tmp_path: Path, aioclient_mock
) -> None:
    """Concurrent fetches share one download."""
    aioclient_mock.get(URL, content=b"abc")
    cache = MediaCache(hass, tmp_path)
    assert await cache.async_lookup(URL) is None

    first, second = await asyncio.gather(cache.async_fetch(URL), cache.async_fetch(URL))
    assert first == second
    assert first.startswith("media-source://media_source/local/")
    assert aioclient_mock.call_count == 1
    assert await cache.async_lookup(URL) == first
    assert await cache.async_fetch(URL) == first
    assert aioclient_mock.call_count == 1


async def test_file_too_large(
    hass: HomeAssistant, tmp_path: Path, aioclient_mock
) -> None:
    """Oversized downloads are aborted and leave no files behind."""
    aioclient_mock.get(URL, content=b"0123456789")
    cache = MediaCache(hass, tmp_path, max_file_bytes=5)
    with pytest.raises(CacheError) as err:
        await cache.async_fetch(URL)
    assert err.value.translation_key == "cache_file_too_large"
    assert list(tmp_path.iterdir()) == []


async def test_eviction(hass: HomeAssistant, tmp_path: Path, aioclient_mock) -> None:
    """The oldest files are removed above the total limit."""
    old = tmp_path / "old.mp4"
    old.write_bytes(b"x" * 8)
    os.utime(old, (1, 1))
    aioclient_mock.get(URL, content=b"y" * 8)
    cache = MediaCache(hass, tmp_path, max_total_bytes=10)
    media_id = await cache.async_fetch(URL)
    assert not old.exists()
    assert (tmp_path / media_id.rsplit("/", 1)[1]).exists()
