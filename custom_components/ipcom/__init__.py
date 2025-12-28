"""The IPCom Home Anywhere Blue integration.

This integration provides a bridge between Home Assistant and the IPCom system
using the CLI JSON interface as the ONLY communication method.

Architecture:
    CLI (ipcom_cli.py) → JSON Contract → Home Assistant

    This integration does NOT:
    - Parse TCP packets
    - Handle encryption
    - Manage sockets
    - Implement protocol logic

    It ONLY:
    - Calls CLI commands via subprocess
    - Parses JSON responses
    - Manages Home Assistant entities

Configuration:
    Since there is no config_flow yet, this integration must be configured
    via YAML in configuration.yaml:

    ipcom:
      cli_path: "/path/to/ipcom_cli.py"
      host: "megane-david.dyndns.info"
      port: 5000
      scan_interval: 10
"""
from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)

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
    # Get configuration from entry
    cli_path = entry.data["cli_path"]
    host = entry.data.get(CONF_HOST, DEFAULT_HOST)
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    _LOGGER.info(
        "Setting up IPCom integration: %s:%d (scan_interval=%ds, cli=%s)",
        host,
        port,
        scan_interval,
        cli_path,
    )

    # Validate CLI path exists
    if not os.path.exists(cli_path):
        _LOGGER.error("CLI script not found at: %s", cli_path)
        return False

    # Create coordinator
    coordinator = IPComCoordinator(
        hass=hass,
        cli_path=cli_path,
        host=host,
        port=port,
        scan_interval=scan_interval,
    )

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed to fetch initial data from IPCom: %s", err)
        return False

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "cli_path": cli_path,
        "host": host,
        "port": port,
    }

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(
        "IPCom integration loaded: %d devices found",
        len(coordinator.data.get("devices", {})) if coordinator.data else 0,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    This will be used when config_flow is implemented.
    """
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
