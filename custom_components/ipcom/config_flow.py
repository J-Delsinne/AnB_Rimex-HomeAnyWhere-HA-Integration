"""Config flow for IPCom Home Anywhere Blue integration.

This config flow allows users to set up the integration entirely via the UI,
without editing configuration.yaml.

Flow Steps:
    1. User provides host, port, username, password
    2. Validation: Check bundled CLI can connect to IPCom
    3. Create config entry with validated data

The CLI is bundled with the integration at custom_components/ipcom/cli/.
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
    CONF_USERNAME,
    CONF_PASSWORD,
    DEFAULT_PORT,
    DOMAIN,
    get_cli_path,
    get_python_executable,
)

_LOGGER = logging.getLogger(__name__)

# Step ID for user input
STEP_USER = "user"


async def validate_cli_connection(
    hass: HomeAssistant, host: str, port: int,
    username: str, password: str
) -> dict[str, Any]:
    """Validate that CLI can connect to IPCom and return valid JSON.

    This is the ONLY validation that involves the IPCom system.
    We do NOT implement protocol logic - we just verify the CLI works.

    Args:
        hass: Home Assistant instance
        host: IPCom host
        port: IPCom port
        username: IPCom username
        password: IPCom password

    Returns:
        dict with:
            - "device_count": Number of devices found
            - "timestamp": Timestamp from CLI response

    Raises:
        ValueError: If CLI fails, returns invalid JSON, or contract is wrong
    """
    # Use the bundled CLI path
    cli_path = get_cli_path()
    cli_script = os.path.join(cli_path, "ipcom_cli.py")
    python_exe = get_python_executable()

    cmd = [
        python_exe,
        cli_script,
        "status",
        "--json",
        "--host",
        host,
        "--port",
        str(port),
        "--username",
        username,
        "--password",
        password,
    ]

    _LOGGER.debug("Validating CLI connection using Python: %s", python_exe)
    _LOGGER.debug("CLI command: %s ... (credentials hidden)", " ".join(cmd[:6]))
    _LOGGER.debug("CLI working directory: %s", cli_path)
    _LOGGER.debug("CLI script path: %s", cli_script)
    _LOGGER.debug("CLI script exists: %s", os.path.exists(cli_script))

    def _run_cli():
        """Run CLI command synchronously (blocking)."""
        # Use check=False to capture output even on failure
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # Don't raise exception, we'll check returncode manually
            timeout=30,
            cwd=cli_path,  # Set working directory to CLI location
        )

    try:
        # Run CLI in executor to avoid blocking event loop
        result = await hass.async_add_executor_job(_run_cli)

        # Log stdout/stderr for debugging (always log for troubleshooting)
        _LOGGER.debug("CLI exit code: %d", result.returncode)
        _LOGGER.debug("CLI stdout length: %d bytes", len(result.stdout) if result.stdout else 0)
        _LOGGER.debug("CLI stderr length: %d bytes", len(result.stderr) if result.stderr else 0)

        # Check for failure BEFORE parsing JSON
        if result.returncode != 0:
            # CLI failed - get error message from stdout (CLI prints errors there)
            error_output = result.stdout or result.stderr or "(no output)"
            _LOGGER.error(
                "CLI command failed | exit_code: %d | output: %s",
                result.returncode,
                error_output[:500]
            )
            # Extract meaningful error message for user
            if "Authentication failed" in error_output or "❌ Authentication failed" in error_output:
                raise ValueError("Authentication failed - check username and password")
            elif "Connection failed" in error_output or "❌ Connection failed" in error_output:
                raise ValueError("Connection failed - check host and port")
            elif "timed out" in error_output.lower():
                raise ValueError("Connection timed out - check host and port")
            else:
                # Use first line of output as error message
                first_line = error_output.strip().split('\n')[0][:200]
                raise ValueError(f"CLI failed: {first_line}")

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

    except FileNotFoundError as err:
        _LOGGER.error(
            "Python executable or CLI script not found: %s | python_exe: %s | cli_script: %s",
            err, python_exe, cli_script
        )
        raise ValueError(f"Python or CLI script not found: {err}") from err
    except subprocess.TimeoutExpired as err:
        _LOGGER.error("CLI command timed out after 30 seconds")
        raise ValueError("CLI command timed out - check host/port") from err
    except json.JSONDecodeError as err:
        _LOGGER.error("CLI returned invalid JSON: %s", err)
        raise ValueError(f"CLI returned invalid JSON: {err}") from err
    except Exception as err:
        _LOGGER.error("Unexpected error validating CLI: %s", err, exc_info=True)
        raise ValueError(f"Unexpected error: {err}") from err


class IPComConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPCom integration.

    This config flow:
    - Presents a form for host, port, username, password
    - Validates the bundled CLI can connect to IPCom
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
                # Validate CLI connection using bundled CLI
                validation_result = await validate_cli_connection(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
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
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

            except ValueError as err:
                _LOGGER.error("Validation error: %s", err)
                error_str = str(err).lower()
                # Set generic error key, will be translated
                if "timed out" in error_str:
                    errors["base"] = "connection_timeout"
                elif "invalid json" in error_str:
                    errors["base"] = "invalid_json"
                elif "auth" in error_str or "credential" in error_str or "password" in error_str or "username" in error_str:
                    errors["base"] = "auth_failed"
                elif "connection" in error_str and "failed" in error_str:
                    errors["base"] = "connection_failed"
                elif "failed" in error_str:
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
                    CONF_HOST,
                    description={"suggested_value": "your-ipcom-host.example.com"},
                ): cv.string,
                vol.Required(
                    CONF_PORT,
                    default=DEFAULT_PORT,
                ): cv.port,
                vol.Required(
                    CONF_USERNAME,
                ): cv.string,
                vol.Required(
                    CONF_PASSWORD,
                ): cv.string,
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

        # Validate CLI connection (optional, but recommended)
        try:
            validation_result = await validate_cli_connection(
                self.hass,
                import_data[CONF_HOST],
                import_data[CONF_PORT],
                import_data.get(CONF_USERNAME, ""),
                import_data.get(CONF_PASSWORD, ""),
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
                CONF_HOST: import_data[CONF_HOST],
                CONF_PORT: import_data[CONF_PORT],
                CONF_USERNAME: import_data.get(CONF_USERNAME, ""),
                CONF_PASSWORD: import_data.get(CONF_PASSWORD, ""),
            },
        )
