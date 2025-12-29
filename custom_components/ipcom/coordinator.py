"""DataUpdateCoordinator for IPCom integration."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class IPComCoordinator(DataUpdateCoordinator):
    """Class to manage fetching IPCom data using persistent connection.

    UPGRADED: Now uses persistent TCP connection with background loops instead of
    subprocess calls. This matches the official HomeAnywhere app behavior.

    Architecture:
    - Maintains a single persistent IPComClient instance
    - Uses 3 background loops (keep-alive, status poll, command queue)
    - Receives real-time state updates via callbacks
    - No more connect-poll-disconnect overhead

    Benefits vs. old approach:
    - 29× faster updates (350ms vs 10s)
    - Real-time state changes
    - Instant command execution
    - Reduced CPU/network overhead
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
            cli_path: Path to ipcom directory (for importing modules)
            host: IPCom server host
            port: IPCom server port
            scan_interval: Fallback update interval (persistent connection updates at 350ms)
        """
        self.cli_path = cli_path
        self.host = host
        self.port = port
        self._client = None
        self._device_mapper = None
        self._latest_data = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Note: scan_interval is now just a fallback. Real updates happen at 350ms via callbacks
            update_interval=timedelta(seconds=scan_interval),
        )

    async def async_start(self) -> bool:
        """Start the persistent connection and background loops.

        Returns:
            True if connection started successfully, False otherwise
        """
        _LOGGER.critical("coordinator.async_start() CALLED")
        try:
            # Import IPCom modules dynamically
            _LOGGER.critical("Importing IPCom modules from: %s", self.cli_path)
            cli_dir = os.path.dirname(self.cli_path)
            _LOGGER.critical("CLI dir: %s", cli_dir)
            if cli_dir not in sys.path:
                sys.path.insert(0, cli_dir)
                _LOGGER.critical("Added to sys.path")

            _LOGGER.critical("Importing IPComClient...")
            from ipcom_tcp_client import IPComClient
            _LOGGER.critical("Importing DeviceMapper...")
            from ipcom_cli import DeviceMapper
            _LOGGER.critical("Imports successful")

            # Create client and mapper
            _LOGGER.critical("Creating IPComClient...")
            self._client = IPComClient(host=self.host, port=self.port, debug=False)
            _LOGGER.critical("Creating DeviceMapper...")

            # DeviceMapper needs the full path to devices.yaml
            devices_yaml_path = os.path.join(cli_dir, "devices.yaml")
            _LOGGER.critical("Loading devices from: %s", devices_yaml_path)
            self._device_mapper = DeviceMapper(config_file=devices_yaml_path)
            _LOGGER.critical("DeviceMapper created with %d devices", len(self._device_mapper.devices))
            _LOGGER.critical("Client and mapper created")

            # Register callback for state updates
            def on_snapshot(snapshot):
                """Handle state snapshot updates from background loop."""
                try:
                    _LOGGER.debug(f"Received snapshot callback (timestamp: {snapshot.timestamp})")

                    # Convert snapshot to device data
                    devices_data = self._snapshot_to_devices(snapshot)
                    _LOGGER.debug(f"Converted snapshot to {len(devices_data)} devices")

                    # Store latest data
                    self._latest_data = {
                        "timestamp": snapshot.timestamp_iso,
                        "devices": devices_data
                    }

                    # Trigger coordinator update without fetching (data is already fresh)
                    # Schedule the update in the event loop
                    _LOGGER.debug("Scheduling coordinator update via call_soon_threadsafe")
                    self.hass.loop.call_soon_threadsafe(
                        lambda: self.async_set_updated_data(self._latest_data)
                    )
                    _LOGGER.debug("Coordinator update scheduled successfully")

                except Exception as e:
                    _LOGGER.error(f"Error processing snapshot callback: {e}", exc_info=True)

            _LOGGER.critical("Registering snapshot callback...")
            self._client.on_state_snapshot(on_snapshot)
            _LOGGER.critical("Callback registered")

            # Start persistent connection in executor (blocking call)
            _LOGGER.critical("Starting persistent connection via executor...")
            success = await self.hass.async_add_executor_job(
                self._client.start_persistent_connection,
                True  # auto_reconnect
            )
            _LOGGER.critical("Executor returned, success=%s", success)

            if success:
                _LOGGER.critical(
                    "Persistent connection started: %s:%d (updates every 350ms)",
                    self.host,
                    self.port
                )

                # Give the persistent connection a moment to receive first snapshot
                # The status poll loop runs every 350ms, so wait up to 1 second
                _LOGGER.critical("Waiting for first snapshot to arrive...")
                for i in range(10):  # Wait up to 1 second (10 * 0.1s)
                    if self._latest_data:
                        _LOGGER.critical(f"First snapshot received after {(i+1)*0.1:.1f}s with {len(self._latest_data.get('devices', {}))} devices")
                        break
                    _LOGGER.critical(f"Waiting iteration {i+1}/10, latest_data={self._latest_data}")
                    await asyncio.sleep(0.1)

                if not self._latest_data:
                    _LOGGER.critical("No snapshot received after 1 second - will continue waiting in background")
                    _LOGGER.critical("Client connected: %s", self._client.is_connected() if self._client else "No client")

            else:
                _LOGGER.error("Failed to start persistent connection")

            _LOGGER.critical("async_start() returning success=%s", success)
            return success

        except Exception as e:
            _LOGGER.error(f"Error starting persistent connection: {e}", exc_info=True)
            return False

    async def async_stop(self):
        """Stop the persistent connection and cleanup."""
        if self._client:
            _LOGGER.info("Stopping persistent connection...")
            await self.hass.async_add_executor_job(
                self._client.stop_persistent_connection
            )
            self._client = None

    def _snapshot_to_devices(self, snapshot) -> dict:
        """Convert StateSnapshot to devices dict.

        Args:
            snapshot: StateSnapshot object

        Returns:
            Dict mapping "category.device_key" to device data
        """
        from models import StateSnapshot

        devices = {}

        # Iterate through all mapped devices
        for device_key, device_info in self._device_mapper.devices.items():
            module = device_info["module"]
            output = device_info["output"]
            category = device_info["category"]
            device_type = device_info["type"]

            # Get value from snapshot
            value = snapshot.get_value(module, output)
            if value is None:
                continue

            # Determine state
            state = "on" if value > 0 else "off"

            # Build device data
            device_data = {
                "device_key": device_key,
                "display_name": device_info["display_name"],
                "category": category,
                "type": device_type,
                "module": module,
                "output": output,
                "value": value,
                "state": state,
            }

            # Add brightness for dimmers
            if device_type == "dimmer":
                # Module 6 (EXO DIM) uses 0-100, others use 0-255
                if module == 6:
                    brightness = value
                else:
                    brightness = int((value / 255.0) * 100)
                device_data["brightness"] = brightness

            # Add to devices dict with composite key
            entity_key = f"{category}.{device_key}"
            devices[entity_key] = device_data

        return devices

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from IPCom (fallback only - real updates via callbacks).

        In persistent connection mode, this method is rarely called because
        state updates happen automatically via the 350ms polling loop callback.

        This method only serves as a fallback if:
        1. The persistent connection hasn't started yet
        2. The connection is temporarily down
        3. Manual refresh is requested

        Returns:
            Dictionary with device data, or raises UpdateFailed
        """
        # If we have recent data from callback, return it
        if self._latest_data:
            _LOGGER.debug(f"Returning cached data with {len(self._latest_data.get('devices', {}))} devices")
            return self._latest_data

        # No data available yet
        _LOGGER.debug(f"No cached data available. Client connected: {self._client.is_connected() if self._client else False}")
        if not self._client or not self._client.is_connected():
            raise UpdateFailed("Persistent connection not established")

        # Wait for first snapshot (give it up to 2 seconds on first load)
        _LOGGER.debug("Waiting for first snapshot from persistent connection...")
        for i in range(20):  # Wait up to 2 seconds (20 * 0.1s)
            if self._latest_data:
                _LOGGER.debug(f"Received first snapshot after {(i+1)*0.1:.1f}s")
                return self._latest_data
            await asyncio.sleep(0.1)

        # Still no data - this is an error
        raise UpdateFailed("No snapshot data received after 2 seconds. Check connection to device.")

    async def async_execute_command(
        self, device_key: str, command: str, value: int | None = None
    ) -> bool:
        """Execute a control command via persistent connection.

        Commands are queued and executed by the command queue loop,
        which automatically pauses status polling during execution.

        Args:
            device_key: Device identifier (e.g., "keuken")
            command: Command to execute ("on", "off", "toggle", "dim")
            value: Optional value for dim command (0-100)

        Returns:
            True if command succeeded, False otherwise
        """
        if not self._client or not self._client.is_connected():
            _LOGGER.error("Cannot execute command: not connected")
            return False

        if not self._device_mapper:
            _LOGGER.error("Cannot execute command: device mapper not initialized")
            return False

        try:
            # Get device info from mapper
            device_info = self._device_mapper.get_device(device_key)
            if not device_info:
                _LOGGER.error(f"Device not found: {device_key}")
                return False

            module = device_info["module"]
            output = device_info["output"]

            # Execute command based on type
            if command == "on":
                _LOGGER.debug(f"Queuing ON command for {device_key} (M{module}O{output})")
                await self.hass.async_add_executor_job(
                    self._client.queue_command,
                    self._client.turn_on,
                    module,
                    output
                )

            elif command == "off":
                _LOGGER.debug(f"Queuing OFF command for {device_key} (M{module}O{output})")
                await self.hass.async_add_executor_job(
                    self._client.queue_command,
                    self._client.turn_off,
                    module,
                    output
                )

            elif command == "dim":
                if value is None:
                    _LOGGER.error("Dim command requires value")
                    return False

                _LOGGER.debug(f"Queuing DIM command for {device_key} (M{module}O{output}) to {value}%")
                await self.hass.async_add_executor_job(
                    self._client.queue_command,
                    self._client.set_dimmer,
                    module,
                    output,
                    value
                )

            elif command == "toggle":
                # Get current state
                current_value = self._client.get_value(module, output)
                if current_value is None:
                    _LOGGER.error(f"Cannot toggle: no current state for {device_key}")
                    return False

                # Toggle
                if current_value > 0:
                    _LOGGER.debug(f"Toggling {device_key} OFF (current: {current_value})")
                    await self.hass.async_add_executor_job(
                        self._client.queue_command,
                        self._client.turn_off,
                        module,
                        output
                    )
                else:
                    _LOGGER.debug(f"Toggling {device_key} ON (current: {current_value})")
                    await self.hass.async_add_executor_job(
                        self._client.queue_command,
                        self._client.turn_on,
                        module,
                        output
                    )

            else:
                _LOGGER.error(f"Unknown command: {command}")
                return False

            # Command queued successfully
            # State will update automatically via 350ms polling loop callback
            return True

        except Exception as err:
            _LOGGER.error(f"Error executing command: {err}", exc_info=True)
            return False
