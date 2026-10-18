"""Config and options flow tests."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_dashboard_player.const import (
    CONF_ENABLE_CACHE,
    CONF_RESTORE_LAST_MEDIA,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_user_flow(hass: HomeAssistant) -> None:
    """Create an entry; the name is kept as typed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "  Küche Display ",
            CONF_ENABLE_CACHE: True,
            CONF_RESTORE_LAST_MEDIA: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Küche Display"
    assert result["data"] == {CONF_NAME: "Küche Display"}
    assert result["options"] == {
        CONF_ENABLE_CACHE: True,
        CONF_RESTORE_LAST_MEDIA: False,
    }


async def test_user_flow_empty_name(hass: HomeAssistant) -> None:
    """An empty name shows an error and can be corrected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "   ", CONF_ENABLE_CACHE: False, CONF_RESTORE_LAST_MEDIA: True},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NAME: "name_required"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Flur", CONF_ENABLE_CACHE: False, CONF_RESTORE_LAST_MEDIA: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_duplicate(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The same name cannot be configured twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Living Room",
            CONF_ENABLE_CACHE: False,
            CONF_RESTORE_LAST_MEDIA: True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Options are stored and prefilled from the entry."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ENABLE_CACHE: True, CONF_RESTORE_LAST_MEDIA: False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {
        CONF_ENABLE_CACHE: True,
        CONF_RESTORE_LAST_MEDIA: False,
    }
