"""DataUpdateCoordinator for IPCom integration."""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CLI_PYTHON, CLI_SCRIPT, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class IPComCoordinator(DataUpdateCoordinator):
    """Class to manage fetching IPCom data from CLI JSON interface.

    This coordinator is the ONLY interface to the IPCom system.
    It consumes the stable CLI JSON contract (v1.0) and provides data to entities.

    The coordinator does NOT:
    - Parse TCP packets
    - Handle encryption
    - Manage sockets
    - Implement protocol logic

    It ONLY:
    - Calls `ipcom_cli.py status --json`
    - Parses the JSON response
    - Provides structured data to entities
    """

    def __init__(
        self,
        hass: HomeAssistant,
        cli_path: str,
        host: str,
        port: int,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            cli_path: Path to ipcom_cli.py script
            host: IPCom server host
            port: IPCom server port
            scan_interval: Update interval in seconds
        """
        self.cli_path = cli_path
        self.host = host
        self.port = port

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from IPCom via CLI JSON interface.

        Returns:
            Dictionary with structure:
            {
                "timestamp": "ISO-8601 datetime",
                "devices": {
                    "<category>.<device_key>": {
                        "device_key": str,
                        "display_name": str,
                        "category": str,
                        "type": "dimmer" | "switch",
                        "module": int,
                        "output": int,
                        "value": int (0-255),
                        "state": "on" | "off",
                        "brightness": int (0-100, only for dimmers)
                    }
                }
            }

        Raises:
            UpdateFailed: If CLI command fails or returns invalid JSON
        """
        try:
            # Build CLI command
            cmd = [
                CLI_PYTHON,
                self.cli_path,
                "status",
                "--json",
                "--host",
                self.host,
                "--port",
                str(self.port),
            ]

            _LOGGER.debug("Running CLI command: %s", " ".join(cmd))

            # Run CLI command (blocking - run in executor)
            result = await self.hass.async_add_executor_job(
                self._run_cli_command, cmd
            )

            # Parse JSON response
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as err:
                _LOGGER.error("Invalid JSON from CLI: %s", result.stdout[:200])
                raise UpdateFailed(f"Invalid JSON from CLI: {err}") from err

            # Check for error response
            if "error" in data:
                error_msg = data.get("error", "Unknown error")
                _LOGGER.error("CLI returned error: %s", error_msg)
                raise UpdateFailed(f"CLI error: {error_msg}")

            # Validate response structure
            if "devices" not in data or "timestamp" not in data:
                _LOGGER.error("Invalid CLI response structure: %s", list(data.keys()))
                raise UpdateFailed("Invalid CLI response: missing required fields")

            # Transform device list into dict keyed by "<category>.<device_key>"
            devices = {}
            for device in data["devices"]:
                device_key = device.get("device_key")
                category = device.get("category")

                if not device_key or not category:
                    _LOGGER.warning("Device missing key or category: %s", device)
                    continue

                entity_key = f"{category}.{device_key}"
                devices[entity_key] = device

            _LOGGER.debug(
                "Coordinator update successful: %d devices at %s",
                len(devices),
                data.get("timestamp"),
            )

            return {
                "timestamp": data["timestamp"],
                "devices": devices,
            }

        except subprocess.CalledProcessError as err:
            _LOGGER.error(
                "CLI command failed (exit %d): %s",
                err.returncode,
                err.stderr[:200] if err.stderr else "no stderr",
            )
            raise UpdateFailed(f"CLI command failed: {err}") from err

        except Exception as err:
            _LOGGER.error("Unexpected error updating IPCom data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err

    def _run_cli_command(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run CLI command synchronously (called via executor).

        Args:
            cmd: Command list to execute

        Returns:
            Completed process with stdout/stderr

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        import os

        # Get CLI directory to set as working directory
        cli_dir = os.path.dirname(self.cli_path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,  # 30 second timeout
            cwd=cli_dir,  # Set working directory to CLI location
        )
        return result

    async def async_execute_command(
        self, device_key: str, command: str, value: int | None = None
    ) -> bool:
        """Execute a control command via CLI.

        Args:
            device_key: Device identifier (e.g., "keuken")
            command: Command to execute ("on", "off", "toggle", "dim")
            value: Optional value for dim command (0-100)

        Returns:
            True if command succeeded, False otherwise
        """
        try:
            # Build command
            cmd = [
                CLI_PYTHON,
                self.cli_path,
                command,
                device_key,
            ]

            # Add value for dim command (must come after device_key)
            if command == "dim" and value is not None:
                cmd.append(str(value))  # Append after device_key

            # Add connection parameters
            cmd.extend([
                "--host",
                self.host,
                "--port",
                str(self.port),
            ])

            _LOGGER.debug("Executing command: %s", " ".join(cmd))

            # Run command
            result = await self.hass.async_add_executor_job(
                self._run_cli_command, cmd
            )

            _LOGGER.debug("Command successful: %s", result.stdout.strip())

            # Request immediate coordinator update to sync state
            await self.async_request_refresh()

            return True

        except subprocess.CalledProcessError as err:
            _LOGGER.error(
                "Command failed (exit %d): %s",
                err.returncode,
                err.stderr[:200] if err.stderr else "no stderr",
            )
            return False

        except Exception as err:
            _LOGGER.error("Unexpected error executing command: %s", err)
            return False
