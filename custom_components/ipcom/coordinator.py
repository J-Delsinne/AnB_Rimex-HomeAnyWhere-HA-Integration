"""DataUpdateCoordinator for IPCom integration.

This coordinator manages a PERSISTENT subprocess running the CLI agent.
It does NOT poll on an interval - it receives real-time updates via stdout.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IPComCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage persistent CLI agent subprocess.

    Architecture:
    - Starts ONE persistent subprocess: `python ipcom_cli.py watch --json`
    - CLI handles TCP connection, authentication, polling, keep-alive
    - CLI outputs newline-delimited JSON to stdout (changes only)
    - Coordinator applies changes to maintain full device state
    - Coordinator updates HA entities immediately via async_set_updated_data()

    NO polling interval - updates are event-driven from CLI output.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        cli_path: str,
        host: str,
        port: int,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance
            cli_path: Absolute path to CLI directory (containing ipcom_cli.py)
            host: IPCom host
            port: IPCom port
        """
        # Initialize DataUpdateCoordinator WITHOUT update_interval (no polling)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # NO POLLING - event-driven updates only
        )

        self._cli_path = cli_path
        self._host = host
        self._port = port

        # Subprocess management
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._shutdown = False

        # State tracking
        self._device_state: dict[str, dict[str, Any]] = {}  # Keyed by "category.device_key"
        self._restart_count = 0
        self._max_restart_attempts = 1

    async def async_start(self) -> None:
        """Start the persistent CLI subprocess and reader task.

        This is called during integration setup (async_setup_entry).
        """
        _LOGGER.info("Starting IPCom CLI agent subprocess")
        await self._start_subprocess()

    async def _start_subprocess(self) -> None:
        """Start the CLI subprocess and reader task."""
        if self._process is not None:
            _LOGGER.warning("Subprocess already running, stopping first")
            await self._stop_subprocess()

        try:
            # Build CLI command
            cli_script = os.path.join(self._cli_path, "ipcom_cli.py")
            cmd = [
                "python",
                cli_script,
                "watch",
                "--json",
                "--host",
                self._host,
                "--port",
                str(self._port),
            ]

            _LOGGER.debug("Starting CLI subprocess: %s", " ".join(cmd))

            # Start subprocess
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cli_path,
            )

            # Fetch initial state via separate status command
            await self._fetch_initial_state()

            # Start reader task
            self._reader_task = asyncio.create_task(self._read_stdout_loop())

            _LOGGER.info("CLI subprocess started successfully (PID: %s)", self._process.pid)

        except FileNotFoundError as err:
            _LOGGER.error("CLI script not found: %s", cli_script)
            raise
        except Exception as err:
            _LOGGER.error("Failed to start CLI subprocess: %s", err)
            raise

    async def _fetch_initial_state(self) -> None:
        """Fetch initial device state using 'status --json' command.

        This runs ONCE at startup to populate initial state before watch begins.
        """
        try:
            cli_script = os.path.join(self._cli_path, "ipcom_cli.py")
            cmd = [
                "python",
                cli_script,
                "status",
                "--json",
                "--host",
                self._host,
                "--port",
                str(self._port),
            ]

            _LOGGER.debug("Fetching initial state: %s", " ".join(cmd))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cli_path,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)

            if process.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                _LOGGER.error("Initial state fetch failed: %s", error_msg)
                return

            # Parse JSON
            data = json.loads(stdout.decode())

            if "error" in data:
                _LOGGER.error("CLI returned error: %s", data["error"])
                return

            # Build initial device state
            self._device_state = {}
            for device in data.get("devices", []):
                device_key = device.get("device_key")
                category = device.get("category")

                if not device_key or not category:
                    continue

                entity_key = f"{category}.{device_key}"
                self._device_state[entity_key] = device

            _LOGGER.info("Initial state loaded: %d devices", len(self._device_state))

            # Notify coordinator that initial data is ready
            self.async_set_updated_data({
                "timestamp": data.get("timestamp"),
                "devices": self._device_state,
            })

        except asyncio.TimeoutError:
            _LOGGER.error("Initial state fetch timed out")
        except json.JSONDecodeError as err:
            _LOGGER.error("Invalid JSON from initial state: %s", err)
        except Exception as err:
            _LOGGER.error("Unexpected error fetching initial state: %s", err)

    async def _read_stdout_loop(self) -> None:
        """Read stdout from CLI subprocess line-by-line and apply changes.

        This task runs continuously until shutdown or subprocess exits.
        """
        _LOGGER.debug("Starting stdout reader loop")

        try:
            while not self._shutdown and self._process:
                # Read one line (newline-delimited JSON)
                line = await self._process.stdout.readline()

                if not line:
                    # EOF - subprocess exited
                    _LOGGER.warning("CLI subprocess exited unexpectedly")
                    await self._handle_subprocess_exit()
                    break

                # Parse JSON line
                try:
                    data = json.loads(line.decode().strip())
                except json.JSONDecodeError as err:
                    _LOGGER.warning("Invalid JSON line from CLI: %s", err)
                    continue

                # Apply changes to state
                self._apply_changes(data)

        except asyncio.CancelledError:
            _LOGGER.debug("Reader task cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Error in stdout reader loop: %s", err)
            await self._handle_subprocess_exit()

    def _apply_changes(self, data: dict[str, Any]) -> None:
        """Apply changes from watch output to device state.

        Args:
            data: JSON object from CLI watch output with structure:
                {
                    "timestamp": "ISO-8601",
                    "changes": [
                        {
                            "module": int,
                            "output": int,
                            "old": int,
                            "new": int,
                            "device_key": str (optional),
                            "display_name": str (optional),
                            "category": str (optional)
                        }
                    ]
                }
        """
        changes = data.get("changes", [])
        timestamp = data.get("timestamp")

        if not changes:
            # No changes - skip update
            return

        # Apply each change to device state
        updated = False
        for change in changes:
            device_key = change.get("device_key")
            category = change.get("category")
            new_value = change.get("new")

            if not device_key or not category:
                # Unmapped device - skip
                continue

            entity_key = f"{category}.{device_key}"

            # Update device state
            if entity_key in self._device_state:
                device = self._device_state[entity_key]
                device["value"] = new_value
                device["state"] = "on" if new_value > 0 else "off"

                # Update brightness for dimmers
                if device.get("type") == "dimmer":
                    module = device.get("module")
                    if module == 6:
                        # EXO DIM: Value is 0-100 directly
                        device["brightness"] = new_value
                    else:
                        # Regular dimmer: Convert 0-255 to 0-100
                        device["brightness"] = int((new_value / 255) * 100) if new_value > 0 else 0

                updated = True
            else:
                _LOGGER.debug("Change for unknown device: %s", entity_key)

        # Notify Home Assistant of updated data
        if updated:
            self.async_set_updated_data({
                "timestamp": timestamp,
                "devices": self._device_state,
            })

    async def _handle_subprocess_exit(self) -> None:
        """Handle unexpected subprocess exit with auto-restart logic."""
        if self._shutdown:
            # Expected shutdown - do nothing
            return

        _LOGGER.error("CLI subprocess exited unexpectedly")

        # Auto-restart once
        if self._restart_count < self._max_restart_attempts:
            self._restart_count += 1
            _LOGGER.warning("Attempting to restart CLI subprocess (attempt %d/%d)",
                          self._restart_count, self._max_restart_attempts)

            try:
                await self._start_subprocess()
                _LOGGER.info("CLI subprocess restarted successfully")
            except Exception as err:
                _LOGGER.error("Failed to restart CLI subprocess: %s", err)
                self._mark_unavailable()
        else:
            _LOGGER.error("Max restart attempts reached - marking integration unavailable")
            self._mark_unavailable()

    def _mark_unavailable(self) -> None:
        """Mark all entities as unavailable."""
        # Set last_update_success to False to mark entities unavailable
        self.last_update_success = False
        self.async_update_listeners()

    async def _stop_subprocess(self) -> None:
        """Stop the CLI subprocess gracefully."""
        _LOGGER.debug("Stopping CLI subprocess")

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Terminate subprocess
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
                _LOGGER.info("CLI subprocess stopped gracefully")
            except asyncio.TimeoutError:
                _LOGGER.warning("CLI subprocess did not stop gracefully, killing")
                self._process.kill()
                await self._process.wait()
            except Exception as err:
                _LOGGER.error("Error stopping subprocess: %s", err)

        self._process = None
        self._reader_task = None

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and stop subprocess.

        Called during integration unload or HA shutdown.
        """
        _LOGGER.info("Shutting down IPCom coordinator")
        self._shutdown = True
        await self._stop_subprocess()

    async def async_execute_command(
        self, device_key: str, command: str, value: int | None = None
    ) -> bool:
        """Execute a control command via separate CLI subprocess.

        This spawns a SHORT-LIVED CLI process to execute the command.
        The persistent watch process continues running in the background.

        Args:
            device_key: Device identifier (e.g., "keuken")
            command: Command to execute ("on", "off", "dim")
            value: Optional value for dim command (0-100)

        Returns:
            True if command succeeded, False otherwise
        """
        try:
            # Build command
            cli_script = os.path.join(self._cli_path, "ipcom_cli.py")
            cmd = [
                "python",
                cli_script,
                command,
                device_key,
            ]

            # Add value for dim command
            if command == "dim" and value is not None:
                cmd.append(str(value))

            # Add connection parameters
            cmd.extend([
                "--host",
                self._host,
                "--port",
                str(self._port),
            ])

            _LOGGER.debug("Executing command: %s", " ".join(cmd))

            # Execute subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cli_path,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )

            if process.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                _LOGGER.error(
                    "Command failed (exit %d): %s", process.returncode, error_msg
                )
                return False

            _LOGGER.debug("Command successful: %s", stdout.decode().strip())

            # State update will arrive via watch process - no need to refresh

            return True

        except asyncio.TimeoutError:
            _LOGGER.error("Command timed out after 10s")
            return False
        except Exception as err:
            _LOGGER.error("Error executing command: %s", err)
            return False
