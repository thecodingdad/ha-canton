"""Select platform for Canton Smart Sound."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.translation import async_get_translations

from . import CantonHub
from .const import (
    DOMAIN,
    INPUT_SELECTION_OPTIONS,
    INPUT_SELECTION_REVERSE,
    MENU_INPUT_SELECTION,
    MENU_RF_CHANNEL,
    MENU_RF_POWER,
    MENU_SLEEP_TIMER,
    MENU_STANDBY_MODE,
    RF_CHANNEL_OPTIONS,
    RF_CHANNEL_REVERSE,
    RF_POWER_OPTIONS,
    RF_POWER_REVERSE,
    SIGNAL_STATE_UPDATED,
    SLEEP_TIMER_OPTIONS,
    SLEEP_TIMER_REVERSE,
    STANDBY_MODE_OPTIONS,
    STANDBY_MODE_REVERSE,
    TUNNEL_INPUT_NAMES,
    TUNNEL_PLAY_MODES,
)
from .entity import CantonEntity

# (setting_name, label, icon, options_map, reverse_map)
_SELECT_DEFINITIONS = [
    (MENU_SLEEP_TIMER, "Sleep Timer", "mdi:timer-sand", SLEEP_TIMER_OPTIONS, SLEEP_TIMER_REVERSE),
    (MENU_STANDBY_MODE, "Standby Mode", "mdi:power-sleep", STANDBY_MODE_OPTIONS, STANDBY_MODE_REVERSE),
    (MENU_INPUT_SELECTION, "Input Selection", "mdi:import", INPUT_SELECTION_OPTIONS, INPUT_SELECTION_REVERSE),
    (MENU_RF_POWER, "RF Power", "mdi:wifi-strength-4", RF_POWER_OPTIONS, RF_POWER_REVERSE),
    (MENU_RF_CHANNEL, "RF Channel", "mdi:wifi", RF_CHANNEL_OPTIONS, RF_CHANNEL_REVERSE),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton select entities."""
    hub: CantonHub = entry.runtime_data
    translations = await async_get_translations(
        hass, hass.config.language, "common", {DOMAIN}
    )
    active_suffix = translations.get(
        f"component.{DOMAIN}.common.preset_active_suffix", "(active)"
    )
    entities: list = [
        CantonInputSelect(hub),
        CantonPlayModeSelect(hub),
        CantonPresetSelect(hub, active_suffix),
    ]
    for name, label, icon, options, reverse in _SELECT_DEFINITIONS:
        if hub.menu_id(name) is not None:
            entities.append(
                CantonMenuSelect(hub, name, label, icon, options, reverse)
            )
    async_add_entities(entities)


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
        setting_name: str,
        label: str,
        icon: str,
        options_map: dict[int, str],
        reverse_map: dict[str, int],
    ) -> None:
        super().__init__(hub)
        self._setting_name = setting_name
        self._options_map = options_map
        self._reverse_map = reverse_map
        self._attr_unique_id = f"{hub.usn}_{setting_name}"
        self._attr_name = label
        self._attr_icon = icon
        self._attr_options = list(options_map.values())

    @property
    def current_option(self) -> str | None:
        val = self._hub.menu_value(self._setting_name)
        if val is not None:
            return self._options_map.get(val)
        return None

    async def async_select_option(self, option: str) -> None:
        val = self._reverse_map.get(option)
        if val is not None:
            await self._hub.async_menu_set(self._setting_name, val)

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

    def __init__(self, hub: CantonHub, active_suffix: str) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_preset"
        self._active_suffix = active_suffix

    @property
    def _active_label(self) -> str | None:
        n = self._hub.state.active_preset
        return f"Preset {n} {self._active_suffix}" if n > 0 else None

    @property
    def options(self) -> list[str]:
        base = [
            f"Preset {i}" for i in self._hub.state.configured_presets
        ] or ["Preset 1"]
        label = self._active_label
        return [label, *base] if label else base

    @property
    def current_option(self) -> str | None:
        return self._active_label

    async def async_select_option(self, option: str) -> None:
        if option.endswith(self._active_suffix):
            return
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
