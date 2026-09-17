"""Constants for the Canton Smart Sound integration."""

from homeassistant.const import Platform

DOMAIN = "canton"
PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.BUTTON,
]

# Network
DEFAULT_LUCI_PORT = 7777
LSSDP_MULTICAST_ADDR = "239.255.255.250"
LSSDP_PORT = 1800
LSSDP_ST = "urn:schemas-upnp-org:device:DDMSServer:1"

# Timing
KEEPALIVE_INTERVAL = 30
RECONNECT_DELAYS = [5, 10, 30, 60]
COMMAND_TIMEOUT = 5
DISCOVERY_TIMEOUT = 5

# Tunnel sharing
# The device accepts only ONE tunnel connection at a time — a second controller
# (Canton app, Unfolded Circle Remote, another HA instance) takes the slot over and
# the current connection is closed by the device. The integration therefore holds the
# tunnel permanently only while nobody else wants it (exclusive mode) and falls back
# to short on-demand sessions plus polling (shared mode) when it gets taken away.
SHARED_POLL_INTERVAL = 10
# How long to stay in shared mode before probing for exclusive access again.
# Grows with every failed attempt, capped at the last value.
SHARED_MODE_BACKOFF = [300, 600, 900, 1800]
# An exclusive connection surviving this long counts as success and resets the backoff
EXCLUSIVE_STABLE_SECONDS = 60

# LUCI header
HEADER_SIZE = 10

# LUCI command types
CMD_GET = 1
CMD_SET = 2

# LUCI command status
STATUS_INVALID = 0
STATUS_SUCCESS = 1
STATUS_ERROR = 2
STATUS_NOT_READY = 3

# Message Box IDs (MIDs)
MID_NOT_REGISTER = 0
MID_REGISTER = 3
MID_DEREGISTER = 4
MID_FIRMWARE_VERSION = 5
MID_HOST_VERSION = 6
MID_HOST_PRESENT = 9
MID_NEW_SOURCE = 10
MID_DEVICE_ATTACHMENT_STATUS = 38
MID_PLAY_CONTROL = 40
MID_BROWSE_CONTROL = 41
MID_GET_UI = 42
MID_APP_PLAYLIST = 43
MID_CURRENT_UI = 45
MID_PLAY_ELAPSED = 49
MID_CURRENT_SOURCE = 50
MID_CURRENT_PLAY_STATUS = 51
MID_PLAYBACK_EVENT = 54
MID_REBOOT_FROM_APP = 55
MID_VOLUME = 64
MID_FIRMWARE_UPGRADE_REQUEST = 65
MID_DEVICE_UPDATE = 66
MID_FAV = 70
MID_HAMAP3ORP5EQ = 82
MID_DEVICE_NAME = 90
MID_DEVICE_MAC = 91
MID_AUX_START = 95
MID_AUX_STOP = 96
MID_DDMS_TRIGGER = 100
MID_SA_MODE = 101
MID_LS_MODULE_SEARCH = 102
MID_DDMS_QUERY = 103
MID_DDMS_ZONE_ID = 104
MID_DDMS_SSID = 105
MID_SPEAKER_TYPE_SET = 106
MID_SCENE_NAME = 107
MID_TUNNELING_START = 111
MID_RE_BOOT_REQUEST = 114
MID_REBOOT = 115
MID_NETWORK_STATUS = 124
MID_NETWORK_CONFIGURE = 125
MID_CONFIGURE = 142
MID_EQ_PRESET = 145
MID_RSSI_INDICATOR = 151
MID_IOT_CONTROL = 207
MID_ENV_ITEM = 208
MID_BLUETOOTH = 209
MID_SDDP_NOTIFIER = 212
MID_SOURCE_CONTROL = 213
MID_SPOTIFY_SLAVE_INFO = 216
MID_ZONE_VOLUME = 219
MID_DEVICE_DOWNLOAD = 223
MID_GCAST_SERIAL_NUMBER = 231
MID_ALEXA_CLOSE_ALARM = 233
MID_ALEXA_COMMAND = 234

# Play status
PLAY_STATUS_PLAYING = 0
PLAY_STATUS_STOPPED = 1
PLAY_STATUS_PAUSED = 2
PLAY_STATUS_CONNECTING = 3
PLAY_STATUS_RECEIVING = 4
PLAY_STATUS_BUFFERING = 5

# Play sources
SOURCE_NONE = 0
SOURCE_AIRPLAY = 1
SOURCE_DMR = 2
SOURCE_DMP = 3
SOURCE_SPOTIFY = 4
SOURCE_USB = 5
SOURCE_SDCARD = 6
SOURCE_MELON = 7
SOURCE_VTUNER = 8
SOURCE_TUNEIN = 9
SOURCE_MIRACAST = 10
SOURCE_DDMS_SLAVE = 12
SOURCE_LINE_IN = 14
SOURCE_APPLE_USB = 16
SOURCE_DIRECT_URL = 17
SOURCE_QQMUSIC = 18
SOURCE_BLUETOOTH = 19
SOURCE_DEEZER = 21
SOURCE_TIDAL = 22
SOURCE_FAVORITES = 23
SOURCE_GOOGLE_CAST = 24
SOURCE_EXTERNAL = 25
SOURCE_ROON_LABS = 27
SOURCE_ALEXA = 28
SOURCE_ROON = 29
SOURCE_AIRABLE = 30

SOURCE_MAP: dict[int, str] = {
    SOURCE_NONE: "None",
    SOURCE_AIRPLAY: "AirPlay",
    SOURCE_DMR: "DMR",
    SOURCE_DMP: "DMP",
    SOURCE_SPOTIFY: "Spotify",
    SOURCE_USB: "USB",
    SOURCE_SDCARD: "SD Card",
    SOURCE_MELON: "Melon",
    SOURCE_VTUNER: "vTuner",
    SOURCE_TUNEIN: "TuneIn",
    SOURCE_MIRACAST: "Miracast",
    SOURCE_DDMS_SLAVE: "Multiroom",
    SOURCE_LINE_IN: "Line In",
    SOURCE_APPLE_USB: "Apple USB",
    SOURCE_DIRECT_URL: "URL",
    SOURCE_QQMUSIC: "QQ Music",
    SOURCE_BLUETOOTH: "Bluetooth",
    SOURCE_DEEZER: "Deezer",
    SOURCE_TIDAL: "TIDAL",
    SOURCE_FAVORITES: "Favorites",
    SOURCE_GOOGLE_CAST: "Google Cast",
    SOURCE_EXTERNAL: "External",
    SOURCE_ROON_LABS: "Roon Labs",
    SOURCE_ALEXA: "Alexa",
    SOURCE_ROON: "Roon",
    SOURCE_AIRABLE: "Airable",
}

SOURCE_REVERSE_MAP: dict[str, int] = {v: k for k, v in SOURCE_MAP.items()}

# Source capability bits (from SOURCE_LIST hex bitmap)
SOURCE_CAPABILITY_BITS: dict[int, int] = {
    0: SOURCE_AIRPLAY,
    1: SOURCE_DMR,
    2: SOURCE_DMP,
    3: SOURCE_SPOTIFY,
    4: SOURCE_USB,
    5: SOURCE_SDCARD,
    6: SOURCE_MELON,
    7: SOURCE_VTUNER,
    8: SOURCE_TUNEIN,
    9: SOURCE_MIRACAST,
    12: SOURCE_DDMS_SLAVE,
    14: SOURCE_LINE_IN,
    15: SOURCE_APPLE_USB,
    16: SOURCE_DIRECT_URL,
    17: SOURCE_QQMUSIC,
    18: SOURCE_BLUETOOTH,
    20: SOURCE_DEEZER,
    21: SOURCE_TIDAL,
    22: SOURCE_FAVORITES,
    23: SOURCE_GOOGLE_CAST,
    24: SOURCE_EXTERNAL,
    26: SOURCE_ROON_LABS,
    27: SOURCE_ALEXA,
    28: SOURCE_ROON,
    29: SOURCE_AIRABLE,
}

# Volume
VOLUME_MIN = 0
VOLUME_MAX = 99

# Dispatcher signals
SIGNAL_STATE_UPDATED = f"{DOMAIN}_state_updated_{{mac}}"
SIGNAL_CONNECTION_CHANGED = f"{DOMAIN}_connection_{{mac}}"

# Config keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_MAC = "mac"
CONF_DEVICE_NAME = "device_name"
CONF_MODEL = "model"
CONF_FW_VERSION = "fw_version"
CONF_TUNNEL_PORT = "tunnel_port"
CONF_SOURCE_LIST_MODE = "source_list_mode"
DEFAULT_TUNNEL_PORT = 50006
SOURCE_MODE_INPUTS = "inputs"
SOURCE_MODE_PRESETS = "presets"

# Tunnel command IDs (cmd0, cmd1)
# cmd1: 1=SET/response, 2=GET, 3=ENTER/SET, 4=EXIT
TCMD_SOURCE_INFO_GET = (2, 2)
TCMD_SOURCE_SET = (3, 1)
TCMD_SOURCE_GET = (3, 2)
TCMD_EQ_SET = (4, 1)
TCMD_EQ_GET = (4, 2)
TCMD_MENU_SET = (5, 1)
TCMD_MENU_GET = (5, 2)
TCMD_MENU_EXIT = (5, 4)
TCMD_STANDBY_SET = (6, 1)
TCMD_STANDBY_GET = (6, 2)
TCMD_PRESET_RECALL = (7, 3)
TCMD_PRESET_GET = (7, 2)
TCMD_MUTE_SET = (9, 1)
TCMD_MUTE_GET = (9, 2)
TCMD_BT_PAIR = (10, 1)
TCMD_VOLUME_SET = (12, 1)
TCMD_VOLUME_GET = (12, 2)

# Tunnel input name IDs (nameId in SOURCE_SET payload).
# The device assigns a name to every physical input under
# "System Setup -> Input Setup -> Input Name"; the stored value is the nameId below.
# Source: the ENUM options of the input name menus in the Canton app (menu IDs 0x2511+),
# verified against SOURCE_INFO on a Smart Soundbar 10.
INPUT_NAME_UNASSIGNED = 1
TUNNEL_INPUT_NAMES: dict[int, str] = {
    INPUT_NAME_UNASSIGNED: "---",
    2: "TV",
    3: "BDP",
    4: "SAT",
    5: "CD",
    6: "DVD",
    7: "CAM",
    8: "REC",
    9: "PAD",
    10: "POD",
    11: "TAB",
    12: "TUN",
    13: "DAB",
    14: "PS",
    15: "VCR",
    16: "ATV",
    17: "PC",
    18: "AUX",
    # Virtual sources, not selectable as an input name on the device
    19: "NET",
    20: "BT",
}
TUNNEL_INPUT_NAMES_REVERSE: dict[str, int] = {v: k for k, v in TUNNEL_INPUT_NAMES.items()}

# Names that can be selected as an input (everything except the "unassigned" entry)
SELECTABLE_INPUT_NAMES: list[str] = [
    name for nid, name in TUNNEL_INPUT_NAMES.items() if nid != INPUT_NAME_UNASSIGNED
]

# Menu IDs of the per-input name settings ("System Setup -> Input Setup -> Input Name").
# The menu value is the nameId, so these allow reading which name a physical input carries.
INPUT_NAME_MENU_IDS: dict[int, str] = {
    0x2511: "HDMI 1",
    0x2512: "HDMI 2",
    0x2513: "HDMI 3",
    0x2514: "ARC",
    0x2515: "OPT",
    0x2516: "COAX",
    0x2517: "Analog",
}

# Tunnel play mode IDs
TUNNEL_PLAY_MODES: dict[int, str] = {
    1: "Stereo",
    2: "Movie",
    3: "Music",
    4: "Night",
    5: "Party",
    6: "Discrete",
    7: "Pure",
    8: "Movie",
}
# Reverse map: use lowest ID for duplicates (Movie→2, not Movie→8)
TUNNEL_PLAY_MODES_REVERSE: dict[str, int] = {}
for _id in sorted(TUNNEL_PLAY_MODES):
    _name = TUNNEL_PLAY_MODES[_id]
    if _name not in TUNNEL_PLAY_MODES_REVERSE:
        TUNNEL_PLAY_MODES_REVERSE[_name] = _id

# Tunnel physical source IDs (sourceId in SOURCE_SET payload)
TUNNEL_PHYSICAL_SOURCES: dict[int, str] = {
    1: "HDMI 1", 2: "HDMI 2", 3: "HDMI 3", 4: "HDMI 4", 5: "HDMI 5",
    6: "HDMI TV", 7: "OPT 1", 8: "OPT 2", 9: "OPT 3", 10: "OPT 4",
    11: "COAX 1", 12: "COAX 2", 15: "AUX 1", 16: "AUX 2",
    20: "USB", 21: "BT", 22: "WIRELESS", 23: "NET",
}

# Canton device model names (as reported in the CAST_MODEL LSSDP header)
MODEL_SOUNDBAR_10 = "Smart Soundbar 10"
MODEL_SOUNDBAR_9 = "Smart Soundbar 9"
MODEL_SOUNDDECK_100 = "Smart Sounddeck 100"
MODEL_SOUNDBOX_3 = "Smart Soundbox 3"
MODEL_CONNECT_51 = "Smart Connect 5.1"
MODEL_AMP_51 = "Smart Amp 5.1"

# OSD menu setting names (used as keys throughout the integration)
MENU_DRC = "drc"
MENU_VOICE_CLARITY = "voice_clarity"
MENU_SLEEP_TIMER = "sleep_timer"
MENU_CEC = "cec"
MENU_STANDBY_MODE = "standby_mode"
MENU_INPUT_SELECTION = "input_selection"
MENU_LIP_SYNC = "lip_sync"
MENU_MAX_VOLUME = "max_volume"
MENU_TOUCH_PANEL = "touch_panel"
MENU_LED_FLASHING = "led_flashing"
MENU_INPUT_STREAM_DISPLAY = "input_stream_display"
MENU_SLAVE_DISPLAY = "slave_display"
MENU_RF_POWER = "rf_power"
MENU_RF_CHANNEL = "rf_channel"
MENU_SUBWOOFER_LEVEL = "subwoofer_level"

# Per-model menu IDs accessed via MENU_GET/SET tunnel cmd 5.
# None means the setting is not supported on that model.
# Source: reverse-engineered from APK menu definitions per device model.
MENU_IDS_BY_MODEL: dict[str, dict[str, int | None]] = {
    MENU_DRC: {
        MODEL_SOUNDBAR_10: 19,
        MODEL_SOUNDBAR_9: 19,
        MODEL_SOUNDDECK_100: 19,
        MODEL_SOUNDBOX_3: None,
        MODEL_CONNECT_51: 19,
        MODEL_AMP_51: 19,
    },
    MENU_VOICE_CLARITY: {
        MODEL_SOUNDBAR_10: 20,
        MODEL_SOUNDBAR_9: 21,
        MODEL_SOUNDDECK_100: 20,
        MODEL_SOUNDBOX_3: 19,
        MODEL_CONNECT_51: 20,
        MODEL_AMP_51: 20,
    },
    MENU_SLEEP_TIMER: {
        MODEL_SOUNDBAR_10: 33,
        MODEL_SOUNDBAR_9: 33,
        MODEL_SOUNDDECK_100: 33,
        MODEL_SOUNDBOX_3: 33,
        MODEL_CONNECT_51: 33,
        MODEL_AMP_51: 33,
    },
    MENU_CEC: {
        MODEL_SOUNDBAR_10: 35,
        MODEL_SOUNDBAR_9: 35,
        MODEL_SOUNDDECK_100: 35,
        MODEL_SOUNDBOX_3: None,
        MODEL_CONNECT_51: 35,
        MODEL_AMP_51: 35,
    },
    MENU_STANDBY_MODE: {
        MODEL_SOUNDBAR_10: 36,
        MODEL_SOUNDBAR_9: 36,
        MODEL_SOUNDDECK_100: 36,
        MODEL_SOUNDBOX_3: 35,
        MODEL_CONNECT_51: 36,
        MODEL_AMP_51: 36,
    },
    MENU_INPUT_SELECTION: {
        MODEL_SOUNDBAR_10: 38,
        MODEL_SOUNDBAR_9: 38,
        MODEL_SOUNDDECK_100: 38,
        MODEL_SOUNDBOX_3: 36,
        MODEL_CONNECT_51: None,
        MODEL_AMP_51: None,
    },
    MENU_LIP_SYNC: {
        MODEL_SOUNDBAR_10: 40,
        MODEL_SOUNDBAR_9: 41,
        MODEL_SOUNDDECK_100: 40,
        MODEL_SOUNDBOX_3: None,
        MODEL_CONNECT_51: None,
        MODEL_AMP_51: None,
    },
    MENU_MAX_VOLUME: {
        MODEL_SOUNDBAR_10: 41,
        MODEL_SOUNDBAR_9: 42,
        MODEL_SOUNDDECK_100: 41,
        MODEL_SOUNDBOX_3: 38,
        MODEL_CONNECT_51: 40,
        MODEL_AMP_51: 41,
    },
    MENU_TOUCH_PANEL: {
        MODEL_SOUNDBAR_10: 44,
        MODEL_SOUNDBAR_9: None,
        MODEL_SOUNDDECK_100: None,
        MODEL_SOUNDBOX_3: 40,
        MODEL_CONNECT_51: 45,
        MODEL_AMP_51: 45,
    },
    MENU_LED_FLASHING: {
        MODEL_SOUNDBAR_10: 674,
        MODEL_SOUNDBAR_9: 690,
        MODEL_SOUNDDECK_100: 690,
        MODEL_SOUNDBOX_3: 627,
        MODEL_CONNECT_51: None,
        MODEL_AMP_51: None,
    },
    MENU_INPUT_STREAM_DISPLAY: {
        MODEL_SOUNDBAR_10: 675,
        MODEL_SOUNDBAR_9: 691,
        MODEL_SOUNDDECK_100: 691,
        MODEL_SOUNDBOX_3: None,
        MODEL_CONNECT_51: None,
        MODEL_AMP_51: None,
    },
    MENU_SLAVE_DISPLAY: {
        MODEL_SOUNDBAR_10: 676,
        MODEL_SOUNDBAR_9: 692,
        MODEL_SOUNDDECK_100: 692,
        MODEL_SOUNDBOX_3: None,
        MODEL_CONNECT_51: 708,
        MODEL_AMP_51: 708,
    },
    MENU_RF_POWER: {
        MODEL_SOUNDBAR_10: 67,
        MODEL_SOUNDBAR_9: 67,
        MODEL_SOUNDDECK_100: 67,
        MODEL_SOUNDBOX_3: 66,
        MODEL_CONNECT_51: 66,
        MODEL_AMP_51: 65,
    },
    MENU_RF_CHANNEL: {
        MODEL_SOUNDBAR_10: 68,
        MODEL_SOUNDBAR_9: 68,
        MODEL_SOUNDDECK_100: 68,
        MODEL_SOUNDBOX_3: None,
        MODEL_CONNECT_51: 67,
        MODEL_AMP_51: 66,
    },
    MENU_SUBWOOFER_LEVEL: {
        MODEL_SOUNDBAR_10: 281,
        MODEL_SOUNDBAR_9: 279,
        MODEL_SOUNDDECK_100: 281,
        MODEL_SOUNDBOX_3: 276,
        MODEL_CONNECT_51: 285,
        MODEL_AMP_51: 285,
    },
}

# Number of MENU_EXIT commands needed to fully close the OSD after a SET.
# The device auto-navigates into the menu hierarchy when MENU_SET is sent,
# so we need to send one EXIT per nesting level + 1 to fully close the OSD.
# Hierarchy depth assumed identical across models.
MENU_EXIT_COUNT: dict[str, int] = {
    # 1 level deep (System Setup -> item) → 2 exits
    MENU_SLEEP_TIMER: 2,
    MENU_CEC: 2,
    MENU_STANDBY_MODE: 2,
    MENU_INPUT_SELECTION: 2,
    MENU_LIP_SYNC: 2,
    MENU_MAX_VOLUME: 2,
    MENU_TOUCH_PANEL: 2,
    # 1 level deep (Speaker Setup -> item) → 2 exits
    MENU_DRC: 2,
    MENU_VOICE_CLARITY: 2,
    # 1 level deep (Wireless Setup -> item) → 2 exits
    MENU_RF_POWER: 2,
    MENU_RF_CHANNEL: 2,
    # 2 levels deep (Speaker Setup -> Channel Level -> Subwoofer) → 3 exits
    MENU_SUBWOOFER_LEVEL: 3,
    # 2 levels deep (System Setup -> Display Setup -> item) → 3 exits
    MENU_LED_FLASHING: 3,
    MENU_INPUT_STREAM_DISPLAY: 3,
    MENU_SLAVE_DISPLAY: 3,
}
MENU_EXIT_COUNT_DEFAULT = 3

SLEEP_TIMER_OPTIONS: dict[int, str] = {
    0: "15 Min",
    1: "30 Min",
    2: "45 Min",
    3: "60 Min",
    4: "Off",
}
SLEEP_TIMER_REVERSE: dict[str, int] = {v: k for k, v in SLEEP_TIMER_OPTIONS.items()}

STANDBY_MODE_OPTIONS: dict[int, str] = {
    0: "ECO",
    1: "Network",
    2: "Signal",
    3: "Manual",
}
STANDBY_MODE_REVERSE: dict[str, int] = {v: k for k, v in STANDBY_MODE_OPTIONS.items()}

INPUT_SELECTION_OPTIONS: dict[int, str] = {
    0: "Manual",
    1: "Auto",
}
INPUT_SELECTION_REVERSE: dict[str, int] = {v: k for k, v in INPUT_SELECTION_OPTIONS.items()}

# RF Power: display labels with internal device values (showValue array from APK)
RF_POWER_OPTIONS: dict[int, str] = {
    0: "ECO",
    3: "Middle",
    5: "Max",
}
RF_POWER_REVERSE: dict[str, int] = {v: k for k, v in RF_POWER_OPTIONS.items()}

# RF Channel: display labels with internal device values (showValue array from APK)
RF_CHANNEL_OPTIONS: dict[int, str] = {
    0: "AUTO",
    7: "2.4G1",
    8: "2.4G2",
    9: "2.4G3",
    10: "5.2G1",
    11: "5.2G2",
    12: "5.2G3",
    13: "5.8G1",
    14: "5.8G2",
    15: "5.8G3",
}
RF_CHANNEL_REVERSE: dict[str, int] = {v: k for k, v in RF_CHANNEL_OPTIONS.items()}

