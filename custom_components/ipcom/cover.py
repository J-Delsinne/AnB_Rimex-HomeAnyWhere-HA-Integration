"""Cover platform for IPCom integration - Dual-Relay Shutter Control.

ARCHITECTURE
------------
This platform implements a BEHAVIOR LAYER that translates Home Assistant
cover commands into safe dual-relay operations.

HARDWARE TRUTH (Authoritative)
-------------------------------
Each physical shutter is controlled by TWO independent relays:
  - UP relay (opens shutter)
  - DOWN relay (closes shutter)

Relay Truth Table:
  UP  DOWN  Result
  0   0     STOP / IDLE
  1   0     MOVING UP (opening)
  0   1     MOVING DOWN (closing)
  1   1     ❌ INVALID - MUST NEVER OCCUR

SAFETY REQUIREMENTS
-------------------
1. UP=1 & DOWN=1 must NEVER be commanded
2. STOP is achieved by setting both relays to 0
3. Commands must be idempotent
4. No time-based assumptions or delays

BEHAVIOR LAYER MAPPING
----------------------
Home Assistant Command → Relay Sequence:

open_cover:
  1. If DOWN is ON → turn it OFF
  2. Turn UP ON
  Result: UP=1, DOWN=0

close_cover:
  1. If UP is ON → turn it OFF
  2. Turn DOWN ON
  Result: UP=0, DOWN=1

stop_cover:
  1. Turn UP OFF
  2. Turn DOWN OFF
  Result: UP=0, DOWN=0

STATE REPORTING
---------------
Derive cover state from relay states:
  - opening → UP=1, DOWN=0
  - closing → UP=0, DOWN=1
  - stopped → UP=0, DOWN=0
  - invalid → UP=1, DOWN=1 (log warning, treat as stopped)

CONSTRAINTS
-----------
❌ DO NOT modify: CLI, protocol, TCP layer, JSON contract
✅ ONLY modify: This cover.py behavior logic
✅ Use existing CLI commands: on, off (unchanged)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IPComCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IPCom covers from config entry.

    Creates cover entities for devices with relay_role='up' (paired shutters).
    Each cover entity controls both UP and DOWN relays for a single physical shutter.

    Args:
        hass: Home Assistant instance
        entry: ConfigEntry created by config flow
        async_add_entities: Callback to add entities
    """
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Create entities only for UP relays (each UP relay represents one physical shutter)
    entities = []

    if coordinator.data and "devices" in coordinator.data:
        for entity_key, device_data in coordinator.data["devices"].items():
            category = device_data.get("category")
            relay_role = device_data.get("relay_role")

            # Only create cover entities for shutters with relay_role='up'
            # (Each UP relay controls one physical shutter via UP+DOWN pair)
            if category == "shutters" and relay_role == "up":
                device_key = device_data.get("device_key")
                paired_device_key = device_data.get("paired_device")

                if not paired_device_key:
                    _LOGGER.error(
                        "Shutter %s has relay_role='up' but missing paired_device",
                        device_key
                    )
                    continue

                _LOGGER.debug(
                    "Creating dual-relay cover: %s (UP: %s, DOWN: %s)",
                    entity_key,
                    device_key,
                    paired_device_key,
                )

                entity = IPComDualRelayCover(
                    coordinator,
                    entity_key,
                    device_data,
                    up_device_key=device_key,
                    down_device_key=paired_device_key
                )
                entities.append(entity)

    if entities:
        _LOGGER.info("Adding %d dual-relay cover entities", len(entities))
        async_add_entities(entities, update_before_add=True)
    else:
        _LOGGER.warning("No cover entities found in coordinator data")


class IPComDualRelayCover(CoordinatorEntity, CoverEntity):
    """Dual-Relay Cover Entity with Safety Layer.

    This entity represents a single physical shutter controlled by two relays.
    It implements a safety behavior layer that ensures UP=1 & DOWN=1 never occurs.

    Attributes:
        _up_device_key: Device key for UP relay (e.g., "rolluik_sal_links_m")
        _down_device_key: Device key for DOWN relay (e.g., "rolluik_sal_links_d")

    State Derivation:
        Read both relay states from coordinator data and derive cover state.

    Command Safety:
        All commands ensure opposite relay is OFF before activating target relay.
    """

    # Supported features: open, close, and stop
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
    )

    # Device class for shutters
    _attr_device_class = CoverDeviceClass.SHUTTER

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
        up_device_key: str,
        down_device_key: str,
    ) -> None:
        """Initialize the dual-relay cover.

        Args:
            coordinator: Data coordinator
            entity_key: Unique entity key (category.device_key for UP relay)
            device_data: Device data for UP relay from CLI JSON
            up_device_key: Device key for UP relay
            down_device_key: Device key for DOWN relay (paired device)
        """
        super().__init__(coordinator)

        self._entity_key = entity_key
        self._up_device_key = up_device_key
        self._down_device_key = down_device_key

        # Extract shutter name (remove _m suffix from UP relay name)
        # Example: "rolluik_sal_links_m" → "rolluik_sal_links"
        shutter_base_name = up_device_key.replace("_m", "")

        self._attr_unique_id = f"ipcom_cover_{shutter_base_name}"
        self._attr_name = device_data.get("display_name", shutter_base_name.upper()).replace(" M", "")

        # Store module/output for debugging
        self._module = device_data.get("module")
        self._up_output = device_data.get("output")

        _LOGGER.debug(
            "Initialized dual-relay cover %s: UP=%s, DOWN=%s",
            self._attr_name,
            up_device_key,
            down_device_key,
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping in HA UI."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": "Home Anywhere Blue",
            "model": "IPCom Dual-Relay Shutter",
            "sw_version": f"Module {self._module}",
        }

    def _get_relay_state(self, device_key: str) -> int:
        """Get current state of a relay from coordinator data.

        Args:
            device_key: Device key for the relay

        Returns:
            Relay value (0=OFF, >0=ON), or 0 if unknown
        """
        if not self.coordinator.data or "devices" not in self.coordinator.data:
            return 0

        entity_key = f"shutters.{device_key}"
        device_data = self.coordinator.data["devices"].get(entity_key)

        if not device_data:
            _LOGGER.warning("Could not find device data for %s", device_key)
            return 0

        return device_data.get("value", 0)

    @property
    def is_opening(self) -> bool:
        """Return true if cover is opening.

        Opening state: UP=1, DOWN=0
        """
        up_state = self._get_relay_state(self._up_device_key)
        down_state = self._get_relay_state(self._down_device_key)

        return up_state > 0 and down_state == 0

    @property
    def is_closing(self) -> bool:
        """Return true if cover is closing.

        Closing state: UP=0, DOWN=1
        """
        up_state = self._get_relay_state(self._up_device_key)
        down_state = self._get_relay_state(self._down_device_key)

        return up_state == 0 and down_state > 0

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed.

        We have no position feedback, so we derive state from relay activity:
        - If last movement was DOWN → consider closed
        - If last movement was UP → consider open
        - If both OFF (stopped) → state unknown (return None)

        Note: This is a best-effort heuristic without position sensors.
        """
        up_state = self._get_relay_state(self._up_device_key)
        down_state = self._get_relay_state(self._down_device_key)

        # Safety check: Both relays ON is invalid
        if up_state > 0 and down_state > 0:
            _LOGGER.error(
                "SAFETY VIOLATION: Both relays ON for %s (UP=%d, DOWN=%d)",
                self._attr_name,
                up_state,
                down_state,
            )
            return None

        # Derive state from relay activity
        if down_state > 0:
            return False  # Currently closing, assume will be/is closed
        elif up_state > 0:
            return False  # Currently opening, assume will be/is open
        else:
            return None  # Both OFF (stopped), position unknown

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (move UP).

        Behavior Sequence:
        1. If DOWN relay is ON → turn it OFF (safety)
        2. Turn UP relay ON

        Target State: UP=1, DOWN=0

        Args:
            **kwargs: Additional arguments (unused)
        """
        _LOGGER.debug("Opening cover %s", self._attr_name)

        # SAFETY: Ensure DOWN relay is OFF before activating UP
        down_state = self._get_relay_state(self._down_device_key)
        if down_state > 0:
            _LOGGER.debug(
                "Safety: Turning OFF DOWN relay %s before opening",
                self._down_device_key
            )
            success = await self.coordinator.async_execute_command(
                self._down_device_key, "off"
            )
            if not success:
                _LOGGER.error(
                    "Failed to turn OFF DOWN relay %s, aborting open",
                    self._down_device_key
                )
                return

        # Activate UP relay
        success = await self.coordinator.async_execute_command(
            self._up_device_key, "on"
        )

        if not success:
            _LOGGER.error("Failed to turn ON UP relay %s", self._up_device_key)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (move DOWN).

        Behavior Sequence:
        1. If UP relay is ON → turn it OFF (safety)
        2. Turn DOWN relay ON

        Target State: UP=0, DOWN=1

        Args:
            **kwargs: Additional arguments (unused)
        """
        _LOGGER.debug("Closing cover %s", self._attr_name)

        # SAFETY: Ensure UP relay is OFF before activating DOWN
        up_state = self._get_relay_state(self._up_device_key)
        if up_state > 0:
            _LOGGER.debug(
                "Safety: Turning OFF UP relay %s before closing",
                self._up_device_key
            )
            success = await self.coordinator.async_execute_command(
                self._up_device_key, "off"
            )
            if not success:
                _LOGGER.error(
                    "Failed to turn OFF UP relay %s, aborting close",
                    self._up_device_key
                )
                return

        # Activate DOWN relay
        success = await self.coordinator.async_execute_command(
            self._down_device_key, "on"
        )

        if not success:
            _LOGGER.error("Failed to turn ON DOWN relay %s", self._down_device_key)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover (both relays OFF).

        Behavior Sequence:
        1. Turn UP relay OFF
        2. Turn DOWN relay OFF

        Target State: UP=0, DOWN=0

        Order doesn't matter since we're turning both OFF.

        Args:
            **kwargs: Additional arguments (unused)
        """
        _LOGGER.debug("Stopping cover %s", self._attr_name)

        # Turn both relays OFF (order doesn't matter)
        up_success = await self.coordinator.async_execute_command(
            self._up_device_key, "off"
        )

        down_success = await self.coordinator.async_execute_command(
            self._down_device_key, "off"
        )

        if not up_success:
            _LOGGER.error("Failed to turn OFF UP relay %s", self._up_device_key)

        if not down_success:
            _LOGGER.error("Failed to turn OFF DOWN relay %s", self._down_device_key)
