"""Select platform for Canton Smart Sound."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CantonHub
from .const import (
    MENU_SLEEP_TIMER,
    MENU_STANDBY_MODE,
    SIGNAL_STATE_UPDATED,
    SLEEP_TIMER_OPTIONS,
    SLEEP_TIMER_REVERSE,
    STANDBY_MODE_OPTIONS,
    STANDBY_MODE_REVERSE,
    TUNNEL_INPUT_NAMES,
    TUNNEL_PLAY_MODES,
)
from .entity import CantonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton select entities."""
    hub: CantonHub = entry.runtime_data
    async_add_entities([
        CantonInputSelect(hub),
        CantonPlayModeSelect(hub),
        CantonPresetSelect(hub),
        CantonMenuSelect(hub, "sleep_timer", "Sleep Timer", "mdi:timer-sand", MENU_SLEEP_TIMER, SLEEP_TIMER_OPTIONS, SLEEP_TIMER_REVERSE),
        CantonMenuSelect(hub, "standby_mode", "Standby Mode", "mdi:power-sleep", MENU_STANDBY_MODE, STANDBY_MODE_OPTIONS, STANDBY_MODE_REVERSE),
    ])


class CantonInputSelect(CantonEntity, SelectEntity):
    """Representation of Canton input source selector."""

    _attr_translation_key = "input_source"
    _attr_name = "Input"
    _attr_icon = "mdi:import"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_input"
        self._attr_options = list(TUNNEL_INPUT_NAMES.values())

    @property
    def current_option(self) -> str | None:
        return self._hub.state.input_name or None

    async def async_select_option(self, option: str) -> None:
        await self._hub.async_set_input(option)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class CantonPlayModeSelect(CantonEntity, SelectEntity):
    """Representation of Canton play mode selector."""

    _attr_translation_key = "play_mode"
    _attr_name = "Play Mode"
    _attr_icon = "mdi:surround-sound"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_play_mode"
        self._attr_options = list(dict.fromkeys(TUNNEL_PLAY_MODES.values()))

    @property
    def current_option(self) -> str | None:
        return self._hub.state.play_mode or None

    async def async_select_option(self, option: str) -> None:
        await self._hub.async_set_play_mode(option)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class CantonMenuSelect(CantonEntity, SelectEntity):
    """Generic select entity for Canton menu ENUM settings."""

    def __init__(
        self,
        hub: CantonHub,
        key: str,
        name: str,
        icon: str,
        menu_id: int,
        options_map: dict[int, str],
        reverse_map: dict[str, int],
    ) -> None:
        super().__init__(hub)
        self._menu_id = menu_id
        self._options_map = options_map
        self._reverse_map = reverse_map
        self._attr_unique_id = f"{hub.usn}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = list(options_map.values())

    @property
    def current_option(self) -> str | None:
        val = self._hub.state.menu_values.get(self._menu_id)
        if val is not None:
            return self._options_map.get(val)
        return None

    async def async_select_option(self, option: str) -> None:
        val = self._reverse_map.get(option)
        if val is not None:
            await self._hub.async_menu_set(self._menu_id, val)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class CantonPresetSelect(CantonEntity, SelectEntity):
    """Representation of Canton preset selector."""

    _attr_translation_key = "preset"
    _attr_name = "Preset"
    _attr_icon = "mdi:playlist-star"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_preset"

    @property
    def options(self) -> list[str]:
        return [
            f"Preset {i}" for i in self._hub.state.configured_presets
        ] if self._hub.state.configured_presets else ["Preset 1"]

    @property
    def current_option(self) -> str | None:
        if self._hub.state.active_preset > 0:
            return f"Preset {self._hub.state.active_preset}"
        return None

    async def async_select_option(self, option: str) -> None:
        try:
            preset = int(option.split()[-1])
        except (ValueError, IndexError):
            return
        await self._hub.async_recall_preset(preset)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()
