"""Media player platform for Canton Smart Sound."""

from __future__ import annotations

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
    async_process_play_media_url,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.dt import utcnow
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CantonHub
from .const import (
    CONF_SOURCE_LIST_MODE,
    PLAY_STATUS_BUFFERING,
    PLAY_STATUS_CONNECTING,
    PLAY_STATUS_PAUSED,
    PLAY_STATUS_PLAYING,
    PLAY_STATUS_RECEIVING,
    PLAY_STATUS_STOPPED,
    SIGNAL_STATE_UPDATED,
    SOURCE_MODE_PRESETS,
)
from .entity import CantonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Canton media player from a config entry."""
    hub: CantonHub = entry.runtime_data
    async_add_entities([CantonMediaPlayer(hub, entry)])


class CantonMediaPlayer(CantonEntity, MediaPlayerEntity):
    """Representation of a Canton media player."""

    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(self, hub: CantonHub, entry: ConfigEntry) -> None:
        super().__init__(hub)
        self._entry = entry
        self._attr_unique_id = f"{hub.usn}_player"

    @property
    def _is_preset_mode(self) -> bool:
        return self._entry.options.get(CONF_SOURCE_LIST_MODE) == SOURCE_MODE_PRESETS

    @property
    def state(self) -> MediaPlayerState:
        if not self._hub.state.power_on:
            return MediaPlayerState.OFF
        # For NET/BT, reflect actual playback state
        if self._hub.state.input_name in ("NET", "BT"):
            ps = self._hub.state.play_status
            if ps == PLAY_STATUS_PLAYING:
                return MediaPlayerState.PLAYING
            if ps == PLAY_STATUS_PAUSED:
                return MediaPlayerState.PAUSED
            if ps in (PLAY_STATUS_CONNECTING, PLAY_STATUS_RECEIVING, PLAY_STATUS_BUFFERING):
                return MediaPlayerState.BUFFERING
            if ps == PLAY_STATUS_STOPPED:
                return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        if self._hub.state.volume_max == 0:
            return None
        return self._hub.state.volume / self._hub.state.volume_max

    @property
    def is_volume_muted(self) -> bool:
        return self._hub.state.is_muted

    @property
    def source(self) -> str | None:
        if self._is_preset_mode:
            p = self._hub.state.active_preset
            return f"Preset {p}" if p > 0 else None
        return self._hub.current_input

    @property
    def source_list(self) -> list[str]:
        if self._is_preset_mode:
            return [
                f"Preset {i}" for i in self._hub.state.configured_presets
            ] if self._hub.state.configured_presets else []
        return self._hub.input_list

    @property
    def media_content_type(self) -> MediaType | None:
        if self._hub.state.media_title:
            return MediaType.MUSIC
        return None

    @property
    def media_title(self) -> str | None:
        return self._hub.state.media_title

    @property
    def media_artist(self) -> str | None:
        return self._hub.state.media_artist

    @property
    def media_album_name(self) -> str | None:
        return self._hub.state.media_album

    @property
    def media_image_url(self) -> str | None:
        return self._hub.state.media_image_url

    @property
    def media_duration(self) -> float | None:
        if self._hub.state.media_duration:
            return self._hub.state.media_duration / 1000
        return None

    @property
    def media_position(self) -> float | None:
        if self._hub.state.media_position is not None and self._hub.state.media_position >= 0:
            return self._hub.state.media_position / 1000
        return None

    @property
    def shuffle(self) -> bool | None:
        if self._hub.state.input_name in ("NET", "BT"):
            return self._hub.state.shuffle
        return None

    @property
    def repeat(self) -> RepeatMode | None:
        if self._hub.state.input_name not in ("NET", "BT"):
            return None
        return {
            0: RepeatMode.OFF,
            1: RepeatMode.ONE,
            2: RepeatMode.ALL,
        }.get(self._hub.state.repeat, RepeatMode.OFF)

    @property
    def media_position_updated_at(self):
        """Return when position was last updated (enables HA position interpolation)."""
        if self._hub.state.media_position is not None and self._hub.state.media_position >= 0:
            return utcnow()
        return None

    @property
    def sound_mode(self) -> str | None:
        return self._hub.state.play_mode or None

    @property
    def sound_mode_list(self) -> list[str]:
        from .const import TUNNEL_PLAY_MODES
        return list(dict.fromkeys(TUNNEL_PLAY_MODES.values()))

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = self._attr_supported_features
        if self.sound_mode_list:
            features |= MediaPlayerEntityFeature.SELECT_SOUND_MODE
        if self._hub.state.input_name in ("NET", "BT"):
            features |= (
                MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.NEXT_TRACK
                | MediaPlayerEntityFeature.PREVIOUS_TRACK
                | MediaPlayerEntityFeature.STOP
                | MediaPlayerEntityFeature.SEEK
                | MediaPlayerEntityFeature.SHUFFLE_SET
                | MediaPlayerEntityFeature.REPEAT_SET
            )
        return features

    async def async_set_volume_level(self, volume: float) -> None:
        vol = round(volume * self._hub.state.volume_max)
        await self._hub.async_set_volume(vol)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._hub.async_set_mute(mute)

    async def async_turn_on(self) -> None:
        await self._hub.async_set_power(True)

    async def async_turn_off(self) -> None:
        await self._hub.async_set_power(False)

    async def async_select_source(self, source: str) -> None:
        if self._is_preset_mode and source.startswith("Preset "):
            try:
                preset = int(source.split()[-1])
                await self._hub.async_recall_preset(preset)
            except (ValueError, IndexError):
                pass
        else:
            await self._hub.async_set_input(source)

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        await self._hub.async_set_play_mode(sound_mode)

    async def async_media_play(self) -> None:
        await self._hub.async_play_control("RESUME")

    async def async_media_pause(self) -> None:
        await self._hub.async_play_control("PAUSE")

    async def async_media_stop(self) -> None:
        await self._hub.async_play_control("STOP")

    async def async_media_next_track(self) -> None:
        await self._hub.async_play_control("NEXT")

    async def async_media_previous_track(self) -> None:
        await self._hub.async_play_control("PREV")

    async def async_media_seek(self, position: float) -> None:
        await self._hub.async_play_control(f"SEEK:{int(position * 1000)}")

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._hub.async_play_control(f"SHUFFLE:{'ON' if shuffle else 'OFF'}")

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        mapping = {
            RepeatMode.OFF: "REPEAT:OFF",
            RepeatMode.ONE: "REPEAT:ONE",
            RepeatMode.ALL: "REPEAT:ALL",
        }
        await self._hub.async_play_control(mapping.get(repeat, "REPEAT:OFF"))

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs
    ) -> None:
        """Play media via the device's built-in Chromecast."""
        # Resolve media-source URLs
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = async_process_play_media_url(self.hass, play_item.url)
            if play_item.mime_type:
                media_type = play_item.mime_type

        if not media_type or media_type == MediaType.MUSIC:
            media_type = "audio/mp3"

        await self._hub.async_play_url(media_id, content_type=media_type)

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse media using HA's media source browser."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

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
