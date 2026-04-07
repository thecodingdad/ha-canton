"""Button platform for Canton Smart Sound."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CantonHub
from .entity import CantonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton button entities."""
    hub: CantonHub = entry.runtime_data
    async_add_entities([CantonBluetoothPairButton(hub)])


class CantonBluetoothPairButton(CantonEntity, ButtonEntity):
    """Button to enter Bluetooth pairing mode."""

    _attr_name = "Bluetooth Pairing"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_bt_pair"

    async def async_press(self) -> None:
        if self._hub._tunnel:
            await self._hub._tunnel.async_send_fire(10, 1)
