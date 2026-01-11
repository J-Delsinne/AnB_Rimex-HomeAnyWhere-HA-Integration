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

# Defaults
DEFAULT_HOST = ""  # No default - user must provide their host
DEFAULT_PORT = 5000

# Entity platforms
PLATFORMS = ["light", "cover"]


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
