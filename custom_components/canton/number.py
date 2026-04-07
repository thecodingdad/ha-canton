"""Number platform for Canton Smart Sound EQ control."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CantonHub
from .const import MENU_MAX_VOLUME, MENU_SUBWOOFER_LEVEL, SIGNAL_STATE_UPDATED
from .entity import CantonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton EQ number entities."""
    hub: CantonHub = entry.runtime_data
    async_add_entities([
        CantonVolumeNumber(hub),
        CantonEQNumber(hub, "bass", "EQ Bass"),
        CantonEQNumber(hub, "mid", "EQ Mid"),
        CantonEQNumber(hub, "treble", "EQ Treble"),
        CantonMenuNumber(hub, "max_volume", "Max Volume", "mdi:volume-off", MENU_MAX_VOLUME, 0, 70, ""),
        CantonMenuNumber(hub, "subwoofer_level", "Subwoofer Level", "mdi:speaker", MENU_SUBWOOFER_LEVEL, -10, 10, "dB"),
    ])


class CantonVolumeNumber(CantonEntity, NumberEntity):
    """Volume as a number entity showing the device's native 0-max range."""

    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:volume-high"
    _attr_name = "Volume"
    _attr_translation_key = "volume"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_volume"

    @property
    def native_max_value(self) -> float:
        return self._hub.state.volume_max

    @property
    def native_value(self) -> float:
        return self._hub.state.volume

    async def async_set_native_value(self, value: float) -> None:
        await self._hub.async_set_volume(int(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal, self._on_state_updated
            )
        )

    @callback
    def _on_state_updated(self) -> None:
        self.async_write_ha_state()


class CantonMenuNumber(CantonEntity, NumberEntity):
    """Generic number entity for Canton menu INT_8 settings."""

    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        hub: CantonHub,
        key: str,
        name: str,
        icon: str,
        menu_id: int,
        min_val: int,
        max_val: int,
        unit: str,
    ) -> None:
        super().__init__(hub)
        self._menu_id = menu_id
        self._attr_unique_id = f"{hub.usn}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_unit_of_measurement = unit or None

    @property
    def native_value(self) -> float | None:
        val = self._hub.state.menu_values.get(self._menu_id)
        return val if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self._hub.async_menu_set(self._menu_id, int(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal, self._on_state_updated
            )
        )

    @callback
    def _on_state_updated(self) -> None:
        self.async_write_ha_state()


class CantonEQNumber(CantonEntity, NumberEntity):
    """Representation of a Canton EQ slider."""

    _attr_native_min_value = -10
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "dB"

    def __init__(self, hub: CantonHub, eq_type: str, name: str) -> None:
        super().__init__(hub)
        self._eq_type = eq_type
        self._attr_translation_key = f"eq_{eq_type}"
        self._attr_unique_id = f"{hub.usn}_eq_{eq_type}"
        self._attr_name = name

    @property
    def native_value(self) -> float:
        if self._eq_type == "bass":
            return self._hub.state.eq_bass
        if self._eq_type == "mid":
            return self._hub.state.eq_mid
        return self._hub.state.eq_treble

    async def async_set_native_value(self, value: float) -> None:
        val = int(value)
        if self._eq_type == "bass":
            await self._hub.async_set_eq(bass=val)
        elif self._eq_type == "mid":
            await self._hub.async_set_eq(mid=val)
        else:
            await self._hub.async_set_eq(treble=val)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal, self._on_state_updated
            )
        )

    @callback
    def _on_state_updated(self) -> None:
        self.async_write_ha_state()
