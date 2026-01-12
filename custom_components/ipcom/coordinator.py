"""DataUpdateCoordinator for IPCom integration.

This coordinator manages a PERSISTENT subprocess running the CLI agent.
It does NOT poll on an interval - it receives real-time updates via stdout.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, get_cli_path, get_devices_yaml_path, get_python_executable

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
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """Initialize coordinator.

        Args:
            hass: Home Assistant instance
            host: IPCom host
            port: IPCom port
            username: IPCom authentication username
            password: IPCom authentication password
        """
        # Initialize DataUpdateCoordinator WITHOUT update_interval (no polling)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # NO POLLING - event-driven updates only
        )

        # Use the bundled CLI path and devices.yaml from HA config dir
        self._cli_path = get_cli_path()
        self._devices_file = get_devices_yaml_path(hass.config.path())
        self._host = host
        self._port = port
        self._username = username
        self._password = password

        # Subprocess management
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._shutdown = False

        # State tracking
        self._device_state: dict[str, dict[str, Any]] = {}  # Keyed by "category.device_key"
        self._restart_count = 0
        self._max_restart_attempts = 5  # Allow multiple restart attempts
        self._restart_delay = 5.0  # Base delay between restarts (seconds)
        self._max_restart_delay = 300.0  # Max delay (5 minutes)
        self._consecutive_failures = 0

        # Connection health monitoring
        self._last_data_received: float = 0.0
        self._health_check_task: asyncio.Task | None = None
        self._health_check_interval = 60.0  # Check every 60 seconds
        self._connection_timeout = 120.0  # Consider dead after 2 minutes of no data

        # Connection statistics for diagnostics
        self._stats = {
            "start_time": None,
            "total_restarts": 0,
            "total_data_lines": 0,
            "last_restart_reason": None,
            "last_restart_time": None,
            "longest_uptime": 0.0,
            "current_session_start": None,
        }

        # Command throttling to prevent overwhelming the IPCom server
        self._command_lock = asyncio.Lock()
        self._command_delay = 0.5  # 500ms delay between commands
        self._last_command_time: float = 0.0

    async def async_start(self) -> None:
        """Start the persistent CLI subprocess and reader task.

        This is called during integration setup (async_setup_entry).
        """
        self._stats["start_time"] = time.time()
        _LOGGER.info(
            "Starting IPCom coordinator - connecting to %s:%s",
            self._host, self._port
        )
        await self._start_subprocess()

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def _start_subprocess(self) -> None:
        """Start the CLI subprocess and reader task."""
        if self._process is not None:
            _LOGGER.warning("Subprocess already running, stopping first")
            await self._stop_subprocess()

        try:
            # Build CLI command
            cli_script = os.path.join(self._cli_path, "ipcom_cli.py")
            python_exe = get_python_executable()
            cmd = [
                python_exe,
                cli_script,
                "watch",
                "--json",
                "--host",
                self._host,
                "--port",
                str(self._port),
                "--username",
                self._username,
                "--password",
                self._password,
                "--devices-file",
                self._devices_file,
            ]

            _LOGGER.debug("Starting CLI subprocess with Python: %s", python_exe)
            _LOGGER.debug("CLI command: %s ... (credentials hidden)", " ".join(cmd[:5]))

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

            _LOGGER.info(
                "CLI_START | PID: %s | host: %s:%s | cli_path: %s | "
                "health_check: %ds | timeout: %ds",
                self._process.pid,
                self._host, self._port,
                self._cli_path,
                int(self._health_check_interval),
                int(self._connection_timeout)
            )

            # Reset failure counter on successful start
            self._consecutive_failures = 0
            self._last_data_received = time.time()
            self._stats["current_session_start"] = time.time()

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
            python_exe = get_python_executable()
            cmd = [
                python_exe,
                cli_script,
                "status",
                "--json",
                "--host",
                self._host,
                "--port",
                str(self._port),
                "--username",
                self._username,
                "--password",
                self._password,
                "--devices-file",
                self._devices_file,
            ]

            _LOGGER.debug("Fetching initial state: %s ... (credentials hidden)", " ".join(cmd[:5]))

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
                    _LOGGER.warning(
                        "CLI_EOF | subprocess stdout closed | "
                        "data lines received: %d | session uptime: %.1f min | "
                        "host: %s:%s",
                        self._stats["total_data_lines"],
                        (time.time() - self._stats["current_session_start"]) / 60 if self._stats["current_session_start"] else 0,
                        self._host, self._port
                    )
                    await self._handle_subprocess_exit("subprocess stdout EOF")
                    break

                # Track data reception for health monitoring
                self._last_data_received = time.time()
                self._stats["total_data_lines"] += 1

                # Parse JSON line
                line_str = line.decode().strip()
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError as err:
                    _LOGGER.warning(
                        "Invalid JSON line from CLI (line #%d): %s - content: %s",
                        self._stats["total_data_lines"], err, line_str[:200]
                    )
                    continue

                # Apply changes to state
                self._apply_changes(data)

        except asyncio.CancelledError:
            _LOGGER.debug("Reader task cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Error in stdout reader loop: %s", err, exc_info=True)
            await self._handle_subprocess_exit(f"reader loop exception: {err}")

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

    async def _handle_subprocess_exit(self, reason: str = "unknown") -> None:
        """Handle unexpected subprocess exit with auto-restart logic.

        Uses exponential backoff with unlimited retries to ensure the
        integration eventually recovers from temporary network issues.

        Args:
            reason: Description of why the subprocess exited (for logging)
        """
        if self._shutdown:
            # Expected shutdown - do nothing
            return

        # Calculate session uptime before incrementing failure counter
        session_uptime = 0.0
        if self._stats["current_session_start"]:
            session_uptime = time.time() - self._stats["current_session_start"]
            if session_uptime > self._stats["longest_uptime"]:
                self._stats["longest_uptime"] = session_uptime

        self._consecutive_failures += 1
        self._stats["total_restarts"] += 1
        self._stats["last_restart_reason"] = reason
        self._stats["last_restart_time"] = time.time()

        # Log detailed diagnostics
        _LOGGER.error(
            "CLI_EXIT | reason: %s | "
            "failure #%d | session: %.1f min | "
            "total restarts: %d | best uptime: %.1f min | "
            "data lines: %d | host: %s:%s",
            reason,
            self._consecutive_failures,
            session_uptime / 60,
            self._stats["total_restarts"],
            self._stats["longest_uptime"] / 60,
            self._stats["total_data_lines"],
            self._host, self._port
        )

        # Calculate backoff delay with exponential increase
        delay = min(
            self._restart_delay * (2 ** (self._consecutive_failures - 1)),
            self._max_restart_delay
        )

        _LOGGER.warning(
            "CLI_RESTART_SCHEDULED | delay: %.0fs | attempt: %d | "
            "backoff formula: %.0f * 2^%d (max: %.0f) | host: %s:%s",
            delay, self._consecutive_failures,
            self._restart_delay, self._consecutive_failures - 1, self._max_restart_delay,
            self._host, self._port
        )

        # Mark as temporarily unavailable during reconnection
        self.last_update_success = False
        self.async_update_listeners()

        # Wait before retry
        await asyncio.sleep(delay)

        if self._shutdown:
            return

        _LOGGER.info("Attempting CLI subprocess restart now...")

        # Attempt restart
        try:
            await self._start_subprocess()
            _LOGGER.info(
                "CLI_RESTART_OK | attempts: %d | host: %s:%s | "
                "total restarts: %d | integration restored",
                self._consecutive_failures, self._host, self._port,
                self._stats["total_restarts"]
            )
            # Mark as available again
            self.last_update_success = True
            self.async_update_listeners()
        except Exception as err:
            _LOGGER.error(
                "CLI_RESTART_FAILED | error: %s | attempts: %d | "
                "next delay: %.0fs | host: %s:%s",
                err, self._consecutive_failures,
                min(self._restart_delay * (2 ** self._consecutive_failures), self._max_restart_delay),
                self._host, self._port
            )
            # Schedule another retry by calling this handler again
            asyncio.create_task(self._handle_subprocess_exit(f"restart failed: {err}"))

    def _mark_unavailable(self) -> None:
        """Mark all entities as unavailable."""
        # Set last_update_success to False to mark entities unavailable
        self.last_update_success = False
        self.async_update_listeners()

    async def _health_check_loop(self) -> None:
        """Periodically check connection health and restart if stale.

        This proactively detects when the connection has gone stale
        (no data received for a long time) and triggers a restart.
        """
        _LOGGER.debug("Starting connection health check loop")

        try:
            while not self._shutdown:
                await asyncio.sleep(self._health_check_interval)

                if self._shutdown:
                    break

                # Check if subprocess is still running
                if self._process is None:
                    _LOGGER.warning(
                        "Health check: subprocess object is None, triggering restart"
                    )
                    await self._handle_subprocess_exit("subprocess object is None")
                    continue

                if self._process.returncode is not None:
                    _LOGGER.warning(
                        "Health check: subprocess exited with code %d, triggering restart",
                        self._process.returncode
                    )
                    await self._handle_subprocess_exit(f"subprocess exited with code {self._process.returncode}")
                    continue

                # Check for data reception timeout
                if self._last_data_received > 0:
                    time_since_data = time.time() - self._last_data_received
                    if time_since_data > self._connection_timeout:
                        _LOGGER.warning(
                            "HEALTH_TIMEOUT | no data for %.0fs (limit: %.0fs) | "
                            "last data: %s | host: %s:%s | "
                            "data lines: %d | triggering restart",
                            time_since_data,
                            self._connection_timeout,
                            time.strftime("%H:%M:%S", time.localtime(self._last_data_received)),
                            self._host, self._port,
                            self._stats["total_data_lines"]
                        )
                        # Force stop the subprocess and trigger restart
                        await self._stop_subprocess()
                        await self._handle_subprocess_exit(f"connection timeout ({time_since_data:.0f}s no data)")
                        continue

                # Only log health check OK at debug level to avoid log spam
                _LOGGER.debug(
                    "HEALTH_OK | PID: %s | data age: %.0fs | "
                    "session: %.1f min | lines: %d | restarts: %d",
                    self._process.pid if self._process else "N/A",
                    time.time() - self._last_data_received if self._last_data_received > 0 else 0,
                    (time.time() - self._stats["current_session_start"]) / 60 if self._stats["current_session_start"] else 0,
                    self._stats["total_data_lines"],
                    self._stats["total_restarts"]
                )

        except asyncio.CancelledError:
            _LOGGER.debug("Health check loop cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Error in health check loop: %s", err)

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

        # Cancel health check task
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        await self._stop_subprocess()

    async def async_execute_command(
        self, device_key: str, command: str, value: int | None = None
    ) -> bool:
        """Execute a control command via separate CLI subprocess.

        This spawns a SHORT-LIVED CLI process to execute the command.
        The persistent watch process continues running in the background.

        Commands are throttled with a delay between executions to prevent
        overwhelming the IPCom server when multiple commands are sent rapidly
        (e.g., automations turning off all lights).

        Args:
            device_key: Device identifier (e.g., "keuken")
            command: Command to execute ("on", "off", "dim")
            value: Optional value for dim command (0-100)

        Returns:
            True if command succeeded, False otherwise
        """
        # Acquire lock to ensure commands execute serially
        async with self._command_lock:
            # Calculate delay needed since last command
            now = time.time()
            time_since_last = now - self._last_command_time

            if time_since_last < self._command_delay:
                delay_needed = self._command_delay - time_since_last
                _LOGGER.debug(
                    "Throttling command to %s: waiting %.0fms",
                    device_key,
                    delay_needed * 1000
                )
                await asyncio.sleep(delay_needed)

            try:
                # Build command
                cli_script = os.path.join(self._cli_path, "ipcom_cli.py")
                python_exe = get_python_executable()
                cmd = [
                    python_exe,
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
                    "--username",
                    self._username,
                    "--password",
                    self._password,
                    "--devices-file",
                    self._devices_file,
                ])

                _LOGGER.debug("Executing command: %s %s %s ...", cmd[0], cmd[1], cmd[2])

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

                # Update timestamp for throttling
                self._last_command_time = time.time()

                # State update will arrive via watch process - no need to refresh

                return True

            except asyncio.TimeoutError:
                _LOGGER.error("Command timed out after 10s")
                return False
            except Exception as err:
                _LOGGER.error("Error executing command: %s", err)
                return False
