"""Switch platform for Canton Smart Sound menu settings."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CantonHub
from .const import (
    MENU_CEC,
    MENU_DRC,
    MENU_INPUT_STREAM_DISPLAY,
    MENU_LED_FLASHING,
    MENU_SLAVE_DISPLAY,
    MENU_TOUCH_PANEL,
    MENU_VOICE_CLARITY,
    SIGNAL_STATE_UPDATED,
)
from .entity import CantonEntity

# (setting_name, label, icon, inverted)
_SWITCH_DEFINITIONS = [
    (MENU_CEC, "HDMI CEC", "mdi:hdmi-port", False),
    (MENU_DRC, "Dynamic Range Compression", "mdi:tune-vertical", False),
    (MENU_VOICE_CLARITY, "Voice Clarity", "mdi:account-voice", False),
    (MENU_TOUCH_PANEL, "Touch Panel", "mdi:gesture-tap", True),
    (MENU_LED_FLASHING, "LED Flashing", "mdi:led-on", False),
    (MENU_INPUT_STREAM_DISPLAY, "Input Stream Display", "mdi:monitor", False),
    (MENU_SLAVE_DISPLAY, "Slave Speaker Display", "mdi:monitor-multiple", False),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton switch entities."""
    hub: CantonHub = entry.runtime_data
    entities: list = [CantonMuteSwitch(hub)]
    for name, label, icon, inverted in _SWITCH_DEFINITIONS:
        if hub.menu_id(name) is not None:
            entities.append(
                CantonMenuSwitch(hub, name, label, icon, inverted=inverted)
            )
    async_add_entities(entities)


class CantonMuteSwitch(CantonEntity, SwitchEntity):
    """Switch to mute/unmute the device."""

    _attr_name = "Mute"

    def __init__(self, hub: CantonHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.usn}_mute"

    @property
    def icon(self) -> str:
        return "mdi:volume-mute" if self.is_on else "mdi:volume-high"

    @property
    def is_on(self) -> bool:
        return self._hub.state.is_muted

    async def async_turn_on(self, **kwargs) -> None:
        await self._hub.async_set_mute(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._hub.async_set_mute(False)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class CantonMenuSwitch(CantonEntity, SwitchEntity):
    """Generic switch entity for Canton menu On/Off settings."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hub: CantonHub,
        setting_name: str,
        label: str,
        icon: str,
        inverted: bool = False,
    ) -> None:
        super().__init__(hub)
        self._setting_name = setting_name
        self._inverted = inverted
        self._attr_unique_id = f"{hub.usn}_{setting_name}"
        self._attr_name = label
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        val = self._hub.menu_value(self._setting_name)
        if val is None:
            return None
        # Most switches: 0=Off, 1=On
        # Touch Panel is inverted: 0=Enable, 1=Disable
        if self._inverted:
            return val == 0
        return val == 1

    async def async_turn_on(self, **kwargs) -> None:
        await self._hub.async_menu_set(
            self._setting_name, 0 if self._inverted else 1
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self._hub.async_menu_set(
            self._setting_name, 1 if self._inverted else 0
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = SIGNAL_STATE_UPDATED.format(mac=self._hub.usn)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()
