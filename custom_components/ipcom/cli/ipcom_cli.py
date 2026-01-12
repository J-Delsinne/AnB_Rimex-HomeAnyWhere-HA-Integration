#!/usr/bin/env python3
"""
Home Anywhere Blue - IPCom CLI

Human-friendly command-line interface for IPCom device control.

Commands:
  status                  - Show full system state
  on <name>               - Turn device ON
  off <name>              - Turn device OFF
  toggle <name>           - Toggle device state
  dim <name> <0-100>      - Set dimmer level (percentage)
  watch                   - Live monitoring with device names
  cover_open <name>       - Open shutter/cover (safe dual-relay)
  cover_close <name>      - Close shutter/cover (safe dual-relay)
  cover_stop <name>       - Stop shutter/cover movement

Examples:
  python ipcom_cli.py status
  python ipcom_cli.py on keuken
  python ipcom_cli.py dim salon 40
  python ipcom_cli.py watch
  python ipcom_cli.py cover_open rolluik_sal_links_m
  python ipcom_cli.py cover_stop rolluik_sal_links_m
"""

import sys
import time
import argparse
import json
import logging
import socket
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List

# Configure stdout for UTF-8 on Windows
# NOTE: Only reconfigure if not already UTF-8 to avoid issues with stream redirection
if sys.platform == 'win32':
    try:
        if sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, OSError):
        # Python < 3.7 or reconfigure not available
        # Only wrap if not already wrapped
        if not isinstance(sys.stdout, codecs.StreamWriter):
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')


class DeviceMapper:
    """Manages device name to module/output mapping."""

    def __init__(self, config_file: str = "devices.yaml"):
        self.devices = {}
        self.device_categories = {}  # Maps device_key -> category name
        self.config_file = config_file
        self._load_config()
        self._validate_mapping()

    def _load_config(self):
        """Load device mapping from YAML file."""
        config_path = Path(self.config_file)

        if not config_path.exists():
            print(f"Warning: {self.config_file} not found. No device names available.")
            print(f"Create {self.config_file} to define device names.")
            return

        try:
            import yaml
        except ImportError:
            # Fallback: simple YAML parser for basic structure
            self._load_config_simple(config_path)
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Load all categories (lights, shutters, etc.)
        if config:
            for category_name, category_devices in config.items():
                if isinstance(category_devices, dict):
                    for device_key, device_config in category_devices.items():
                        self.devices[device_key] = device_config
                        self.device_categories[device_key] = category_name

    def _load_config_simple(self, config_path: Path):
        """Simple YAML parser fallback (no pyyaml dependency)."""
        with open(config_path, 'r', encoding='utf-8') as f:
            current_category = None
            current_device = None
            current_data = {}

            for line in f:
                line = line.rstrip()

                # Skip comments and empty lines
                if not line or line.strip().startswith('#'):
                    continue

                # Category headers (no indent, ends with :)
                if line and not line[0].isspace() and line.strip().endswith(':'):
                    # Save previous device before changing category
                    if current_device and current_data and current_category:
                        self.devices[current_device] = current_data
                        self.device_categories[current_device] = current_category
                        current_device = None
                        current_data = {}

                    current_category = line.strip().rstrip(':')
                    continue

                # Device name (2 spaces indent)
                if line.startswith('  ') and not line.startswith('    '):
                    # Save previous device
                    if current_device and current_data and current_category:
                        self.devices[current_device] = current_data
                        self.device_categories[current_device] = current_category

                    current_device = line.strip().rstrip(':')
                    current_data = {}

                # Device properties (4 spaces indent)
                elif line.startswith('    '):
                    if current_device:
                        parts = line.strip().split(':', 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            value = parts[1].strip().strip('"').strip("'")

                            # Convert numeric values
                            if key in ('module', 'output'):
                                value = int(value)

                            current_data[key] = value

            # Save last device
            if current_device and current_data and current_category:
                self.devices[current_device] = current_data
                self.device_categories[current_device] = current_category

    def _validate_mapping(self):
        """Validate mapping for conflicts and errors."""
        seen_addresses = {}
        seen_display_names = {}

        for device_key, config in self.devices.items():
            module = config.get('module')
            output = config.get('output')

            if module is None or output is None:
                print(f"⚠️ Warning: Device '{device_key}' missing module or output")
                continue

            # Check for duplicate module/output combinations
            address = (module, output)
            if address in seen_addresses:
                print(f"❌ ERROR: Duplicate module/output mapping detected!")
                print(f"   Module {module}, Output {output} is assigned to both:")
                print(f"   - {seen_addresses[address]}")
                print(f"   - {device_key}")
                sys.exit(1)

            seen_addresses[address] = device_key

            # Check for duplicate display names
            display_name = config.get('display_name', device_key.upper())
            if display_name in seen_display_names:
                print(f"⚠️ Warning: Duplicate display name '{display_name}' for:")
                print(f"   - {seen_display_names[display_name]}")
                print(f"   - {device_key}")

            seen_display_names[display_name] = device_key

    def get_device(self, name: str) -> Optional[Dict]:
        """Get device config by name (case-insensitive)."""
        return self.devices.get(name.lower())

    def get_device_name(self, module: int, output: int) -> Optional[str]:
        """Get device display name by module/output (reverse lookup)."""
        for name, config in self.devices.items():
            if config.get('module') == module and config.get('output') == output:
                return config.get('display_name', name.upper())
        return None

    def list_devices(self) -> Dict:
        """Get all configured devices."""
        return self.devices

    def get_category(self, device_key: str) -> Optional[str]:
        """Get category for a device."""
        return self.device_categories.get(device_key.lower())

    def get_all_device_data(self) -> List[Dict]:
        """Get all devices with full metadata, sorted by module/output."""
        devices = []
        for device_key, config in self.devices.items():
            device_data = {
                'device_key': device_key,
                'display_name': config.get('display_name', device_key.upper()),
                'category': self.device_categories.get(device_key, 'unknown'),
                'type': config.get('type', 'switch'),
                'module': config.get('module'),
                'output': config.get('output'),
                'description': config.get('description', '')
            }

            # Add shutter-specific metadata (relay_role and paired_device)
            if 'relay_role' in config:
                device_data['relay_role'] = config['relay_role']
            if 'paired_device' in config:
                device_data['paired_device'] = config['paired_device']

            devices.append(device_data)

        # Sort by module, then output for stable ordering
        devices.sort(key=lambda d: (d['module'] or 0, d['output'] or 0))
        return devices


def print_status(client: "IPComClient", mapper: DeviceMapper):
    """Print full system state overview."""
    print("\n" + "=" * 60)
    print("IPCom State Snapshot")
    print("=" * 60 + "\n")

    snapshot = client.get_latest_snapshot()

    if not snapshot:
        print("❌ No state snapshot available")
        print("   Make sure polling is started and wait a moment.")
        return

    active_outputs = []

    # Print all modules
    for module in range(1, 17):
        module_values = snapshot.get_module_values(module)
        has_active = any(v > 0 for v in module_values)

        if has_active:
            print(f"Module {module}:")

            for output in range(1, 9):
                value = module_values[output - 1]
                device_name = mapper.get_device_name(module, output)

                if value > 0:
                    active_outputs.append((module, output, value, device_name))

                    if device_name:
                        name_str = f" ({device_name})"  # Already in display format
                    else:
                        name_str = ""

                    state_str = _format_value(value, module)

                    marker = " ← ACTIVE" if value > 0 else ""
                    print(f"  Output {output}: {value:3d} [{state_str}]{name_str}{marker}")

            print()

    # Print active outputs summary
    print("=" * 60)
    print(f"Active outputs: {len(active_outputs)}")
    print("=" * 60)

    if active_outputs:
        for module, output, value, device_name in active_outputs:
            name_str = f" ({device_name})" if device_name else ""  # Already in display format

            state_str = _format_value(value, module)

            print(f"  Module {module:2d}, Output {output} = {value:3d} [{state_str}]{name_str}")
    else:
        print("  (none)")

    print()


def control_device(client: "IPComClient", mapper: DeviceMapper, name: str, action: str, value: Optional[int] = None):
    """Control a device by name."""
    device = mapper.get_device(name)

    if not device:
        print(f"❌ Device '{name}' not found in devices.yaml")
        print(f"\nAvailable devices:")
        for dev_name, dev_config in mapper.list_devices().items():
            display = dev_config.get('display_name', dev_name.upper())
            print(f"  - {dev_name} ({display})")
        return False

    module = device['module']
    output = device['output']
    device_type = device.get('type', 'switch')
    display_name = device.get('display_name', name.upper())

    # Get current state for toggle
    current_value = None
    if action == 'toggle':
        snapshot = client.get_latest_snapshot()
        if snapshot:
            current_value = snapshot.get_value(module, output)

    # Execute action
    try:
        if action == 'on':
            client.turn_on(module, output)
            print(f"✔ {display_name} turned ON (Module {module}, Output {output})")

        elif action == 'off':
            client.turn_off(module, output)
            print(f"✔ {display_name} turned OFF (Module {module}, Output {output})")

        elif action == 'toggle':
            if current_value is None:
                print(f"⚠ Cannot determine current state, defaulting to ON")
                client.turn_on(module, output)
                print(f"✔ {display_name} turned ON (Module {module}, Output {output})")
            elif current_value > 0:
                client.turn_off(module, output)
                print(f"✔ {display_name} toggled OFF (Module {module}, Output {output})")
            else:
                client.turn_on(module, output)
                print(f"✔ {display_name} toggled ON (Module {module}, Output {output})")

        elif action == 'dim':
            if device_type != 'dimmer':
                print(f"⚠ Warning: {display_name} is configured as a switch, not a dimmer")

            if value is None or not (0 <= value <= 100):
                print(f"❌ Invalid dimmer value. Must be 0-100.")
                return False

            client.set_dimmer(module, output, value)
            print(f"✔ {display_name} dimmed to {value}% (Module {module}, Output {output})")

        return True

    except Exception as e:
        print(f"❌ Error controlling {display_name}: {e}")
        return False


def control_cover(client: "IPComClient", mapper: DeviceMapper, name: str, action: str):
    """Control a shutter/cover using dual-relay logic.

    Args:
        client: IPComClient instance
        mapper: DeviceMapper instance
        name: Device key (can be either UP or DOWN relay)
        action: 'open', 'close', or 'stop'

    Returns:
        bool: True if successful, False otherwise

    Safety Rules:
        - NEVER allow UP=1 AND DOWN=1 simultaneously
        - Always turn OFF the opposite relay before turning ON the target relay
        - STOP means both relays OFF (UP=0, DOWN=0)
    """
    # Resolve device (accept either UP or DOWN relay name)
    device = mapper.get_device(name)

    if not device:
        print(f"❌ Device '{name}' not found in devices.yaml")
        print(f"\nAvailable shutter devices:")
        for dev_name, dev_config in mapper.list_devices().items():
            category = mapper.get_category(dev_name)
            if category == "shutters":
                display = dev_config.get('display_name', dev_name.upper())
                relay_role = dev_config.get('relay_role', 'unknown')
                print(f"  - {dev_name} ({display}) [{relay_role}]")
        return False

    # Verify this is a shutter
    category = mapper.get_category(name)
    if category != "shutters":
        print(f"❌ Device '{name}' is not a shutter (category: {category})")
        print(f"Use 'on'/'off' commands for non-shutter devices")
        return False

    # Get relay metadata
    relay_role = device.get('relay_role')
    paired_device_key = device.get('paired_device')

    if not relay_role or not paired_device_key:
        print(f"❌ Shutter '{name}' is missing relay_role or paired_device metadata")
        return False

    # Resolve paired relay
    paired_device = mapper.get_device(paired_device_key)
    if not paired_device:
        print(f"❌ Paired device '{paired_device_key}' not found")
        return False

    # Determine which is UP and which is DOWN
    if relay_role == "up":
        up_relay_name = name
        up_relay = device
        down_relay_name = paired_device_key
        down_relay = paired_device
    elif relay_role == "down":
        down_relay_name = name
        down_relay = device
        up_relay_name = paired_device_key
        up_relay = paired_device
    else:
        print(f"❌ Invalid relay_role: {relay_role} (must be 'up' or 'down')")
        return False

    up_module = up_relay['module']
    up_output = up_relay['output']
    down_module = down_relay['module']
    down_output = down_relay['output']

    # Get logical shutter name (remove _m or _d suffix)
    shutter_name = name.replace('_m', '').replace('_d', '')
    display_name = device.get('display_name', shutter_name.upper()).replace(' M', '').replace(' D', '')

    # Safety check: verify current state
    snapshot = client.get_latest_snapshot()
    if snapshot:
        up_value = snapshot.get_value(up_module, up_output)
        down_value = snapshot.get_value(down_module, down_output)

        if up_value > 0 and down_value > 0:
            print(f"⚠️ WARNING: Invalid state detected! UP=1 AND DOWN=1")
            print(f"   UP relay:   Module {up_module}, Output {up_output} = {up_value}")
            print(f"   DOWN relay: Module {down_module}, Output {down_output} = {down_value}")
            print(f"   This should NEVER happen. Forcing STOP for safety.")
            action = 'stop'

    # Execute action with safety logic
    try:
        if action == 'open':
            # OPEN: Ensure DOWN=0, then set UP=1
            print(f"Opening {display_name}...")
            print(f"  Step 1: Ensuring DOWN relay OFF (Module {down_module}, Output {down_output})")
            client.turn_off(down_module, down_output)

            print(f"  Step 2: Setting UP relay ON (Module {up_module}, Output {up_output})")
            client.turn_on(up_module, up_output)

            print(f"✔ {display_name} opening (UP=1, DOWN=0)")

        elif action == 'close':
            # CLOSE: Ensure UP=0, then set DOWN=1
            print(f"Closing {display_name}...")
            print(f"  Step 1: Ensuring UP relay OFF (Module {up_module}, Output {up_output})")
            client.turn_off(up_module, up_output)

            print(f"  Step 2: Setting DOWN relay ON (Module {down_module}, Output {down_output})")
            client.turn_on(down_module, down_output)

            print(f"✔ {display_name} closing (UP=0, DOWN=1)")

        elif action == 'stop':
            # STOP: Set both relays OFF
            print(f"Stopping {display_name}...")
            print(f"  Setting UP relay OFF (Module {up_module}, Output {up_output})")
            client.turn_off(up_module, up_output)

            print(f"  Setting DOWN relay OFF (Module {down_module}, Output {down_output})")
            client.turn_off(down_module, down_output)

            print(f"✔ {display_name} stopped (UP=0, DOWN=0)")

        else:
            print(f"❌ Invalid cover action: {action} (must be 'open', 'close', or 'stop')")
            return False

        return True

    except Exception as e:
        print(f"❌ Error controlling cover {display_name}: {e}")
        return False


def watch_mode(client: "IPComClient", mapper: DeviceMapper):
    """Live monitoring with device names."""
    print("\n" + "=" * 60)
    print("Live Monitoring Mode (Ctrl+C to exit)")
    print("=" * 60 + "\n")

    snapshot_count = 0
    last_snapshot = None

    def on_snapshot(snapshot):
        nonlocal snapshot_count, last_snapshot
        snapshot_count += 1

        # Get current time
        current_time = time.strftime("%H:%M:%S")

        # Detect changes
        changes = []

        if last_snapshot:
            for module in range(1, 17):
                for output in range(1, 9):
                    old_value = last_snapshot.get_value(module, output)
                    new_value = snapshot.get_value(module, output)

                    if old_value != new_value:
                        device_name = mapper.get_device_name(module, output)

                        if device_name:
                            name_str = device_name  # Already in display format
                        else:
                            name_str = f"Module {module}, Output {output}"

                        changes.append((name_str, old_value, new_value))

        # Print snapshot info
        if changes:
            print(f"[{current_time}] Snapshot #{snapshot_count}")
            print(f"  Changes detected:")
            for name, old_val, new_val in changes:
                old_state = _format_value(old_val)
                new_state = _format_value(new_val)
                print(f"    {name}: {old_state} → {new_state}")
            print()
        elif snapshot_count % 10 == 0:
            # Print periodic heartbeat
            print(f"[{current_time}] Snapshot #{snapshot_count} - No changes")

        last_snapshot = snapshot

    # Register callback
    client.on_state_snapshot(on_snapshot)

    try:
        # Keep running and process incoming data
        while True:
            client._receive_loop()  # Process incoming network data
            time.sleep(0.05)  # Small delay to prevent CPU spin
    except KeyboardInterrupt:
        print("\n\n✔ Monitoring stopped")


def _format_value(value: int, module: int = 0) -> str:
    """
    Format output value for display.

    Args:
        value: Output value (0-255 for regular modules, 0-100 for Module 6)
        module: Module number (needed to detect EXO DIM - Module 6)

    Returns:
        Formatted string (OFF, ON, or percentage)
    """
    if value == 0:
        return "OFF"

    # Module 6 (EXO DIM) uses 0-100 values directly
    if module == 6:
        if value == 100:
            return "ON"  # 100% = full brightness
        else:
            return f"{value}%"  # Value is already percentage
    else:
        # Regular modules use 0-255
        if value == 255:
            return "ON"
        else:
            percentage = int(value / 255 * 100)
            return f"{percentage}%"


def print_status_json(client: "IPComClient", mapper: DeviceMapper, host: str):
    """Print status as JSON for machine consumption."""
    snapshot = client.get_latest_snapshot()

    if not snapshot:
        # Output error as JSON
        error_output = {
            "error": "No state snapshot available",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        print(json.dumps(error_output, ensure_ascii=False))
        return

    # Build device list with current state
    devices = []
    all_device_metadata = mapper.get_all_device_data()

    for device_meta in all_device_metadata:
        module = device_meta['module']
        output = device_meta['output']
        device_type = device_meta['type']

        if module is None or output is None:
            continue

        # Get current value from snapshot
        try:
            value = snapshot.get_value(module, output)
        except (ValueError, IndexError):
            continue

        # Build device state
        device_state = {
            'device_key': device_meta['device_key'],
            'display_name': device_meta['display_name'],
            'category': device_meta['category'],
            'type': device_type,
            'module': module,
            'output': output,
            'supports_brightness': (device_type == 'dimmer'),
            'value': value,
            'state': 'on' if value > 0 else 'off'
        }

        # Add shutter-specific metadata (relay_role and paired_device)
        if 'relay_role' in device_meta:
            device_state['relay_role'] = device_meta['relay_role']
        if 'paired_device' in device_meta:
            device_state['paired_device'] = device_meta['paired_device']

        # Add brightness for dimmers
        if device_type == 'dimmer':
            # Module 6 (EXO DIM) stores brightness as 0-100 directly, not 0-255
            # See: EXO_DIM_STRUCTURE.md
            if module == 6:
                # EXO DIM: Value is already 0-100 percentage
                brightness = value
            else:
                # Regular dimmers: Convert 0-255 to 0-100
                brightness = int((value / 255) * 100) if value > 0 else 0

            device_state['brightness'] = brightness

        devices.append(device_state)

    # Build final output
    output = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'host': host,
        'devices': devices
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


def watch_mode_json(client: "IPComClient", mapper: DeviceMapper, host: str, port: int,
                    username: str, password: str):
    """Live monitoring in JSON format (newline-delimited JSON).

    Features robust connection handling with automatic reconnection
    to ensure continuous operation for Home Assistant integration.
    """
    # Get logger for this module
    logger = logging.getLogger("ipcom_cli.watch")

    snapshot_count = 0
    last_snapshot = None
    last_data_time = time.time()
    session_start_time = time.time()
    CONNECTION_TIMEOUT = 90  # Consider connection dead after 90s of no data
    RECONNECT_DELAY = 5  # Base delay between reconnection attempts

    # Statistics for diagnostics
    stats = {
        "total_snapshots": 0,
        "total_changes": 0,
        "reconnect_count": 0,
        "session_start": time.time(),
        "errors_by_type": {},  # Track error types for diagnostics
    }

    logger.info(
        "WATCH_START | connected to %s:%s | timeout: %ds | "
        "reconnect base delay: %ds | PID: %d",
        host, port, CONNECTION_TIMEOUT, RECONNECT_DELAY, os.getpid() if 'os' in dir() else -1
    )

    # Create reverse lookup: (module, output) -> device_key
    address_to_device = {}
    for device_key, config in mapper.list_devices().items():
        module = config.get('module')
        output = config.get('output')
        if module is not None and output is not None:
            address_to_device[(module, output)] = device_key

    def on_snapshot(snapshot):
        nonlocal snapshot_count, last_snapshot, last_data_time
        snapshot_count += 1
        stats["total_snapshots"] += 1
        last_data_time = time.time()

        # Detect changes
        changes = []

        if last_snapshot:
            for module in range(1, 17):
                for output in range(1, 9):
                    old_value = last_snapshot.get_value(module, output)
                    new_value = snapshot.get_value(module, output)

                    if old_value != new_value:
                        device_key = address_to_device.get((module, output))

                        change = {
                            'module': module,
                            'output': output,
                            'old': old_value,
                            'new': new_value
                        }

                        if device_key:
                            change['device_key'] = device_key
                            change['display_name'] = mapper.get_device_name(module, output)
                            change['category'] = mapper.get_category(device_key)

                        changes.append(change)
                        stats["total_changes"] += 1

        # Output JSON line
        output = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'changes': changes
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.stdout.flush()

        last_snapshot = snapshot

    # Register callback
    client.on_state_snapshot(on_snapshot)

    reconnect_attempts = 0
    loop_iterations = 0

    while True:
        loop_iterations += 1
        try:
            # Check for connection timeout (no data received)
            time_since_data = time.time() - last_data_time
            if time_since_data > CONNECTION_TIMEOUT:
                session_uptime = time.time() - stats["session_start"]
                error_type = "TIMEOUT_NO_DATA"
                stats["errors_by_type"][error_type] = stats["errors_by_type"].get(error_type, 0) + 1
                logger.warning(
                    "%s | no data for %.0fs (limit: %ds) | "
                    "session uptime: %.1f min | snapshots: %d | changes: %d | "
                    "host: %s:%s | reconnects so far: %d",
                    error_type, time_since_data, CONNECTION_TIMEOUT,
                    session_uptime / 60,
                    stats["total_snapshots"],
                    stats["total_changes"],
                    host, port,
                    stats["reconnect_count"]
                )
                raise ConnectionError(f"Connection timeout - no data for {time_since_data:.0f}s")

            # Process incoming network data
            client._receive_loop()
            time.sleep(0.05)  # Small delay to prevent CPU spin

            # Reset reconnect counter on successful data reception
            if time_since_data < 5:
                reconnect_attempts = 0

        except KeyboardInterrupt:
            logger.info("Watch mode interrupted by user")
            break  # Silent exit for JSON mode

        except (socket.error, ConnectionError, OSError) as e:
            reconnect_attempts += 1
            stats["reconnect_count"] += 1
            delay = min(RECONNECT_DELAY * reconnect_attempts, 60)

            # Track error type for diagnostics
            error_type = type(e).__name__
            stats["errors_by_type"][error_type] = stats["errors_by_type"].get(error_type, 0) + 1

            session_uptime = time.time() - stats["session_start"]
            logger.warning(
                "CONN_LOST | error: %s (%s) | "
                "attempt #%d (total: %d) | delay: %ds | "
                "session uptime: %.1f min | snapshots: %d | "
                "error counts: %s",
                error_type, str(e),
                reconnect_attempts, stats["reconnect_count"],
                delay, session_uptime / 60, stats["total_snapshots"],
                json.dumps(stats["errors_by_type"])
            )

            # Clean up old connection
            try:
                client.disconnect()
                logger.debug("Old connection disconnected cleanly")
            except Exception as disconnect_err:
                logger.debug("Error disconnecting old connection: %s", disconnect_err)

            time.sleep(delay)

            # Attempt reconnection
            logger.info("Attempting reconnection to %s:%s...", host, port)
            try:
                # Re-import to get fresh client
                from ipcom_tcp_client import IPComClient

                client = IPComClient(host, port, username=username, password=password)

                if not client.connect():
                    logger.error(
                        "Reconnection failed: could not establish TCP connection to %s:%s",
                        host, port
                    )
                    continue

                logger.debug("TCP connection established, authenticating...")

                if not client.authenticate():
                    logger.error(
                        "Reconnection failed: authentication rejected by %s:%s",
                        host, port
                    )
                    client.disconnect()
                    continue

                logger.debug("Authentication successful, starting polling...")
                client.start_snapshot_polling()
                client.on_state_snapshot(on_snapshot)

                # Wait for first snapshot
                logger.debug("Waiting for first snapshot after reconnect...")
                start = time.time()
                while not client.get_latest_snapshot() and time.time() - start < 5:
                    client._receive_loop()
                    time.sleep(0.05)

                last_data_time = time.time()
                stats["session_start"] = time.time()  # Reset session timer

                logger.info(
                    "RECONNECT_OK | connected to %s:%s | "
                    "attempts this cycle: %d | total reconnects: %d | "
                    "error history: %s",
                    host, port, reconnect_attempts, stats["reconnect_count"],
                    json.dumps(stats["errors_by_type"])
                )

            except Exception as reconnect_err:
                logger.error(
                    "Reconnection attempt #%d failed: %s | will retry in %ds",
                    reconnect_attempts, reconnect_err,
                    min(RECONNECT_DELAY * (reconnect_attempts + 1), 60)
                )
                continue

        except Exception as e:
            logger.error(
                "Unexpected error in watch loop (iteration %d): %s | "
                "continuing operation",
                loop_iterations, e,
                exc_info=True
            )
            # Continue running, don't crash
            time.sleep(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Home Anywhere Blue - IPCom CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                    Show full system state
  %(prog)s on keuken                 Turn kitchen light ON
  %(prog)s off keuken                Turn kitchen light OFF
  %(prog)s toggle eetkamer           Toggle dining room light
  %(prog)s dim salon 40              Dim living room to 40%%
  %(prog)s watch                     Live monitoring mode
  %(prog)s cover_open rolluik_sal_links_m    Open living room left shutter
  %(prog)s cover_stop rolluik_sal_links_m    Stop shutter movement

Device names are defined in devices.yaml
        """
    )

    parser.add_argument('command', choices=['status', 'on', 'off', 'toggle', 'dim', 'watch', 'cover_open', 'cover_close', 'cover_stop'],
                        help='Command to execute')
    parser.add_argument('device', nargs='?', help='Device name (from devices.yaml)')
    parser.add_argument('value', nargs='?', type=int, help='Dimmer value (0-100) for dim command')
    parser.add_argument('--host', required=True, help='IPCom server host')
    parser.add_argument('--port', type=int, default=5000, help='IPCom server port')
    parser.add_argument('--username', required=True, help='IPCom authentication username')
    parser.add_argument('--password', required=True, help='IPCom authentication password')
    parser.add_argument('--json', action='store_true', help='Output in JSON format (for status/watch)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--devices-file', default='devices.yaml', help='Path to devices.yaml configuration file')

    args = parser.parse_args()

    # Configure logging BEFORE importing IPComClient: suppress all output in JSON mode
    if args.json:
        logging.basicConfig(level=logging.CRITICAL + 1)  # Disable all logging
    elif args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Import IPComClient AFTER logging is configured
    # Note: ipcom_tcp_client is in the same directory (ipcom/)
    from ipcom_tcp_client import IPComClient

    # Validate arguments
    if args.command in ('on', 'off', 'toggle', 'dim') and not args.device:
        parser.error(f"{args.command} command requires device name")

    if args.command == 'dim' and args.value is None:
        parser.error("dim command requires dimmer value (0-100)")

    # Validate JSON flag usage
    if args.json and args.command not in ('status', 'watch'):
        parser.error("--json flag only valid with 'status' or 'watch' commands")

    # Load device mapper
    mapper = DeviceMapper(config_file=args.devices_file)

    # Connect to IPCom
    # Suppress connection messages in JSON mode
    if not args.json:
        print(f"Connecting to {args.host}:{args.port}...")

    client = IPComClient(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        debug=args.debug
    )

    try:
        # Connect
        if not client.connect():
            if args.json:
                error = {"error": "Connection failed", "timestamp": datetime.now(timezone.utc).isoformat()}
                print(json.dumps(error, ensure_ascii=False))
            else:
                print("❌ Connection failed")
            return 1

        if not args.debug and not args.json:
            print("✔ Connected")

        # Authenticate
        if not client.authenticate():
            if args.json:
                error = {"error": "Authentication failed", "timestamp": datetime.now(timezone.utc).isoformat()}
                print(json.dumps(error, ensure_ascii=False))
            else:
                print("❌ Authentication failed")
            return 1

        if not args.debug and not args.json:
            print("✔ Authenticated")

        # Start polling
        client.start_snapshot_polling()

        if not args.debug and not args.json:
            print("✔ Polling started")

        # Wait for first snapshot
        if not args.debug and not args.json:
            print("Waiting for initial state...", end='', flush=True)

        start = time.time()
        while not client.get_latest_snapshot() and time.time() - start < 3:
            client._receive_loop()  # Manually process incoming data
            time.sleep(0.05)

        if not args.debug and not args.json:
            print(" Done")

        # Execute command
        if args.command == 'status':
            if args.json:
                print_status_json(client, mapper, args.host)
            else:
                print_status(client, mapper)

        elif args.command == 'watch':
            if args.json:
                watch_mode_json(client, mapper, args.host, args.port,
                               args.username, args.password)
            else:
                watch_mode(client, mapper)

        elif args.command in ('on', 'off', 'toggle'):
            success = control_device(client, mapper, args.device, args.command)
            if not success:
                return 1

        elif args.command == 'dim':
            success = control_device(client, mapper, args.device, args.command, args.value)
            if not success:
                return 1

        elif args.command == 'cover_open':
            success = control_cover(client, mapper, args.device, 'open')
            if not success:
                return 1

        elif args.command == 'cover_close':
            success = control_cover(client, mapper, args.device, 'close')
            if not success:
                return 1

        elif args.command == 'cover_stop':
            success = control_cover(client, mapper, args.device, 'stop')
            if not success:
                return 1

        return 0

    except KeyboardInterrupt:
        if not args.json:
            print("\n\n✔ Interrupted by user")
        return 0

    except Exception as e:
        if args.json:
            error = {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
            print(json.dumps(error, ensure_ascii=False))
        else:
            print(f"\n❌ Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

    finally:
        client.disconnect()
        if not args.debug and not args.json:
            print("✔ Disconnected")


if __name__ == "__main__":
    sys.exit(main())
