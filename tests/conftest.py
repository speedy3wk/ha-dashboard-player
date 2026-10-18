"""Fixtures for HA Dashboard Player tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_dashboard_player.const import (
    CONF_ENABLE_CACHE,
    CONF_RESTORE_LAST_MEDIA,
    DOMAIN,
)

ENTITY_ID = "media_player.living_room"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def media_dir(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Configure a local media directory."""
    hass.config.media_dirs = {"local": str(tmp_path)}
    return tmp_path


@pytest.fixture
def entry_options() -> dict[str, bool]:
    """Options of the mock config entry."""
    return {CONF_ENABLE_CACHE: False, CONF_RESTORE_LAST_MEDIA: True}


@pytest.fixture
def config_entry(entry_options: dict[str, bool]) -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Living Room",
        data={CONF_NAME: "Living Room"},
        options=entry_options,
        entry_id="01TESTENTRY",
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, media_dir: Path
) -> MockConfigEntry:
    """Set up the integration with the mock entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def mock_setup_entry() -> Generator[None]:
    """Skip entry setup in config flow tests."""
    with patch(
        "custom_components.ha_dashboard_player.async_setup_entry", return_value=True
    ) as mock:
        yield mock
