"""Integration setup tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
import pytest

from custom_components.ha_dashboard_player.const import (
    FRONTEND_SCRIPT,
    FRONTEND_URL_BASE,
)


@pytest.mark.usefixtures("setup_integration")
async def test_card_is_served(hass: HomeAssistant, hass_client) -> None:
    """The Lovelace card is served by the integration."""
    client = await hass_client()
    resp = await client.get(f"{FRONTEND_URL_BASE}/{FRONTEND_SCRIPT}")
    assert resp.status == 200
    assert "customElements.define" in await resp.text()


async def test_card_registered_as_module(hass: HomeAssistant) -> None:
    """The card is added to every dashboard with a cache-busting version."""
    from unittest.mock import AsyncMock, patch

    from custom_components.ha_dashboard_player.card import async_register_frontend

    hass.config.components.add("frontend")
    hass.http = AsyncMock()
    with patch(
        "homeassistant.components.frontend.add_extra_js_url"
    ) as mock_add_extra_js_url:
        await async_register_frontend(hass)

    url = mock_add_extra_js_url.call_args.args[1]
    assert url.startswith(f"{FRONTEND_URL_BASE}/{FRONTEND_SCRIPT}?v=")
    assert url.endswith("0.2.1")
