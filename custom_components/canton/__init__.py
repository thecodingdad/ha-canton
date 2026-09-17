"""Canton Smart Sound integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    CMD_GET,
    CMD_SET,
    CONF_FW_VERSION,
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_TUNNEL_PORT,
    DEFAULT_TUNNEL_PORT,
    DOMAIN,
    MENU_EXIT_COUNT,
    MENU_EXIT_COUNT_DEFAULT,
    MENU_IDS_BY_MODEL,
    MID_TUNNELING_START,
    MID_VOLUME,
    PLATFORMS,
    SIGNAL_CONNECTION_CHANGED,
    SIGNAL_STATE_UPDATED,
    TCMD_EQ_GET,
    TCMD_EQ_SET,
    TCMD_MENU_EXIT,
    TCMD_MENU_GET,
    TCMD_MENU_SET,
    TCMD_MUTE_GET,
    TCMD_MUTE_SET,
    TCMD_PRESET_GET,
    TCMD_PRESET_RECALL,
    TCMD_SOURCE_GET,
    TCMD_SOURCE_INFO_GET,
    TCMD_SOURCE_SET,
    TCMD_STANDBY_GET,
    TCMD_STANDBY_SET,
    TCMD_VOLUME_GET,
    TCMD_VOLUME_SET,
    TUNNEL_INPUT_NAMES,
    TUNNEL_PHYSICAL_SOURCES,
    TUNNEL_PLAY_MODES,
)
from .protocol import LuciMessage, LuciProtocol, TunnelProtocol
from .tunnel_manager import TunnelManager, TunnelMode

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_presets"

type CantonConfigEntry = ConfigEntry[CantonHub]


@dataclass
class PresetData:
    """Stored settings for a single preset."""

    source_id: int
    input_name_id: int
    play_mode_id: int
    volume: int
    eq_treble: int
    eq_mid: int
    eq_bass: int

    def to_dict(self) -> dict[str, int]:
        return {
            "source_id": self.source_id,
            "input_name_id": self.input_name_id,
            "play_mode_id": self.play_mode_id,
            "volume": self.volume,
            "eq_treble": self.eq_treble,
            "eq_mid": self.eq_mid,
            "eq_bass": self.eq_bass,
        }

    @staticmethod
    def from_dict(data: dict[str, int]) -> PresetData:
        return PresetData(
            source_id=data["source_id"],
            input_name_id=data["input_name_id"],
            play_mode_id=data["play_mode_id"],
            volume=data["volume"],
            eq_treble=data["eq_treble"],
            eq_mid=data["eq_mid"],
            eq_bass=data["eq_bass"],
        )


@dataclass
class CantonState:
    """Current state of a Canton device."""

    power_on: bool = True
    volume: int = 0
    volume_max: int = 70
    is_muted: bool = False
    play_status: int | None = None  # LUCI play status for NET/BT
    media_title: str | None = None
    media_artist: str | None = None
    media_album: str | None = None
    media_image_url: str | None = None
    media_duration: int | None = None
    media_position: int | None = None
    shuffle: bool = False
    repeat: int = 0  # 0=Off, 1=One, 2=All
    input_name_id: int = 0
    input_name: str = ""
    source_id: int = 0
    source_name: str = ""
    play_mode_id: int = 1
    play_mode: str = "Stereo"
    eq_treble: int = 0
    eq_mid: int = 0
    eq_bass: int = 0
    eq_range: int = 10
    input_map: dict[int, tuple[int, int]] = field(default_factory=dict)
    # Menu settings
    menu_values: dict[int, int] = field(default_factory=dict)
    # Preset tracking
    active_preset: int = 0
    configured_presets: list[int] = field(default_factory=list)
    preset_data: dict[int, PresetData] = field(default_factory=dict)


class CantonHub:
    """Manages communication with a Canton device via LUCI + Tunnel."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        tunnel_port: int,
        usn: str,
        device_name: str,
        model: str,
        firmware_version: str,
        wifi_band: str = "",
    ) -> None:
        self.hass = hass
        self._luci = LuciProtocol(host, port)
        self._tunnel: TunnelManager | None = None
        self._tunnel_port = tunnel_port
        self.usn = usn
        self.host = host
        self.device_name = device_name
        self.model = model
        self.firmware_version = firmware_version
        self.wifi_band = wifi_band
        self.state = CantonState()
        self._teardown = False
        self._reconnect_task: asyncio.Task | None = None
        self._cast = None  # Lazy-initialized pychromecast device
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{usn}"
        )

    @property
    def is_connected(self) -> bool:
        """Return True if the device is usable.

        In shared mode no permanent tunnel connection exists, so the device counts
        as connected while LUCI is up and the last tunnel session succeeded.
        """
        return (
            self._luci.is_connected
            and self._tunnel is not None
            and self._tunnel.available
        )

    @property
    def tunnel_mode(self) -> TunnelMode:
        """Return whether the tunnel is held exclusively or shared."""
        return self._tunnel.mode if self._tunnel else TunnelMode.EXCLUSIVE

    @property
    def input_list(self) -> list[str]:
        """Return the inputs as configured on the device.

        Every physical input carries a name assigned under
        "System Setup -> Input Setup -> Input Name", reported by SOURCE_INFO.
        Inputs left unnamed ("---") are skipped. Falls back to all selectable names
        while the mapping is unknown.
        """
        from .const import INPUT_NAME_UNASSIGNED, SELECTABLE_INPUT_NAMES

        names = [
            TUNNEL_INPUT_NAMES[name_id]
            # Sort by physical source so the order matches the device
            for name_id, (source_id, _) in sorted(
                self.state.input_map.items(), key=lambda item: item[1][0]
            )
            if name_id != INPUT_NAME_UNASSIGNED and name_id in TUNNEL_INPUT_NAMES
        ]
        return names or SELECTABLE_INPUT_NAMES

    async def async_setup(self) -> None:
        """Set up the connection to the device."""
        self._luci.on_message = self._on_luci_message
        self._luci.on_connection_change = self._on_connection_change

        if not await self._luci.async_connect():
            raise ConfigEntryNotReady(
                f"Cannot connect to Canton device at {self._luci.host}"
            )

        # Tunnel access is managed adaptively: held permanently while free, shared
        # through short sessions when another controller uses it.
        self._tunnel = TunnelManager(
            host=self._luci.host,
            port=self._tunnel_port,
            luci=self._luci,
            on_message=self._on_tunnel_message,
            poll=self._async_poll_state,
            log_id=self.device_name or self.host,
            loop=self.hass.loop,
        )
        await self._tunnel.start()

        # Load stored presets
        await self._load_presets()

        await self._fetch_initial_state()

        if not self._tunnel.available:
            await self._tunnel.stop()
            await self._luci.async_disconnect()
            raise ConfigEntryNotReady(
                f"Cannot reach Canton tunnel at {self._luci.host}:{self._tunnel_port}"
            )

        # Capture current state for the active preset
        if self.state.active_preset > 0:
            self._capture_preset(self.state.active_preset)
            await self._save_presets()

    async def async_teardown(self) -> None:
        """Disconnect from the device."""
        self._teardown = True
        await self._async_cancel_reconnect()
        if self._tunnel:
            await self._tunnel.stop()
            self._tunnel = None
        await self._luci.async_disconnect()
        await self.async_cast_disconnect()

    @asynccontextmanager
    async def _tunnel_session(self) -> AsyncIterator[TunnelProtocol | None]:
        """Provide a connected tunnel, or None if there is none."""
        if self._tunnel is None:
            yield None
            return
        async with self._tunnel.session() as session:
            yield session

    async def _async_poll_state(self) -> None:
        """Read the volatile device state in one short session (shared mode)."""
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            resp = await tunnel.async_send(*TCMD_STANDBY_GET)
            if resp is not None and len(resp) >= 1:
                self.state.power_on = resp[0] == 1
            resp = await tunnel.async_send(*TCMD_SOURCE_GET)
            if resp is not None and len(resp) >= 3:
                self._parse_source(resp)
            resp = await tunnel.async_send(*TCMD_VOLUME_GET)
            if resp is not None and len(resp) >= 1:
                self._parse_volume(resp)
            resp = await tunnel.async_send(*TCMD_MUTE_GET)
            if resp is not None and len(resp) >= 1:
                self.state.is_muted = resp[0] == 1
            resp = await tunnel.async_send(*TCMD_EQ_GET)
            if resp is not None and len(resp) >= 3:
                self._parse_eq(resp)

        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def _load_presets(self) -> None:
        """Load preset data from persistent storage."""
        data = await self._store.async_load()
        if data and "presets" in data:
            for key, val in data["presets"].items():
                try:
                    self.state.preset_data[int(key)] = PresetData.from_dict(val)
                except (KeyError, ValueError):
                    pass

    async def _save_presets(self) -> None:
        """Save preset data to persistent storage."""
        data = {
            "presets": {
                str(k): v.to_dict() for k, v in self.state.preset_data.items()
            }
        }
        await self._store.async_save(data)

    def _capture_preset(self, preset: int) -> None:
        """Capture current device state as preset data."""
        self.state.preset_data[preset] = PresetData(
            source_id=self.state.source_id,
            input_name_id=self.state.input_name_id,
            play_mode_id=self.state.play_mode_id,
            volume=self.state.volume,
            eq_treble=self.state.eq_treble,
            eq_mid=self.state.eq_mid,
            eq_bass=self.state.eq_bass,
        )

    async def _fetch_initial_state(self) -> None:
        """Fetch the full device state, including menu settings, in one session."""
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return

            # Query standby state (1=on, 0=standby)
            resp = await tunnel.async_send(*TCMD_STANDBY_GET)
            if resp is not None and len(resp) >= 1:
                self.state.power_on = resp[0] == 1

            # Query input mapping (SOURCE_INFO)
            resp = await tunnel.async_send(*TCMD_SOURCE_INFO_GET)
            if resp is not None and len(resp) >= 3:
                for i in range(0, len(resp) - 2, 3):
                    src_id, name_id, mode_id = resp[i], resp[i + 1], resp[i + 2]
                    self.state.input_map[name_id] = (src_id, mode_id)

            # Query presets
            resp = await tunnel.async_send(*TCMD_PRESET_GET)
            if resp is not None and len(resp) >= 11:
                self.state.active_preset = resp[0]
                self.state.configured_presets = [
                    i + 1 for i in range(10) if resp[i + 1] == 2
                ]

            # Query source/playmode
            resp = await tunnel.async_send(*TCMD_SOURCE_GET)
            if resp is not None and len(resp) >= 3:
                self._parse_source(resp)

            # Query EQ
            resp = await tunnel.async_send(*TCMD_EQ_GET)
            if resp is not None and len(resp) >= 3:
                self._parse_eq(resp)

            # Query volume
            resp = await tunnel.async_send(*TCMD_VOLUME_GET)
            if resp is not None and len(resp) >= 1:
                self._parse_volume(resp)

            # Query mute
            resp = await tunnel.async_send(*TCMD_MUTE_GET)
            if resp is not None and len(resp) >= 1:
                self.state.is_muted = resp[0] == 1

            # Query all menu settings supported by this model
            for name in MENU_IDS_BY_MODEL:
                menu_id = self.menu_id(name)
                if menu_id is None:
                    continue
                val = await self._async_menu_get_by_id(tunnel, menu_id)
                if val is not None:
                    self.state.menu_values[menu_id] = val

    def _parse_source(self, payload: bytes) -> None:
        """Parse SOURCE_PLAY_MODE response: [sourceId, nameId, playModeId]."""
        self.state.source_id = payload[0]
        self.state.input_name_id = payload[1]
        self.state.play_mode_id = payload[2]
        self.state.source_name = TUNNEL_PHYSICAL_SOURCES.get(
            payload[0], f"Source {payload[0]}"
        )
        self.state.input_name = TUNNEL_INPUT_NAMES.get(
            payload[1], f"Input {payload[1]}"
        )
        self.state.play_mode = TUNNEL_PLAY_MODES.get(
            payload[2], f"Mode {payload[2]}"
        )
        # NET/BT use LUCI volume (0-100), other inputs use tunnel volume (0-70)
        if self.state.input_name in ("NET", "BT"):
            self.state.volume_max = 100
            self.hass.async_create_task(self._refresh_luci_state())
        else:
            self.state.volume_max = 70
            self.state.play_status = None
            self.state.media_title = None
            self.state.media_artist = None
            self.state.media_album = None
            self.state.media_image_url = None
            self.state.media_duration = None
            self.state.media_position = None
            self.state.shuffle = False
            self.state.repeat = 0

    async def _refresh_luci_state(self) -> None:
        """Refresh volume, play status, and metadata from LUCI (for NET/BT)."""
        from .const import MID_GET_UI

        resp = await self._luci.async_send(MID_VOLUME, CMD_GET)
        if resp and resp.payload:
            try:
                self.state.volume = int(resp.payload)
            except ValueError:
                pass

        resp = await self._luci.async_send(MID_GET_UI, CMD_GET)
        if resp and resp.payload:
            self._parse_media_metadata(resp.payload)

        async_dispatcher_send(
            self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn)
        )

    def _parse_eq(self, payload: bytes) -> None:
        """Parse EQ response: [treble, mid, bass, range]."""
        self.state.eq_treble = payload[0] if payload[0] < 128 else payload[0] - 256
        self.state.eq_mid = payload[1] if payload[1] < 128 else payload[1] - 256
        self.state.eq_bass = payload[2] if payload[2] < 128 else payload[2] - 256
        if len(payload) >= 4:
            self.state.eq_range = payload[3]

    def _parse_volume(self, payload: bytes) -> None:
        """Parse VOLUME response: [volume, max_volume]."""
        self.state.volume = payload[0]
        if len(payload) >= 2:
            self.state.volume_max = payload[1]

    @callback
    def _on_luci_message(self, msg: LuciMessage) -> None:
        """Handle LUCI push messages (volume/playback/metadata for NET/BT)."""
        import json

        from .const import MID_CURRENT_PLAY_STATUS, MID_GET_UI, MID_PLAY_ELAPSED

        changed = False
        if msg.mid == MID_VOLUME and self._is_network_source():
            try:
                self.state.volume = int(msg.payload)
                changed = True
            except ValueError:
                pass
        elif msg.mid == MID_CURRENT_PLAY_STATUS:
            try:
                self.state.play_status = int(msg.payload)
                changed = True
            except ValueError:
                pass
        elif msg.mid == MID_PLAY_ELAPSED:
            try:
                elapsed = int(msg.payload)
                if elapsed >= 0:
                    self.state.media_position = elapsed
                    changed = True
            except ValueError:
                pass
        elif msg.mid == MID_GET_UI and msg.payload:
            self._parse_media_metadata(msg.payload)
            changed = True

        if changed:
            async_dispatcher_send(
                self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn)
            )

    def _parse_media_metadata(self, payload: str) -> None:
        """Parse GetUI JSON for media metadata."""
        import json

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return

        contents = data.get("Window CONTENTS", {})
        if not contents:
            return

        title = contents.get("TrackName", "")
        self.state.media_title = title if title and title != "null" else None

        artist = contents.get("Artist", "")
        self.state.media_artist = artist if artist and artist != "null" else None

        album = contents.get("Album", "")
        self.state.media_album = album if album and album != "null" else None

        cover = contents.get("CoverArtUrl", "")
        if cover and cover != "null":
            if cover == "coverart.jpg":
                cover = f"http://{self.host}/{cover}"
            self.state.media_image_url = cover
        else:
            self.state.media_image_url = None

        play_state = contents.get("PlayState")
        if play_state is not None:
            self.state.play_status = int(play_state)

        total = contents.get("TotalTime")
        self.state.media_duration = int(total) if total and int(total) > 0 else None

        current = contents.get("Current_time")
        self.state.media_position = int(current) if current and int(current) >= 0 else None

        self.state.shuffle = bool(contents.get("Shuffle", 0))
        self.state.repeat = int(contents.get("Repeat", 0))

    @callback
    def _on_tunnel_message(self, cmd: tuple[int, int], payload: bytes) -> None:
        """Handle incoming tunnel push messages."""
        changed = False

        if cmd == TCMD_SOURCE_SET and len(payload) >= 3:
            self._parse_source(payload)
            changed = True
        elif cmd == TCMD_EQ_SET and len(payload) >= 3:
            self._parse_eq(payload)
            changed = True
        elif cmd == TCMD_STANDBY_SET and len(payload) >= 1:
            self.state.power_on = payload[0] == 1
            changed = True
        elif cmd == TCMD_PRESET_RECALL and len(payload) >= 2:
            # Preset notification from hardware button: [preset, 1] = recall
            preset_num = payload[0]
            if payload[1] == 1 and preset_num > 0:
                self.state.active_preset = preset_num
                self.hass.async_create_task(
                    self._delayed_preset_capture(preset_num)
                )
            changed = True
        elif cmd == TCMD_MENU_SET and len(payload) >= 5:
            menu_id = int.from_bytes(payload[:4], "big")
            value = payload[4] if payload[4] < 128 else payload[4] - 256
            self.state.menu_values[menu_id] = value
            changed = True
        elif cmd == TCMD_MUTE_SET and len(payload) >= 1:
            self.state.is_muted = payload[0] == 1
            changed = True
        elif cmd == TCMD_VOLUME_SET and len(payload) >= 1:
            self._parse_volume(payload)
            changed = True

        if changed:
            async_dispatcher_send(
                self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn)
            )

    async def _delayed_preset_capture(self, preset: int) -> None:
        """Capture preset state after the device has applied it."""
        await asyncio.sleep(1)
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            # Re-read current state
            resp = await tunnel.async_send(*TCMD_SOURCE_GET)
            if resp and len(resp) >= 3:
                self._parse_source(resp)
            resp = await tunnel.async_send(*TCMD_EQ_GET)
            if resp and len(resp) >= 3:
                self._parse_eq(resp)
            resp = await tunnel.async_send(*TCMD_VOLUME_GET)
            if resp and len(resp) >= 1:
                self._parse_volume(resp)

        self._capture_preset(preset)
        await self._save_presets()
        _LOGGER.debug("Captured preset %s: %s", preset, self.state.preset_data[preset])
        async_dispatcher_send(
            self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn)
        )

    def _on_connection_change(self, connected: bool) -> None:
        """Handle connection state changes (may be called from any thread)."""
        self.hass.loop.call_soon_threadsafe(
            self._handle_connection_change_in_loop, connected
        )

    @callback
    def _handle_connection_change_in_loop(self, connected: bool) -> None:
        async_dispatcher_send(
            self.hass,
            SIGNAL_CONNECTION_CHANGED.format(mac=self.usn),
            connected,
        )
        if not connected and not self._teardown:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule an automatic reconnect attempt."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = self.hass.async_create_task(
            self._auto_reconnect()
        )

    def _cancel_reconnect(self) -> None:
        """Cancel any pending reconnect (fire and forget)."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None

    async def _async_cancel_reconnect(self) -> None:
        """Cancel any pending reconnect and wait for it to finish."""
        task = self._reconnect_task
        self._reconnect_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _auto_reconnect(self) -> None:
        """Automatically reconnect with backoff."""
        delays = [10, 30, 60]
        for delay in delays:
            if self._teardown:
                return
            _LOGGER.debug("Auto-reconnect to %s in %s seconds", self.host, delay)
            await asyncio.sleep(delay)
            if self._teardown:
                return
            if await self._try_reconnect():
                return

        # Keep trying at max interval
        while not self._teardown:
            _LOGGER.debug("Auto-reconnect to %s in 60 seconds", self.host)
            await asyncio.sleep(60)
            if self._teardown:
                return
            if await self._try_reconnect():
                return

    async def _try_reconnect(self) -> bool:
        """Attempt a single reconnect cycle."""
        try:
            if self._teardown:
                return False

            if not self._luci.is_connected:
                if not await self._luci.async_connect():
                    return False

            if self._teardown:
                await self._luci.async_disconnect()
                return False

            self._tunnel = TunnelManager(
                host=self._luci.host,
                port=self._tunnel_port,
                luci=self._luci,
                on_message=self._on_tunnel_message,
                poll=self._async_poll_state,
                log_id=self.device_name or self.host,
                loop=self.hass.loop,
            )
            await self._tunnel.start()

            if self._teardown:
                await self._tunnel.stop()
                await self._luci.async_disconnect()
                return False

            await self._fetch_initial_state()
            if not self._tunnel.available:
                await self._tunnel.stop()
                return False
            _LOGGER.info("Reconnected to %s", self.host)
            async_dispatcher_send(
                self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn)
            )
            return True
        except asyncio.CancelledError:
            # Cleanup on cancellation
            if self._tunnel is not None:
                try:
                    await self._tunnel.stop()
                except Exception:
                    pass
            if self._luci.is_connected:
                try:
                    await self._luci.async_disconnect()
                except Exception:
                    pass
            raise
        except Exception:
            _LOGGER.debug("Reconnect attempt to %s failed", self.host, exc_info=True)
            return False

    # --- Menu methods ---

    def menu_id(self, name: str) -> int | None:
        """Return the menu ID for a setting name on this device model.

        Returns None if the setting is not supported on this model.
        """
        return MENU_IDS_BY_MODEL.get(name, {}).get(self.model)

    def menu_value(self, name: str) -> int | None:
        """Return the cached menu value for a setting name."""
        menu_id = self.menu_id(name)
        if menu_id is None:
            return None
        return self.state.menu_values.get(menu_id)

    @staticmethod
    async def _async_menu_get_by_id(
        tunnel: TunnelProtocol, menu_id: int
    ) -> int | None:
        """Low-level: get a menu value by raw ID on an open tunnel session."""
        resp = await tunnel.async_send(*TCMD_MENU_GET, menu_id.to_bytes(4, "big"))
        if resp and len(resp) >= 5:
            val = resp[4]
            return val if val < 128 else val - 256
        return None

    async def async_menu_set(self, name: str, value: int) -> None:
        """Set a menu value by setting name."""
        menu_id = self.menu_id(name)
        if menu_id is None:
            return

        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(
                *TCMD_MENU_SET, menu_id.to_bytes(4, "big") + bytes([value & 0xFF])
            )
            # Close OSD menu on the device display. The device auto-navigates
            # into the menu hierarchy when MENU_SET is sent, so one EXIT only
            # goes up one level — we need to send one EXIT per nesting level
            # plus one to fully close the OSD. The device needs ~200ms between
            # OSD commands to process them correctly.
            exit_count = MENU_EXIT_COUNT.get(name, MENU_EXIT_COUNT_DEFAULT)
            for _ in range(exit_count):
                await asyncio.sleep(0.2)
                await tunnel.async_send_fire(*TCMD_MENU_EXIT)
            # Short sessions get no push notification — remember what we set
            self.state.menu_values[menu_id] = value

        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    # --- Command methods ---

    def _is_network_source(self) -> bool:
        """Check if current input is NET or BT (uses LUCI for volume)."""
        return self.state.input_name in ("NET", "BT")

    async def async_play_control(self, command: str) -> None:
        """Send playback control via LUCI (for NET/BT sources)."""
        from .const import MID_PLAY_CONTROL
        await self._luci.async_send_fire(MID_PLAY_CONTROL, CMD_SET, command)

    async def async_set_volume(self, volume: int) -> None:
        if self._is_network_source():
            await self._luci.async_send_fire(MID_VOLUME, CMD_SET, str(volume))
            self.state.volume = volume
        else:
            async with self._tunnel_session() as tunnel:
                if tunnel is None:
                    return
                await tunnel.async_send_fire(*TCMD_VOLUME_SET, bytes([volume]))
                self.state.volume = volume
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def async_set_mute(self, mute: bool) -> None:
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(*TCMD_MUTE_SET, bytes([1 if mute else 0]))
            self.state.is_muted = mute
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def async_set_power(self, on: bool) -> None:
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(*TCMD_STANDBY_SET, bytes([1 if on else 0]))
            self.state.power_on = on
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def async_set_input(self, input_name: str) -> None:
        """Set input by name (e.g., 'CD', 'TV', 'AUX')."""
        from .const import TUNNEL_INPUT_NAMES_REVERSE

        name_id = TUNNEL_INPUT_NAMES_REVERSE.get(input_name)
        if name_id is None:
            return
        mapping = self.state.input_map.get(name_id)
        if mapping:
            source_id = mapping[0]
        else:
            _LOGGER.warning(
                "No source mapping for input %s (nameId=%s)", input_name, name_id
            )
            return

        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(
                *TCMD_SOURCE_SET,
                bytes([source_id, name_id, self.state.play_mode_id]),
            )
            await self._async_read_source(tunnel)
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def _async_read_source(self, tunnel: TunnelProtocol) -> None:
        """Re-read source and volume after a change, for sessions without push."""
        await asyncio.sleep(0.3)
        resp = await tunnel.async_send(*TCMD_SOURCE_GET)
        if resp and len(resp) >= 3:
            self._parse_source(resp)
        resp = await tunnel.async_send(*TCMD_VOLUME_GET)
        if resp and len(resp) >= 1:
            self._parse_volume(resp)

    async def async_set_play_mode(self, mode: str) -> None:
        """Set play mode (e.g., 'Stereo', 'Movie', 'Music')."""
        from .const import TUNNEL_PLAY_MODES_REVERSE

        mode_id = TUNNEL_PLAY_MODES_REVERSE.get(mode)
        if mode_id is None:
            return
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(
                *TCMD_SOURCE_SET,
                bytes([self.state.source_id, self.state.input_name_id, mode_id]),
            )
            await self._async_read_source(tunnel)
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def async_recall_preset(self, preset: int) -> None:
        """Recall a preset by sending the recall command to the device."""
        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(*TCMD_PRESET_RECALL, bytes([preset, 1]))

        self.state.active_preset = preset
        async_dispatcher_send(
            self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn)
        )
        self.hass.async_create_task(self._delayed_preset_capture(preset))

    async def async_set_eq(
        self,
        treble: int | None = None,
        mid: int | None = None,
        bass: int | None = None,
    ) -> None:
        """Set EQ values (-10 to +10 dB)."""
        t = treble if treble is not None else self.state.eq_treble
        m = mid if mid is not None else self.state.eq_mid
        b = bass if bass is not None else self.state.eq_bass

        async with self._tunnel_session() as tunnel:
            if tunnel is None:
                return
            await tunnel.async_send_fire(
                *TCMD_EQ_SET,
                bytes([t & 0xFF, m & 0xFF, b & 0xFF, self.state.eq_range]),
            )
            self.state.eq_treble, self.state.eq_mid, self.state.eq_bass = t, m, b
        async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATED.format(mac=self.usn))

    async def async_bluetooth_pair(self) -> None:
        """Put the device into Bluetooth pairing mode."""
        from .const import TCMD_BT_PAIR

        async with self._tunnel_session() as tunnel:
            if tunnel is not None:
                await tunnel.async_send_fire(*TCMD_BT_PAIR)

    # --- Chromecast (built-in) ---

    async def _ensure_cast(self):
        """Lazy-initialize the pychromecast device."""
        if self._cast is not None:
            return self._cast

        try:
            cast = await self.hass.async_add_executor_job(self._connect_cast)
            self._cast = cast
            return cast
        except Exception as err:
            _LOGGER.warning("Failed to connect to Chromecast on %s: %s", self.host, err)
            return None

    def _connect_cast(self):
        """Blocking pychromecast connection (run in executor)."""
        import pychromecast

        chromecasts, browser = pychromecast.get_chromecasts(
            known_hosts=[self.host], timeout=5
        )
        try:
            for cc in chromecasts:
                if cc.cast_info.host == self.host:
                    cc.wait(timeout=5)
                    return cc
        finally:
            pychromecast.discovery.stop_discovery(browser)

        # Fallback: direct connection
        cast = pychromecast.Chromecast(self.host)
        cast.wait(timeout=5)
        return cast

    async def async_play_url(
        self,
        url: str,
        content_type: str = "audio/mp3",
        title: str | None = None,
        thumb: str | None = None,
    ) -> None:
        """Play a media URL via the device's built-in Chromecast."""
        # Switch to NET source first if not already
        if self.state.input_name != "NET":
            await self.async_set_input("NET")
            await asyncio.sleep(0.5)

        cast = await self._ensure_cast()
        if cast is None:
            _LOGGER.warning("Cannot play media: Chromecast unavailable on %s", self.host)
            return

        def _do_play():
            mc = cast.media_controller
            mc.play_media(url, content_type, title=title, thumb=thumb)
            mc.block_until_active(timeout=5)

        try:
            await self.hass.async_add_executor_job(_do_play)
        except Exception as err:
            _LOGGER.warning("Failed to cast media to %s: %s", self.host, err)
            # Reset cast on error to force reconnect next time
            self._cast = None

    async def async_cast_disconnect(self) -> None:
        """Disconnect the chromecast (called on teardown)."""
        if self._cast is None:
            return
        try:
            await self.hass.async_add_executor_job(self._cast.disconnect)
        except Exception:
            pass
        self._cast = None


async def async_setup_entry(hass: HomeAssistant, entry: CantonConfigEntry) -> bool:
    """Set up Canton from a config entry."""
    hub = CantonHub(
        hass=hass,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        tunnel_port=entry.data.get(CONF_TUNNEL_PORT, DEFAULT_TUNNEL_PORT),
        usn=entry.unique_id or "",
        device_name=entry.title,
        model=entry.data.get(CONF_MODEL, ""),
        firmware_version=entry.data.get(CONF_FW_VERSION, ""),
        wifi_band=entry.data.get("wifi_band", ""),
    )

    await hub.async_setup()

    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop(_event) -> None:
        await hub.async_teardown()

    entry.async_on_unload(
        hass.bus.async_listen_once("homeassistant_stop", _async_stop)
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: CantonConfigEntry
) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CantonConfigEntry) -> bool:
    """Unload a Canton config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_teardown()
    return unload_ok
