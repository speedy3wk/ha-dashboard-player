"""Media cache for HA Dashboard Player.

Remote media is downloaded into the local media directory and exposed through the
built-in ``media_source`` local source, so cached files are only reachable with
Home Assistant authentication.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import hashlib
import logging
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse

import aiohttp
from aiohttp import hdrs
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CACHE_DOWNLOAD_CHUNK_BYTES,
    CACHE_MAX_FILE_BYTES,
    CACHE_MAX_TOTAL_BYTES,
    CACHE_READ_TIMEOUT_SECONDS,
    CACHE_SUBDIR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_LOCAL_MEDIA_SOURCE_PREFIX = "media-source://media_source/local"
_SUFFIX_RE = re.compile(r"^\.[a-z0-9]{1,8}$")


class CacheError(HomeAssistantError):
    """Raised when media cannot be cached."""


def is_http_url(value: str) -> bool:
    """Return True for absolute http(s) URLs."""
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class MediaCache:
    """Download remote media into the local media directory."""

    def __init__(
        self,
        hass: HomeAssistant,
        directory: Path,
        max_file_bytes: int = CACHE_MAX_FILE_BYTES,
        max_total_bytes: int = CACHE_MAX_TOTAL_BYTES,
    ) -> None:
        """Initialize the cache."""
        self._hass = hass
        self._directory = directory
        self._max_file_bytes = max_file_bytes
        self._max_total_bytes = max_total_bytes
        self._downloads: dict[str, asyncio.Task[str]] = {}

    @classmethod
    def from_hass(cls, hass: HomeAssistant) -> MediaCache | None:
        """Create a cache in the local media directory, if one is configured."""
        local_dir = hass.config.media_dirs.get("local")
        if local_dir is None:
            _LOGGER.warning(
                "Media cache disabled: no 'local' media directory is configured"
            )
            return None
        return cls(hass, Path(local_dir) / CACHE_SUBDIR)

    @property
    def directory(self) -> Path:
        """Return the cache directory."""
        return self._directory

    @staticmethod
    def filename_for(url: str) -> str:
        """Return the stable cache filename for a URL."""
        suffix = Path(urlparse(url).path).suffix.lower()
        if not _SUFFIX_RE.match(suffix):
            suffix = ""
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return f"{digest}{suffix}"

    @staticmethod
    def media_source_id_for(filename: str) -> str:
        """Return the media-source id of a cached file."""
        return f"{_LOCAL_MEDIA_SOURCE_PREFIX}/{CACHE_SUBDIR}/{filename}"

    async def async_lookup(self, url: str) -> str | None:
        """Return the media-source id if the URL is already cached."""
        filename = self.filename_for(url)
        target = self._directory / filename
        if await self._hass.async_add_executor_job(target.is_file):
            return self.media_source_id_for(filename)
        return None

    async def async_fetch(self, url: str) -> str:
        """Download a URL (deduplicated) and return its media-source id."""
        if not is_http_url(url):
            raise CacheError(
                translation_domain=DOMAIN,
                translation_key="invalid_cache_url",
                translation_placeholders={"url": url},
            )
        if (cached := await self.async_lookup(url)) is not None:
            return cached

        task = self._downloads.get(url)
        if task is None:
            task = self._hass.async_create_background_task(
                self._async_download(url), f"{DOMAIN} cache download"
            )
            self._downloads[url] = task
            task.add_done_callback(lambda _: self._downloads.pop(url, None))
        return await asyncio.shield(task)

    def async_fetch_in_background(
        self, url: str, on_error: Callable[[Exception], None] | None = None
    ) -> None:
        """Start caching a URL without waiting for the result."""

        async def _runner() -> None:
            try:
                await self.async_fetch(url)
            except (CacheError, aiohttp.ClientError, TimeoutError, OSError) as err:
                _LOGGER.warning("Caching %s failed: %s", url, err)
                if on_error is not None:
                    on_error(err)

        self._hass.async_create_background_task(_runner(), f"{DOMAIN} cache {url}")

    async def async_shutdown(self) -> None:
        """Cancel running downloads."""
        tasks = list(self._downloads.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _async_download(self, url: str) -> str:
        filename = self.filename_for(url)
        target = self._directory / filename
        # Unique per download: several players may cache the same URL at once.
        partial = target.with_name(f".{filename}.{secrets.token_hex(4)}.part")
        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(
            total=None, sock_connect=30, sock_read=CACHE_READ_TIMEOUT_SECONDS
        )

        await self._hass.async_add_executor_job(self._prepare_directory)
        handle = await self._hass.async_add_executor_job(partial.open, "wb")
        try:
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                length = resp.headers.get(hdrs.CONTENT_LENGTH, "")
                if length.isdigit() and int(length) > self._max_file_bytes:
                    raise self._too_large(url)
                written = 0
                async for chunk in resp.content.iter_chunked(
                    CACHE_DOWNLOAD_CHUNK_BYTES
                ):
                    written += len(chunk)
                    if written > self._max_file_bytes:
                        raise self._too_large(url)
                    await self._hass.async_add_executor_job(handle.write, chunk)
            await self._hass.async_add_executor_job(handle.close)
            await self._hass.async_add_executor_job(os.replace, partial, target)
        except BaseException:
            await self._hass.async_add_executor_job(
                self._discard_partial, handle, partial
            )
            raise

        _LOGGER.debug("Cached %s as %s (%d bytes)", url, target, written)
        await self._hass.async_add_executor_job(self._enforce_total_limit, target)
        return self.media_source_id_for(filename)

    def _too_large(self, url: str) -> CacheError:
        return CacheError(
            translation_domain=DOMAIN,
            translation_key="cache_file_too_large",
            translation_placeholders={
                "url": url,
                "limit_mb": str(self._max_file_bytes // 1024**2),
            },
        )

    def _prepare_directory(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _discard_partial(handle, partial: Path) -> None:
        handle.close()
        partial.unlink(missing_ok=True)

    def _enforce_total_limit(self, keep: Path) -> None:
        """Delete the least recently modified files above the total size limit."""
        files = [
            (entry.stat().st_mtime, entry.stat().st_size, entry)
            for entry in self._directory.iterdir()
            if entry.is_file() and not entry.name.startswith(".")
        ]
        total = sum(size for _, size, _ in files)
        for _, size, entry in sorted(files, key=lambda item: item[0]):
            if total <= self._max_total_bytes:
                break
            if entry == keep:
                continue
            _LOGGER.debug("Evicting cached media %s", entry)
            entry.unlink(missing_ok=True)
            total -= size
