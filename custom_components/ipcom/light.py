"""Light platform for IPCom integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
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
    """Set up IPCom lights from config entry."""
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for entity_key, device_data in coordinator.data["devices"].items():
        category = device_data.get("category")
        if category == "lights":
            device_type = device_data.get("type", "switch")
            if device_type == "dimmer":
                entities.append(IPComDimmerLight(coordinator, entity_key, device_data))
            else:
                entities.append(IPComLight(coordinator, entity_key, device_data))

    async_add_entities(entities)


class IPComLight(CoordinatorEntity[IPComCoordinator], LightEntity):
    """Representation of an IPCom on/off light."""

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._entity_key = entity_key
        self._device_key = device_data["device_key"]
        self._attr_unique_id = f"ipcom_{self._device_key}"
        self._attr_name = device_data.get("display_name", self._device_key.upper())
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_supported_color_modes = {ColorMode.ONOFF}

        # Store device metadata for device_info
        self._module = device_data.get("module")
        self._output = device_data.get("output")

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information for grouping in HA UI."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": "Home Anywhere Blue",
            "model": "IPCom Light",
            "sw_version": f"Module {self._module}",
        }

    @property
    def is_on(self) -> bool:
        """Return True if light is on."""
        device_data = self.coordinator.data["devices"].get(self._entity_key)
        if not device_data:
            return False
        return device_data.get("state") == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self.coordinator.async_execute_command(self._device_key, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.coordinator.async_execute_command(self._device_key, "off")


class IPComDimmerLight(IPComLight):
    """Representation of an IPCom dimmable light."""

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the dimmable light."""
        super().__init__(coordinator, entity_key, device_data)
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light (0-255)."""
        device_data = self.coordinator.data["devices"].get(self._entity_key)
        if not device_data:
            return None

        # CLI returns brightness 0-100
        cli_brightness = device_data.get("brightness", 0)
        # Convert to HA's 0-255 range
        return int((cli_brightness / 100) * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally setting brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            # Convert HA brightness (0-255) to CLI (0-100)
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            cli_brightness = int((ha_brightness / 255) * 100)
            # Ensure minimum brightness of 1% when turning on
            if cli_brightness == 0:
                cli_brightness = 1
            await self.coordinator.async_execute_command(
                self._device_key, "dim", cli_brightness
            )
        else:
            # No brightness specified, just turn on
            await self.coordinator.async_execute_command(self._device_key, "on")
