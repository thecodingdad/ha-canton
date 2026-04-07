"""Sensor platform for Canton Smart Sound."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CantonHub
from .const import SIGNAL_STATE_UPDATED
from .entity import CantonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton sensor entities."""
    hub: CantonHub = entry.runtime_data
    async_add_entities([
        CantonPhysicalSourceSensor(hub),
        CantonDiagnosticSensor(hub, "ip_address", "IP Address", "mdi:ip-network", hub.host),
        CantonDiagnosticSensor(hub, "wifi_band", "WiFi Band", "mdi:wifi", hub.wifi_band),
    ])


class CantonPhysicalSourceSensor(CantonEntity, SensorEntity):
    """Shows the current physical source (e.g. OPT 1, HDMI TV)."""

    _attr_name = "Physical Source"
    _attr_icon = "mdi:audio-input-stereo-minijack"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_physical_source"

    @property
    def native_value(self) -> str | None:
        return self._hub.state.source_name or None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class CantonDiagnosticSensor(CantonEntity, SensorEntity):
    """Static diagnostic sensor from discovery/config data."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, hub: CantonHub, key: str, name: str, icon: str, value: str
    ) -> None:
        super().__init__(hub)
        self._value = value
        self._attr_unique_id = f"{hub.usn}_{key}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def native_value(self) -> str | None:
        return self._value or None
