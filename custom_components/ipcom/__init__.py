"""The IPCom Home Anywhere Blue integration.

This integration provides a bridge between Home Assistant and the IPCom system
using the persistent TCP connection with background loops.

Architecture:
    IPComCoordinator → IPComClient (persistent) → TCP Socket → IPCom Device

Configuration:
    Configured via UI (Settings → Devices & Services → Add Integration)
"""
from __future__ import annotations

import logging

# Initialize logger FIRST before any other code
_LOGGER = logging.getLogger(__name__)
_LOGGER.info("IPCom __init__.py is being loaded")
import os
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import IPComCoordinator

# Configuration schema for YAML setup
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("cli_path"): cv.string,
                vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IPCom integration from YAML configuration.

    This method now triggers YAML import to migrate to config entries.
    YAML configuration is DEPRECATED - use the UI config flow instead.

    Args:
        hass: Home Assistant instance
        config: Configuration dict from configuration.yaml

    Returns:
        True (actual setup happens in async_setup_entry)
    """
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]

    _LOGGER.warning(
        "IPCom YAML configuration is deprecated and will be removed in a future version. "
        "Please remove the 'ipcom:' section from configuration.yaml. "
        "Your configuration will be automatically imported to the UI."
    )

    # Convert to absolute path if relative
    cli_path = conf["cli_path"]
    if not os.path.isabs(cli_path):
        cli_path = os.path.join(hass.config.config_dir, cli_path)

    # Trigger import flow to create config entry
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                "cli_path": cli_path,
                CONF_HOST: conf[CONF_HOST],
                CONF_PORT: conf[CONF_PORT],
                CONF_SCAN_INTERVAL: conf[CONF_SCAN_INTERVAL],
            },
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPCom from a config entry.

    This is now the PRIMARY setup method (called after config flow).
    YAML configuration triggers import which creates a config entry.

    Args:
        hass: Home Assistant instance
        entry: ConfigEntry created by config flow or YAML import

    Returns:
        True if setup succeeded, False otherwise
    """
    _LOGGER.critical("=" * 80)
    _LOGGER.critical("async_setup_entry CALLED - Integration is starting!")
    _LOGGER.critical("Entry ID: %s", entry.entry_id)
    _LOGGER.critical("Entry Data: %s", entry.data)
    _LOGGER.critical("=" * 80)

    # Get configuration from entry
    try:
        cli_path = entry.data["cli_path"]
        host = entry.data.get(CONF_HOST, DEFAULT_HOST)
        port = entry.data.get(CONF_PORT, DEFAULT_PORT)
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    except KeyError as e:
        _LOGGER.error("Missing required config key: %s", e)
        _LOGGER.error("Entry data: %s", entry.data)
        return False

    _LOGGER.critical("STEP 1: Configuration extracted successfully")
    _LOGGER.info(
        "Setting up IPCom integration: %s:%d (scan_interval=%ds, cli=%s)",
        host,
        port,
        scan_interval,
        cli_path,
    )

    # Validate CLI path exists
    _LOGGER.critical("STEP 2: Checking if CLI path exists: %s", cli_path)
    if not os.path.exists(cli_path):
        _LOGGER.error("CLI script not found at: %s", cli_path)
        return False
    _LOGGER.critical("STEP 2: CLI path exists!")

    # Create coordinator
    _LOGGER.critical("STEP 3: Creating IPComCoordinator...")
    try:
        coordinator = IPComCoordinator(
            hass=hass,
            cli_path=cli_path,
            host=host,
            port=port,
            scan_interval=scan_interval,
        )
        _LOGGER.critical("STEP 3: Coordinator created successfully")
    except Exception as e:
        _LOGGER.error("STEP 3 FAILED: Error creating coordinator: %s", e, exc_info=True)
        return False

    # Start persistent connection
    _LOGGER.critical("STEP 4: Starting persistent connection...")
    try:
        success = await coordinator.async_start()
        _LOGGER.critical("STEP 4: async_start returned: %s", success)
        if not success:
            _LOGGER.error("Failed to start persistent connection")
            return False
    except Exception as err:
        _LOGGER.error("Failed to start persistent connection: %s", err, exc_info=True)
        return False

    # Wait briefly for initial data
    _LOGGER.critical("STEP 5: Waiting for initial data refresh...")
    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.critical("STEP 5: First refresh completed")
    except Exception as err:
        _LOGGER.error("Failed to fetch initial data from IPCom: %s", err, exc_info=True)
        await coordinator.async_stop()
        return False

    # Store coordinator
    _LOGGER.critical("STEP 6: Storing coordinator in hass.data...")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "cli_path": cli_path,
        "host": host,
        "port": port,
    }
    _LOGGER.critical("STEP 6: Coordinator stored")

    # Forward setup to platforms
    _LOGGER.critical("STEP 7: Forwarding setup to platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.critical("STEP 7: Platform setup forwarded")

    _LOGGER.critical("STEP 8: Integration setup complete!")
    _LOGGER.info(
        "IPCom integration loaded: %d devices found",
        len(coordinator.data.get("devices", {})) if coordinator.data else 0,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Stops the persistent connection and cleans up resources.
    """
    # Get coordinator
    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    if entry_data:
        coordinator = entry_data.get("coordinator")
        if coordinator:
            # Stop persistent connection
            await coordinator.async_stop()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
