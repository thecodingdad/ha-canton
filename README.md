# Canton Smart Sound

Home Assistant integration for Canton Smart Sound devices (Soundbar 10, Soundbar 9, Smart Connect 5.1, and others).

This integration communicates directly with your Canton devices over the local network using the reverse-engineered LUCI and Tunnel protocols. No cloud connection required.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/thecodingdad/ha-canton)](https://github.com/thecodingdad/ha-canton/releases)

## Features

- Full local control of Canton Smart Sound devices — no cloud required
- **Auto-discovery** — devices appear automatically in Home Assistant, just click Add
- Power on/off, volume, mute control
- Input source selection (BDP, SAT, PS, TV, CD, DVD, AUX, NET, BT)
- Sound mode selection (Stereo, Movie, Music, Night, Party, Discrete)
- 3-band EQ (Bass, Mid, Treble) with -10 to +10 dB range
- Subwoofer level control, Lip Sync delay
- 10 device presets — recall stored configurations
- Live media metadata (title, artist, album, cover art) for NET and BT sources
- Playback controls (play/pause, next/previous, seek, shuffle, repeat) for streaming sources
- OSD menu settings (CEC, DRC, Voice Clarity, Sleep Timer, Standby Mode, Input Selection, RF Power/Channel, Touch Panel, etc.)
- Built-in Chromecast support — cast TTS, URLs, and media to the device
- Push state updates from the device — no polling delay
- Automatic reconnect on network interruption
- Works in parallel with the official Canton app

## Prerequisites

- Home Assistant 2026.3.0 or newer
- Canton Smart Sound device on the same local network

## Supported Devices

I assume that all of the following Canton Smart devices should work, but I was only able to test the integration with the Soundbar 10.

- Canton Smart Soundbar 10
- Canton Smart Soundbar 9
- Canton Smart Sounddeck 100
- Canton Smart Connect 5.1
- Canton Smart Amp 5.1
- Canton Smart Soundbox 3

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thecodingdad&repository=ha-canton&category=integration)

Or add manually:
1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner and select **Custom repositories**
3. Enter `https://github.com/thecodingdad/ha-canton` and select **Integration** as the category
4. Click **Add**, then search for "Canton Smart Sound" and download it
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/thecodingdad/ha-canton/releases)
2. Copy the `custom_components/canton` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

### Adding a Device

Canton Smart Sound devices are discovered automatically. After installation and a Home Assistant restart, your device will appear under **Settings** > **Devices & Services** in the **Discovered** section. Click **Add** to set it up.

If the device is not discovered automatically:
1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **Canton Smart Sound**
3. Choose **Scan network for devices** or **Enter device manually** (IP address)
4. Select your device and confirm

### Options

After adding a device, you can configure it under **Settings** > **Devices & Services** > **Canton Smart Sound** > **Configure**:

| Option | Values | Description |
|--------|--------|-------------|
| Source list | Inputs / Presets | Controls what the media player source selector shows: physical inputs (BDP, TV, CD, ...) or saved presets (Preset 1, 2, 3, ...) |

## Entities

### Media Player

The main entity providing device control.

| Feature | Description |
|---------|-------------|
| Power | Turn the device on/off |
| Volume | Set volume level (0-70 for hardware inputs, 0-100 for NET/BT) |
| Mute | Mute/unmute audio |
| Source | Select input source or preset (depending on options) |
| Sound Mode | Select surround mode (Stereo, Movie, Music, Night, Party, Discrete) |
| Play/Pause/Stop | Playback control (available for NET and BT sources) |
| Next/Previous | Track skip (available for NET and BT sources) |
| Seek | Seek within track (available for NET and BT sources) |
| Shuffle | Toggle shuffle playback (available for NET and BT sources) |
| Repeat | Repeat mode: off, one, all (available for NET and BT sources) |
| Media Info | Shows title, artist, album, and cover art (for NET and BT sources) |

### Selects

Not all entities are available on every model. Entities are only created when supported by the connected device.

| Entity | Options | Description |
|--------|---------|-------------|
| Input | BDP, SAT, PS, TV, CD, DVD, AUX, NET, BT | Select the active input source |
| Play Mode | Stereo, Movie, Music, Night, Party, Discrete | Select the surround sound mode |
| Preset | Preset 1-10 (only configured ones) | Recall a saved preset (restores input, volume, EQ, and play mode) |
| Sleep Timer | Off, 15 Min, 30 Min, 45 Min, 60 Min | Auto-standby timer |
| Standby Mode | ECO, Network, Signal, Manual | Standby behavior when idle. ECO saves the most power, Network keeps the device reachable |
| Input Selection | Manual, Auto | Whether the device auto-detects the active input source |
| RF Power | ECO, Middle, Max | Transmit power of the wireless surround connection |
| RF Channel | AUTO, 2.4G1–3, 5.2G1–3, 5.8G1–3 | Wireless surround frequency channel |

### Numbers

Not all entities are available on every model. Entities are only created when supported by the connected device.

| Entity | Range | Unit | Description |
|--------|-------|------|-------------|
| Volume | 0-70 | — | Device volume using native range |
| EQ Bass | -10 to +10 | dB | Bass equalization |
| EQ Mid | -10 to +10 | dB | Mid-range equalization |
| EQ Treble | -10 to +10 | dB | Treble equalization |
| Max Volume | 0-70 | — | Maximum volume limit. Prevents the device from exceeding this level |
| Subwoofer Level | -10 to +10 | dB | Subwoofer output level |
| Lip Sync | 0-200 | ms | Audio delay to synchronize sound with video |

### Switches

Not all entities are available on every model. Entities are only created when supported by the connected device.

| Entity | Description |
|--------|-------------|
| Mute | Mute/unmute the device audio |
| HDMI CEC | Enable/disable HDMI CEC control. When enabled, the soundbar responds to TV power and volume commands |
| Dynamic Range Compression | Enable/disable DRC. Compresses the dynamic range — useful for night listening |
| Voice Clarity | Enhance speech intelligibility |
| Touch Panel | Enable/disable the touch controls on the device |
| LED Flashing | Enable/disable LED flashing animations on the device |
| Input Stream Display | Enable/disable automatic display of the current audio stream format (e.g. Dolby Digital, PCM) |
| Slave Speaker Display | Enable/disable the display on wireless surround speakers |

### Sensors

| Entity | Category | Description |
|--------|----------|-------------|
| Physical Source | — | Shows the physical connection in use (e.g. OPT 1, HDMI TV, BT) |
| IP Address | Diagnostic | Device IP address (disabled by default) |
| WiFi Band | Diagnostic | WiFi frequency band (disabled by default) |

### Buttons

| Entity | Description |
|--------|-------------|
| Bluetooth Pairing | Put the device into Bluetooth pairing mode |

## Device Information

The device page in Home Assistant shows:

- **Manufacturer:** Canton
- **Model:** e.g. Smart Soundbar 10
- **Firmware:** Version from device
- **MAC Address:** From device discovery

## Using the Canton App alongside Home Assistant

The Canton app and this integration can be used in parallel without any conflict. Both share control of the soundbar — changes made in one are visible in the other.

If the connection is lost unexpectedly (e.g. network interruption or device standby), the integration will automatically reconnect with exponential backoff (10s, 30s, 60s).

## Technical Details

This integration communicates with Canton devices using two protocols discovered through reverse engineering of the official Canton Android app:

- **LSSDP** (UDP port 1800) — Device discovery via multicast
- **LUCI** (TCP port 7777) — Registration and streaming source control (volume, playback, metadata for NET/BT)
- **Tunnel** (TCP port 50006) — Device control (power, input, EQ, presets, menu settings)

The Tunnel protocol uses a binary frame format with `0xFF 0xAA` header, 2-byte command ID, and variable-length payload.

## Multilanguage Support

This integration supports English and German.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
