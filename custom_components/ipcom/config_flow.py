"""Config flow for IPCom Home Anywhere Blue integration.

This config flow allows users to set up the integration entirely via the UI,
without editing configuration.yaml.

Flow Steps:
    1. User provides CLI path, host, port
    2. Validation: Check CLI exists and can connect
    3. Create config entry with validated data

IMPORTANT: This config flow does NOT implement protocol logic.
It ONLY validates that the CLI works by calling it via subprocess.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_CLI_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Step ID for user input
STEP_USER = "user"


def validate_cli_path(cli_path: str) -> str:
    """Validate that CLI path exists and is accessible.

    Args:
        cli_path: Path to ipcom_cli.py directory (absolute or relative to /config)

    Returns:
        Absolute path to CLI directory if valid

    Raises:
        ValueError: If CLI path doesn't exist or isn't accessible
    """
    # Convert to absolute path if relative
    if not os.path.isabs(cli_path):
        # Relative paths are assumed to be relative to /config directory
        config_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # Go up to /config
        cli_path = os.path.join(config_dir, cli_path)
        _LOGGER.debug("Converted relative path to: %s", cli_path)

    # Normalize path
    cli_path = os.path.normpath(cli_path)

    # Check if directory exists
    if not os.path.exists(cli_path):
        raise ValueError(f"CLI directory not found at: {cli_path}")

    # Check if ipcom_cli.py exists in directory
    cli_script = os.path.join(cli_path, "ipcom_cli.py")
    if not os.path.exists(cli_script):
        raise ValueError(f"ipcom_cli.py not found in directory: {cli_path}")

    # Check if file is readable
    if not os.access(cli_script, os.R_OK):
        raise ValueError(f"CLI script is not readable: {cli_script}")

    return cli_path


async def validate_cli_connection(
    hass: HomeAssistant, cli_path: str, host: str, port: int
) -> dict[str, Any]:
    """Validate that CLI can connect to IPCom and return valid JSON.

    This is the ONLY validation that involves the IPCom system.
    We do NOT implement protocol logic - we just verify the CLI works.

    Args:
        hass: Home Assistant instance
        cli_path: Absolute path to CLI directory
        host: IPCom host
        port: IPCom port

    Returns:
        dict with:
            - "device_count": Number of devices found
            - "timestamp": Timestamp from CLI response

    Raises:
        ValueError: If CLI fails, returns invalid JSON, or contract is wrong
    """
    cli_script = os.path.join(cli_path, "ipcom_cli.py")
    cmd = [
        "python",
        cli_script,
        "status",
        "--json",
        "--host",
        host,
        "--port",
        str(port),
    ]

    _LOGGER.debug("Validating CLI connection: %s", " ".join(cmd))
    _LOGGER.debug("CLI working directory: %s", cli_path)

    def _run_cli():
        """Run CLI command synchronously (blocking)."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            cwd=cli_path,  # Set working directory to CLI location
        )

    try:
        # Run CLI in executor to avoid blocking event loop
        result = await hass.async_add_executor_job(_run_cli)

        # Log stdout/stderr for debugging
        _LOGGER.debug("CLI stdout length: %d bytes", len(result.stdout))
        _LOGGER.debug("CLI stderr length: %d bytes", len(result.stderr))
        if result.stderr:
            _LOGGER.warning("CLI stderr output: %s", result.stderr[:500])
        if not result.stdout:
            _LOGGER.error("CLI returned empty stdout. stderr: %s", result.stderr[:500] if result.stderr else "(empty)")
            raise ValueError(f"CLI returned no output. stderr: {result.stderr[:200] if result.stderr else '(none)'}")

        # Parse JSON response
        data = json.loads(result.stdout)

        # Validate contract structure
        if "timestamp" not in data:
            raise ValueError("CLI response missing 'timestamp' field")
        if "devices" not in data:
            raise ValueError("CLI response missing 'devices' field")
        if not isinstance(data["devices"], list):
            raise ValueError("CLI response 'devices' is not a list")

        device_count = len(data["devices"])
        timestamp = data["timestamp"]

        _LOGGER.info(
            "CLI validation successful: %d devices found at %s",
            device_count,
            timestamp,
        )

        return {
            "device_count": device_count,
            "timestamp": timestamp,
        }

    except subprocess.CalledProcessError as err:
        _LOGGER.error("CLI command failed: %s", err.stderr)
        raise ValueError(f"CLI command failed: {err.stderr}") from err
    except subprocess.TimeoutExpired as err:
        _LOGGER.error("CLI command timed out after 30 seconds")
        raise ValueError("CLI command timed out - check host/port") from err
    except json.JSONDecodeError as err:
        _LOGGER.error("CLI returned invalid JSON: %s", err)
        raise ValueError(f"CLI returned invalid JSON: {err}") from err
    except Exception as err:
        _LOGGER.error("Unexpected error validating CLI: %s", err)
        raise ValueError(f"Unexpected error: {err}") from err


class IPComConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPCom integration.

    This config flow:
    - Presents a form to the user for CLI path, host, port
    - Validates the CLI path exists
    - Validates the CLI can connect to IPCom
    - Creates a config entry with the validated data
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (user input).

        This is the main entry point for manual config flow.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # User submitted the form, validate input
            try:
                # Validate CLI path
                cli_path = validate_cli_path(user_input[CONF_CLI_PATH])

                # Validate CLI connection
                validation_result = await validate_cli_connection(
                    self.hass,
                    cli_path,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                )

                # Check for existing entries with same host
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()

                # All validation passed, create entry
                title = f"IPCom ({user_input[CONF_HOST]}:{user_input[CONF_PORT]})"

                _LOGGER.info(
                    "Creating IPCom config entry: %d devices found",
                    validation_result["device_count"],
                )

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_CLI_PATH: cli_path,  # Store absolute path
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                    },
                )

            except ValueError as err:
                _LOGGER.error("Validation error: %s", err)
                # Set generic error key, will be translated
                if "not found" in str(err).lower():
                    errors["base"] = "cli_not_found"
                elif "not readable" in str(err).lower():
                    errors["base"] = "cli_not_readable"
                elif "timed out" in str(err).lower():
                    errors["base"] = "connection_timeout"
                elif "invalid json" in str(err).lower():
                    errors["base"] = "invalid_json"
                elif "failed" in str(err).lower():
                    errors["base"] = "cli_failed"
                else:
                    errors["base"] = "unknown"

            except Exception as err:
                _LOGGER.exception("Unexpected error in config flow")
                errors["base"] = "unknown"

        # Show form (initial or after error)
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_CLI_PATH,
                    description={"suggested_value": "ipcom"},
                ): cv.string,
                vol.Required(
                    CONF_HOST,
                    default=DEFAULT_HOST,
                ): cv.string,
                vol.Required(
                    CONF_PORT,
                    default=DEFAULT_PORT,
                ): cv.port,
            }
        )

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Handle import from YAML configuration.

        This method is called automatically when YAML configuration exists.
        It migrates the YAML config to a config entry.

        Args:
            import_data: Data from YAML configuration

        Returns:
            FlowResult (create entry or abort)
        """
        _LOGGER.info("Importing IPCom configuration from YAML")

        # Check for existing entries with same host
        await self.async_set_unique_id(f"{import_data[CONF_HOST]}:{import_data[CONF_PORT]}")
        self._abort_if_unique_id_configured()

        # Validate CLI path
        try:
            cli_path = validate_cli_path(import_data[CONF_CLI_PATH])
        except ValueError as err:
            _LOGGER.error("YAML import failed: %s", err)
            return self.async_abort(reason="cli_not_found")

        # Validate CLI connection (optional, but recommended)
        try:
            validation_result = await validate_cli_connection(
                self.hass,
                cli_path,
                import_data[CONF_HOST],
                import_data[CONF_PORT],
            )
            _LOGGER.info(
                "YAML import validation successful: %d devices found",
                validation_result["device_count"],
            )
        except ValueError as err:
            _LOGGER.warning(
                "YAML import: CLI validation failed, but continuing anyway: %s", err
            )
            # Don't abort - allow migration even if CLI is temporarily unavailable

        # Create config entry from YAML data
        title = f"IPCom ({import_data[CONF_HOST]}:{import_data[CONF_PORT]})"

        return self.async_create_entry(
            title=title,
            data={
                CONF_CLI_PATH: cli_path,
                CONF_HOST: import_data[CONF_HOST],
                CONF_PORT: import_data[CONF_PORT],
            },
        )
