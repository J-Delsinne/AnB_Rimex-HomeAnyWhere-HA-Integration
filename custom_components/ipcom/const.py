"""Constants for the IPCom integration."""
import os
import shutil
import sys

DOMAIN = "ipcom"

# Configuration keys (CONF_CLI_PATH kept for backwards compatibility with existing configs)
CONF_CLI_PATH = "cli_path"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Cloud discovery configuration keys
CONF_CLOUD_USERNAME = "cloud_username"
CONF_CLOUD_PASSWORD = "cloud_password"
CONF_SITE_ID = "site_id"
CONF_SITE_NAME = "site_name"
CONF_DEVICES = "devices"  # Stores discovered devices in config entry

# Connection type configuration
CONF_CONNECTION_TYPE = "connection_type"
CONF_LOCAL_HOST = "local_host"
CONF_LOCAL_PORT = "local_port"
CONF_REMOTE_HOST = "remote_host"
CONF_REMOTE_PORT = "remote_port"

# Connection type values
CONNECTION_TYPE_LOCAL = "local"
CONNECTION_TYPE_REMOTE = "remote"
CONNECTION_TYPE_BOTH = "both"  # Local preferred with remote fallback

# Defaults
DEFAULT_HOST = ""  # No default - user must provide their host
DEFAULT_PORT = 5000

# Entity platforms
PLATFORMS = ["light", "cover", "switch"]

# ============================================================================
# GraphicType to Home Assistant Platform Mapping
# ============================================================================
# These GraphicTypes are extracted from the Home Anywhere Blue application
# (Home_Anywhere_D.dll) and define how devices appear in the app.
# We use this to map devices to the correct Home Assistant platform.
# ============================================================================

GRAPHIC_TYPE_MAPPING = {
    # Lights - map to light platform
    "OutputLightBulb": {
        "platform": "light",
        "device_class": None,
        "icon": None,
    },
    "OutputLightBulbEconomic": {
        "platform": "light",
        "device_class": None,
        "icon": "mdi:lightbulb-fluorescent-tube",
    },
    "OutputButtonLedYellow": {
        "platform": "light",
        "device_class": None,
        "icon": "mdi:led-on",
    },
    
    # Switches - Outlets/Sockets
    "OutputSocket": {
        "platform": "switch",
        "device_class": "outlet",
        "icon": None,
    },
    
    # Switches - Appliances
    "OutputTelevision": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:television",
    },
    "OutputWashMachine": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:washing-machine",
    },
    "OutputDishWasher": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:dishwasher",
    },
    "OutputCoffeeMachine": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:coffee-maker",
    },
    "OutputMicrowaveOven": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:microwave",
    },
    "OutputOven": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:stove",
    },
    
    # Switches - HVAC
    "OutputHeater": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:radiator",
    },
    "OutputElectricHeater": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:radiator",
    },
    "OutputBoiler": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:water-boiler",
    },
    "OutputAirConditionner": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:air-conditioner",
    },
    
    # Doors (as switches for now)
    "OutputDoorOpen": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:door-open",
    },
    "OutputDoorClose": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:door-closed",
    },
    "OutputLock": {
        "platform": "switch",
        "device_class": None,
        "icon": "mdi:lock",
    },
    
    # Covers - Shutters (detected via ExoStore module, but GraphicType confirms)
    "OutputShutterUp": {
        "platform": "cover",
        "device_class": "shutter",
        "icon": None,
        "relay_role": "up",
    },
    "OutputShutterDown": {
        "platform": "cover",
        "device_class": "shutter",
        "icon": None,
        "relay_role": "down",
    },
    
    # Covers - Blinds
    "OutputBlindUp": {
        "platform": "cover",
        "device_class": "blind",
        "icon": None,
        "relay_role": "up",
    },
    "OutputBlindDown": {
        "platform": "cover",
        "device_class": "blind",
        "icon": None,
        "relay_role": "down",
    },
}

# Default mapping for unknown GraphicTypes - treat as light
DEFAULT_GRAPHIC_TYPE_MAPPING = {
    "platform": "light",
    "device_class": None,
    "icon": None,
}


def get_cli_path() -> str:
    """Get the path to the bundled CLI directory.

    The CLI is now bundled inside the integration at custom_components/ipcom/cli/.
    This function returns the absolute path to that directory.

    Returns:
        Absolute path to the CLI directory containing ipcom_cli.py
    """
    # __file__ is custom_components/ipcom/const.py
    # CLI is at custom_components/ipcom/cli/
    integration_dir = os.path.dirname(os.path.abspath(__file__))
    cli_path = os.path.join(integration_dir, "cli")
    return cli_path


def get_devices_yaml_path(hass_config_dir: str) -> str:
    """Get the path where devices.yaml should be located.

    The devices.yaml file should be in the Home Assistant config directory
    at /config/ipcom/devices.yaml (or the cli directory as fallback).

    Args:
        hass_config_dir: Home Assistant configuration directory path

    Returns:
        Absolute path to devices.yaml
    """
    # Primary location: /config/ipcom/devices.yaml
    primary_path = os.path.join(hass_config_dir, "ipcom", "devices.yaml")
    if os.path.exists(primary_path):
        return primary_path

    # Fallback: check in the bundled CLI directory
    cli_path = get_cli_path()
    fallback_path = os.path.join(cli_path, "devices.yaml")
    if os.path.exists(fallback_path):
        return fallback_path

    # Return primary path (will be created by user)
    return primary_path


def get_python_executable() -> str:
    """Get the correct Python executable for the current platform.

    Home Assistant containers typically use 'python3', while Windows
    often uses 'python'. This function finds the correct executable.

    Returns:
        Path to Python executable (e.g., 'python3', 'python', or full path)
    """
    # First, try to use the same Python that's running Home Assistant
    # This is the most reliable approach
    current_python = sys.executable
    if current_python:
        return current_python

    # Fallback: Check for python3 first (Linux/macOS), then python
    python3_path = shutil.which("python3")
    if python3_path:
        return python3_path

    python_path = shutil.which("python")
    if python_path:
        return python_path

    # Last resort fallback
    return "python3"
