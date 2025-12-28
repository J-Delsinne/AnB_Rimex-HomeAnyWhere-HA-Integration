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
    """Set up IPCom lights from a config entry.

    This function is called when the integration is loaded.
    It creates light entities for all devices with category="lights".
    """
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Create entities for all light devices
    entities = []

    if coordinator.data and "devices" in coordinator.data:
        for entity_key, device_data in coordinator.data["devices"].items():
            category = device_data.get("category")

            # Only create entities for lights category
            if category == "lights":
                device_type = device_data.get("type", "switch")

                if device_type == "dimmer":
                    entity = IPComDimmableLight(coordinator, entity_key, device_data)
                else:
                    entity = IPComLight(coordinator, entity_key, device_data)

                entities.append(entity)

    if entities:
        _LOGGER.info("Adding %d light entities", len(entities))
        async_add_entities(entities)
    else:
        _LOGGER.warning("No light entities found in coordinator data")


class IPComLight(CoordinatorEntity, LightEntity):
    """Representation of an IPCom on/off light (switch type).

    This entity represents a non-dimmable light controlled via the CLI.
    """

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the light.

        Args:
            coordinator: Data coordinator
            entity_key: Unique key from coordinator (category.device_key)
            device_data: Device data from CLI JSON
        """
        super().__init__(coordinator)

        self._entity_key = entity_key
        self._device_key = device_data["device_key"]
        self._attr_unique_id = f"ipcom_{self._device_key}"
        self._attr_name = device_data.get("display_name", self._device_key.upper())

        # Store module/output for debugging
        self._module = device_data.get("module")
        self._output = device_data.get("output")

        # On/off light has single color mode
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_key)},
            "name": self._attr_name,
            "manufacturer": "Home Anywhere Blue",
            "model": "IPCom Switch",
            "sw_version": f"Module {self._module}, Output {self._output}",
        }

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        if not self.coordinator.data or "devices" not in self.coordinator.data:
            return False

        device_data = self.coordinator.data["devices"].get(self._entity_key)
        if not device_data:
            return False

        # Use state field from CLI JSON contract
        state = device_data.get("state", "off")
        return state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on via CLI."""
        _LOGGER.debug("Turning on %s", self._device_key)

        success = await self.coordinator.async_execute_command(
            self._device_key, "on"
        )

        if not success:
            _LOGGER.error("Failed to turn on %s", self._device_key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off via CLI."""
        _LOGGER.debug("Turning off %s", self._device_key)

        success = await self.coordinator.async_execute_command(
            self._device_key, "off"
        )

        if not success:
            _LOGGER.error("Failed to turn off %s", self._device_key)


class IPComDimmableLight(IPComLight):
    """Representation of an IPCom dimmable light.

    This entity extends IPComLight to add brightness control.
    """

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the dimmable light."""
        super().__init__(coordinator, entity_key, device_data)

        # Dimmable light supports brightness
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        info = super().device_info
        info["model"] = "IPCom Dimmer"
        return info

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light (0-255).

        The CLI JSON contract returns brightness as 0-100 for all modules.
        Module 6 (EXO DIM) values are already correct 0-100, and this scaling
        to Home Assistant's 0-255 range works correctly for all modules.
        """
        if not self.coordinator.data or "devices" not in self.coordinator.data:
            return None

        device_data = self.coordinator.data["devices"].get(self._entity_key)
        if not device_data:
            return None

        # Get brightness from CLI (0-100)
        cli_brightness = device_data.get("brightness")
        if cli_brightness is None:
            return None

        # Scale from 0-100 to 0-255 (Home Assistant standard)
        return int((cli_brightness / 100) * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally setting brightness."""
        # Check if brightness was specified
        if ATTR_BRIGHTNESS in kwargs:
            # Scale brightness from HA (0-255) to CLI (0-100)
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            cli_brightness = int((ha_brightness / 255) * 100)

            # Ensure minimum brightness of 1% when turning on
            if cli_brightness == 0:
                cli_brightness = 1

            _LOGGER.debug(
                "Setting %s brightness to %d%% (HA: %d)",
                self._device_key,
                cli_brightness,
                ha_brightness,
            )

            success = await self.coordinator.async_execute_command(
                self._device_key, "dim", cli_brightness
            )

            if not success:
                _LOGGER.error("Failed to set brightness for %s", self._device_key)
        else:
            # No brightness specified, just turn on
            await super().async_turn_on(**kwargs)
