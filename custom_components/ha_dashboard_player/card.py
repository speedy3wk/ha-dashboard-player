"""Frontend registration for the HA Dashboard Player card."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN, FRONTEND_SCRIPT, FRONTEND_URL_BASE

FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card from the integration and load it on every dashboard."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL_BASE, str(FRONTEND_DIR), cache_headers=False)]
    )

    if "frontend" not in hass.config.components:
        return

    # Imported lazily: frontend is only an after_dependency.
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(
        hass, f"{FRONTEND_URL_BASE}/{FRONTEND_SCRIPT}?v={integration.version}"
    )
