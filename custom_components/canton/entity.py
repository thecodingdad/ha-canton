"""Base entity for Canton Smart Sound integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_CONNECTION_CHANGED

if TYPE_CHECKING:
    from . import CantonHub


class CantonEntity(Entity):
    """Base entity for Canton devices."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: CantonHub) -> None:
        self._hub = hub

    @property
    def device_info(self) -> DeviceInfo:
        # Format USN "CC9093120230" as MAC "CC:90:93:12:02:30"
        usn = self._hub.usn
        mac = ":".join(usn[i : i + 2] for i in range(0, len(usn), 2)) if len(usn) == 12 else None

        info = DeviceInfo(
            identifiers={(DOMAIN, usn)},
            name=self._hub.device_name,
            manufacturer="Canton",
            model=self._hub.model,
            sw_version=self._hub.firmware_version,
        )
        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        return info

    @property
    def available(self) -> bool:
        return self._hub.is_connected

    async def async_added_to_hass(self) -> None:
        signal = SIGNAL_CONNECTION_CHANGED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal, self._on_connection_changed
            )
        )

    @callback
    def _on_connection_changed(self, connected: bool) -> None:
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
