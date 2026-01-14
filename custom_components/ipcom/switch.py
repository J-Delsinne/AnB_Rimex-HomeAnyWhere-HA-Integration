"""Switch platform for IPCom integration.

This platform handles devices that are mapped as switches based on their
GraphicType in the Home Anywhere Blue application, such as:
- OutputSocket (power outlets)
- OutputTelevision, OutputWashMachine, etc. (appliances)
- OutputHeater, OutputBoiler, etc. (HVAC controls)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
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
    """Set up IPCom switches from config entry."""
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Check if we have devices config from auto-discovery
    if coordinator.devices_config and "switches" in coordinator.devices_config:
        # Use devices from config entry (auto-discovery)
        for device_key, device_info in coordinator.devices_config["switches"].items():
            entity_key = f"switches.{device_key}"
            device_data = {
                "device_key": device_key,
                "category": "switches",
                **device_info,
            }
            entities.append(IPComSwitch(coordinator, entity_key, device_data))
    elif coordinator.data and "devices" in coordinator.data:
        # Fallback: Use devices from CLI (devices.yaml) that are marked as switches
        for entity_key, device_data in coordinator.data["devices"].items():
            category = device_data.get("category")
            device_type = device_data.get("type", "")
            # Look for switch-type devices
            if category == "switches" or device_type == "switch":
                entities.append(IPComSwitch(coordinator, entity_key, device_data))

    async_add_entities(entities)


class IPComSwitch(CoordinatorEntity[IPComCoordinator], SwitchEntity):
    """Representation of an IPCom switch (socket, appliance, etc.)."""

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entity_key = entity_key
        self._device_key = device_data["device_key"]
        self._attr_unique_id = f"ipcom_{self._device_key}"
        self._attr_name = device_data.get("display_name", self._device_key.upper())

        # Store device metadata for device_info
        self._module = device_data.get("module")
        self._output = device_data.get("output")
        self._graphic_type = device_data.get("graphic_type", "")

        # Set device class from GraphicType mapping (e.g., "outlet" for sockets)
        device_class = device_data.get("device_class")
        if device_class:
            try:
                self._attr_device_class = SwitchDeviceClass(device_class)
            except ValueError:
                # Unknown device class, leave as None
                pass

        # Set custom icon if specified in mapping
        custom_icon = device_data.get("icon")
        if custom_icon:
            self._attr_icon = custom_icon

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping in HA UI."""
        model = "IPCom Switch"
        if self._graphic_type == "OutputSocket":
            model = "IPCom Socket"
        elif self._graphic_type in ("OutputHeater", "OutputElectricHeater", "OutputBoiler"):
            model = "IPCom HVAC"
        elif self._graphic_type in ("OutputTelevision", "OutputWashMachine", "OutputDishWasher"):
            model = "IPCom Appliance"

        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": "Home Anywhere Blue",
            "model": model,
            "sw_version": f"Module {self._module}",
        }

    @property
    def is_on(self) -> bool:
        """Return True if switch is on."""
        if not self.coordinator.data or "devices" not in self.coordinator.data:
            return False
        device_data = self.coordinator.data["devices"].get(self._entity_key)
        if device_data is None:
            return False
        return device_data.get("state", 0) > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_execute_command(self._device_key, "on")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_execute_command(self._device_key, "off")
        await self.coordinator.async_request_refresh()
