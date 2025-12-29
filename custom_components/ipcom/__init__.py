"""The IPCom Home Anywhere Blue integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLI_PATH,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import IPComCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPCom from a config entry."""
    # Extract config
    cli_path = entry.data[CONF_CLI_PATH]
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Create coordinator
    coordinator = IPComCoordinator(
        hass=hass,
        cli_path=cli_path,
        host=host,
        port=port,
    )

    # Start persistent CLI subprocess
    try:
        await coordinator.async_start()
    except Exception as err:
        _LOGGER.error("Failed to start IPCom coordinator: %s", err)
        return False

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register shutdown handler
    async def _async_shutdown(_):
        """Shutdown handler for HA stop event."""
        await coordinator.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once("homeassistant_stop", _async_shutdown)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Shutdown coordinator first
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
