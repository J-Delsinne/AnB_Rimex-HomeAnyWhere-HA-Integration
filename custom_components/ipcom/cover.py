"""Cover platform for IPCom integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
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
    """Set up IPCom covers from config entry."""
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    covers_added = set()

    for entity_key, device_data in coordinator.data["devices"].items():
        category = device_data.get("category")
        if category == "shutters":
            relay_role = device_data.get("relay_role")
            device_key = device_data.get("device_key")

            # Only create cover for "up" relay (to avoid duplicates)
            if relay_role == "up" and device_key not in covers_added:
                entities.append(IPComCover(coordinator, entity_key, device_data))
                covers_added.add(device_key)

    async_add_entities(entities)


class IPComCover(CoordinatorEntity[IPComCoordinator], CoverEntity):
    """Representation of an IPCom cover (shutter)."""

    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP

    def __init__(
        self,
        coordinator: IPComCoordinator,
        entity_key: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._entity_key = entity_key
        self._device_key = device_data["device_key"]
        self._attr_unique_id = f"ipcom_{self._device_key}"
        self._attr_name = device_data.get("display_name", self._device_key.upper())

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
            "model": "IPCom Shutter",
            "sw_version": f"Module {self._module}",
        }

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        # For now, we don't have position feedback
        # Return None to indicate unknown state
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.async_execute_command(self._device_key, "cover_open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.async_execute_command(self._device_key, "cover_close")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.coordinator.async_execute_command(self._device_key, "cover_stop")
