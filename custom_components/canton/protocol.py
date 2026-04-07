"""LUCI binary protocol and LSSDP discovery for Canton Smart Sound devices."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .const import (
    CMD_GET,
    CMD_SET,
    COMMAND_TIMEOUT,
    DEFAULT_LUCI_PORT,
    DEFAULT_TUNNEL_PORT,
    DISCOVERY_TIMEOUT,
    HEADER_SIZE,
    KEEPALIVE_INTERVAL,
    LSSDP_MULTICAST_ADDR,
    LSSDP_PORT,
    LSSDP_ST,
    MID_DEVICE_NAME,
    MID_GET_UI,
    MID_REGISTER,
    RECONNECT_DELAYS,
    SOURCE_CAPABILITY_BITS,
    SOURCE_MAP,
)

_LOGGER = logging.getLogger(__name__)

# Send in little-endian, receive in big-endian
SEND_FMT = "<HBHBHH"
RECV_FMT = ">HBHBHH"


def _get_local_ip(target_host: str) -> str | None:
    """Get the local IP address used to reach target_host."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target_host, 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def _set_socket_options(writer: asyncio.StreamWriter) -> None:
    """Enable TCP_NODELAY and SO_KEEPALIVE on the underlying socket.

    The Canton app sets both options explicitly. Without SO_KEEPALIVE the
    soundbar may not detect our closed connection quickly enough.
    """
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


@dataclass
class LuciMessage:
    """Represents a LUCI protocol message."""

    remote_id: int
    command_type: int
    mid: int
    status: int
    payload: str

    def encode(self) -> bytes:
        """Encode message to bytes for sending over TCP (little-endian)."""
        payload_bytes = self.payload.encode("utf-8") if self.payload else b""
        header = struct.pack(
            SEND_FMT,
            self.remote_id,
            self.command_type,
            self.mid,
            self.status,
            0,  # CRC (unused)
            len(payload_bytes),
        )
        return header + payload_bytes

    @staticmethod
    def decode(data: bytes) -> LuciMessage:
        """Decode bytes received from device (big-endian)."""
        remote_id, cmd_type, mid, status, _crc, payload_len = struct.unpack(
            RECV_FMT, data[:HEADER_SIZE]
        )
        payload = ""
        if payload_len > 0:
            payload = data[HEADER_SIZE : HEADER_SIZE + payload_len].decode(
                "utf-8", errors="replace"
            )
        return LuciMessage(
            remote_id=remote_id,
            command_type=cmd_type,
            mid=mid,
            status=status,
            payload=payload,
        )

    @staticmethod
    def create(
        mid: int, command_type: int = CMD_GET, payload: str = ""
    ) -> LuciMessage:
        """Create a new message to send."""
        return LuciMessage(
            remote_id=0,
            command_type=command_type,
            mid=mid,
            status=0,
            payload=payload,
        )


class ConnectionState(Enum):
    """Protocol connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class LuciProtocol:
    """Async LUCI protocol handler for Canton devices."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._state = ConnectionState.DISCONNECTED
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._closing = False
        self._pending_responses: dict[int, asyncio.Future[LuciMessage]] = {}
        self.on_message: Callable[[LuciMessage], None] | None = None
        self.on_connection_change: Callable[[bool], None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def host(self) -> str:
        return self._host

    async def async_connect(self) -> bool:
        """Connect to the device and register."""
        if self._state == ConnectionState.CONNECTED:
            return True

        self._closing = False
        self._state = ConnectionState.CONNECTING

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=COMMAND_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug(
                "Connection to %s:%s failed: %s", self._host, self._port, err
            )
            self._state = ConnectionState.DISCONNECTED
            return False

        _set_socket_options(self._writer)

        # Send registration with our local IP as payload (CMD_SET).
        # The Canton app does exactly this — registering as GET leaves the
        # device in a weird state where it stops accepting commands from
        # other clients until power-cycled.
        local_ip = _get_local_ip(self._host) or ""
        try:
            msg = LuciMessage.create(MID_REGISTER, CMD_SET, local_ip)
            self._writer.write(msg.encode())
            await self._writer.drain()

            data = await asyncio.wait_for(
                self._reader.read(HEADER_SIZE + 256), timeout=COMMAND_TIMEOUT
            )
            if len(data) < HEADER_SIZE:
                _LOGGER.debug("Registration with %s failed (short response)", self._host)
                await self._close_connection()
                return False

            response = LuciMessage.decode(data)
            if response.mid != MID_REGISTER:
                _LOGGER.debug(
                    "Registration with %s failed (unexpected MID %s)",
                    self._host,
                    response.mid,
                )
                await self._close_connection()
                return False
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Registration with %s failed: %s", self._host, err)
            await self._close_connection()
            return False

        self._state = ConnectionState.CONNECTED
        _LOGGER.debug("Connected and registered with %s", self._host)

        # Start background tasks
        self._read_task = asyncio.ensure_future(self._read_loop())
        self._keepalive_task = asyncio.ensure_future(self._keepalive_loop())

        if self.on_connection_change:
            self.on_connection_change(True)

        return True

    async def async_disconnect(self) -> None:
        """Disconnect from the device.

        The Canton app never sends MID_DEREGISTER on disconnect — it just
        closes the TCP connection. Sending MID_DEREGISTER puts the soundbar
        into a stuck state where it ignores all commands until power-cycled.
        """
        self._closing = True
        self._cancel_reconnect()
        await self._close_connection()

    async def async_send(
        self, mid: int, command_type: int = CMD_GET, payload: str = ""
    ) -> LuciMessage | None:
        """Send a message and wait for the response."""
        if not self.is_connected or not self._writer:
            return None
        msg = LuciMessage.create(mid, command_type, payload)
        return await self._async_send_and_wait(msg)

    async def async_send_fire(
        self, mid: int, command_type: int = CMD_SET, payload: str = ""
    ) -> None:
        """Send a message without waiting for response."""
        if not self.is_connected or not self._writer:
            return
        msg = LuciMessage.create(mid, command_type, payload)
        try:
            self._writer.write(msg.encode())
            await self._writer.drain()
        except OSError as err:
            _LOGGER.debug("Send failed: %s", err)
            await self._trigger_reconnect()

    async def _async_send_and_wait(self, msg: LuciMessage) -> LuciMessage | None:
        """Send a message and wait for the matching response."""
        if not self._writer:
            return None

        future: asyncio.Future[LuciMessage] = asyncio.get_running_loop().create_future()
        self._pending_responses[msg.mid] = future

        try:
            self._writer.write(msg.encode())
            await self._writer.drain()
            return await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Send and wait failed for MID %s: %s", msg.mid, err)
            return None
        finally:
            self._pending_responses.pop(msg.mid, None)

    async def _read_loop(self) -> None:
        """Read and parse messages from the TCP stream."""
        buffer = b""
        while not self._closing and self._reader:
            try:
                data = await self._reader.read(4096)
                if not data:
                    _LOGGER.debug("Connection closed by %s", self._host)
                    break
                buffer += data

                while len(buffer) >= HEADER_SIZE:
                    # Parse header in big-endian (device response format)
                    _, _, mid, _, _, payload_len = struct.unpack(
                        RECV_FMT, buffer[:HEADER_SIZE]
                    )
                    if mid < 0 or mid >= 1200:
                        _LOGGER.debug("Invalid MID %s, skipping byte", mid)
                        buffer = buffer[1:]
                        continue

                    total_len = HEADER_SIZE + payload_len
                    if len(buffer) < total_len:
                        break

                    msg_data = buffer[:total_len]
                    buffer = buffer[total_len:]

                    msg = LuciMessage.decode(msg_data)
                    self._dispatch_message(msg)

            except (OSError, asyncio.IncompleteReadError) as err:
                if not self._closing:
                    _LOGGER.debug("Read error: %s", err)
                break

        if not self._closing:
            await self._trigger_reconnect()

    def _dispatch_message(self, msg: LuciMessage) -> None:
        """Dispatch a received message to pending futures or callback."""
        future = self._pending_responses.pop(msg.mid, None)
        if future and not future.done():
            future.set_result(msg)
            return

        if self.on_message:
            try:
                self.on_message(msg)
            except Exception:
                _LOGGER.exception("Error in message callback for MID %s", msg.mid)

    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive requests."""
        while not self._closing:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            if self._closing:
                break
            response = await self.async_send(MID_GET_UI, CMD_GET)
            if response is None and not self._closing:
                _LOGGER.debug("Keepalive failed, triggering reconnect")
                await self._trigger_reconnect()
                return

    async def _trigger_reconnect(self) -> None:
        """Close current connection and start reconnecting."""
        if self._closing:
            return

        was_connected = self._state == ConnectionState.CONNECTED
        await self._close_connection()
        self._state = ConnectionState.RECONNECTING

        if was_connected and self.on_connection_change:
            self.on_connection_change(False)

        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        for delay in RECONNECT_DELAYS:
            if self._closing:
                return
            _LOGGER.debug("Reconnecting to %s in %s seconds", self._host, delay)
            await asyncio.sleep(delay)
            if self._closing:
                return
            if await self.async_connect():
                return

        while not self._closing:
            _LOGGER.debug(
                "Reconnecting to %s in %s seconds",
                self._host,
                RECONNECT_DELAYS[-1],
            )
            await asyncio.sleep(RECONNECT_DELAYS[-1])
            if self._closing:
                return
            if await self.async_connect():
                return

    def _cancel_reconnect(self) -> None:
        """Cancel any pending reconnect."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None

    async def _close_connection(self) -> None:
        """Close the TCP connection and cancel tasks."""
        for task in (self._read_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()
        self._read_task = None
        self._keepalive_task = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._writer = None
        self._reader = None

        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()
        self._pending_responses.clear()

        self._state = ConnectionState.DISCONNECTED


class TunnelProtocol:
    """Async tunnel protocol handler for Canton AV devices (Soundbar/Connect)."""

    HEADER_SIZE = 7
    MAGIC = bytes([0xFF, 0xAA])

    def __init__(self, host: str, tunnel_port: int, luci: LuciProtocol) -> None:
        self._host = host
        self._tunnel_port = tunnel_port
        self._luci = luci
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._closing = False
        self._connected = False
        self._pending: dict[int, asyncio.Future[tuple[tuple[int, int], bytes]]] = {}
        self.on_message: Callable[[tuple[int, int], bytes], None] | None = None
        self.on_connection_change: Callable[[bool], None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def encode(cmd0: int, cmd1: int, payload: bytes = b"") -> bytes:
        """Encode a tunnel message."""
        return bytes([
            0xFF, 0xAA, 0x00,
            cmd0, cmd1,
            (len(payload) >> 8) & 0xFF,
            len(payload) & 0xFF,
        ]) + payload

    async def async_connect(self) -> bool:
        """Connect to the tunnel port (requires LUCI to be connected first)."""
        self._closing = False

        # Start tunnel via LUCI
        from .const import MID_TUNNELING_START

        await self._luci.async_send_fire(
            MID_TUNNELING_START, CMD_SET, str(self._tunnel_port)
        )
        await asyncio.sleep(0.5)

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._tunnel_port),
                timeout=COMMAND_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Tunnel connect to %s:%s failed: %s", self._host, self._tunnel_port, err)
            return False

        _set_socket_options(self._writer)

        self._connected = True
        self._read_task = asyncio.ensure_future(self._read_loop())
        self._keepalive_task = asyncio.ensure_future(self._keepalive_loop())
        _LOGGER.debug("Tunnel connected to %s:%s", self._host, self._tunnel_port)

        if self.on_connection_change:
            self.on_connection_change(True)
        return True

    async def async_disconnect(self) -> None:
        """Disconnect the tunnel."""
        self._closing = True
        for task in (self._read_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()
        self._read_task = None
        self._keepalive_task = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._writer = None
        self._reader = None

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        was_connected = self._connected
        self._connected = False
        if was_connected and self.on_connection_change:
            self.on_connection_change(False)

    async def async_send(
        self, cmd0: int, cmd1: int, payload: bytes = b""
    ) -> bytes | None:
        """Send a tunnel command and wait for the response."""
        if not self._connected or not self._writer:
            return None

        # Key by cmd0 only — responses may echo cmd1 or use a different one
        future: asyncio.Future[tuple[tuple[int, int], bytes]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[cmd0] = future

        try:
            self._writer.write(self.encode(cmd0, cmd1, payload))
            await self._writer.drain()
            _, resp_payload = await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
            return resp_payload
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Tunnel send failed for CMD (%s,%s): %s", cmd0, cmd1, err)
            return None
        finally:
            self._pending.pop(cmd0, None)

    async def async_send_fire(
        self, cmd0: int, cmd1: int, payload: bytes = b""
    ) -> None:
        """Send a tunnel command without waiting for response."""
        if not self._connected or not self._writer:
            return
        try:
            self._writer.write(self.encode(cmd0, cmd1, payload))
            await self._writer.drain()
        except OSError as err:
            _LOGGER.debug("Tunnel send_fire failed: %s", err)

    async def _read_loop(self) -> None:
        """Read tunnel messages from TCP stream."""
        buffer = b""
        while not self._closing and self._reader:
            try:
                data = await self._reader.read(4096)
                if not data:
                    break
                buffer += data

                while len(buffer) >= self.HEADER_SIZE:
                    # Find magic bytes
                    if buffer[0] != 0xFF or buffer[1] != 0xAA:
                        buffer = buffer[1:]
                        continue

                    plen = (buffer[5] << 8) | buffer[6]
                    total = self.HEADER_SIZE + plen
                    if len(buffer) < total:
                        break

                    cmd = (buffer[3], buffer[4])
                    payload = bytes(buffer[self.HEADER_SIZE : total])
                    buffer = buffer[total:]

                    self._dispatch(cmd, payload)

            except (OSError, asyncio.IncompleteReadError) as err:
                if not self._closing:
                    _LOGGER.debug("Tunnel read error: %s", err)
                break

        if not self._closing:
            self._connected = False
            if self.on_connection_change:
                self.on_connection_change(False)

    def _dispatch(self, cmd: tuple[int, int], payload: bytes) -> None:
        """Dispatch a tunnel response."""
        future = self._pending.pop(cmd[0], None)
        if future and not future.done():
            future.set_result((cmd, payload))
            return

        if self.on_message:
            try:
                self.on_message(cmd, payload)
            except Exception:
                _LOGGER.exception("Error in tunnel callback for CMD %s", cmd)

    async def _keepalive_loop(self) -> None:
        """Periodic keepalive for tunnel connection."""
        while not self._closing:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            if self._closing:
                break
            result = await self.async_send(12, 2)
            if result is None and not self._closing:
                _LOGGER.debug("Tunnel keepalive failed, disconnecting")
                self._connected = False
                if self.on_connection_change:
                    self.on_connection_change(False)
                return


def parse_source_list(source_list_str: str) -> list[str]:
    """Parse SOURCE_LIST capability bitmap into list of source names.

    Format: "MODEL::HEX" (e.g., "LS9::f7ffffff")
    """
    try:
        hex_part = source_list_str.split("::")[-1]
        if hex_part.startswith("0x"):
            hex_part = hex_part[2:]
        bitmap = int(hex_part, 16)
    except (ValueError, IndexError):
        return []

    sources = []
    for bit, source_id in SOURCE_CAPABILITY_BITS.items():
        if bitmap & (1 << bit):
            name = SOURCE_MAP.get(source_id)
            if name and name != "None":
                sources.append(name)
    return sorted(sources)


def _parse_lssdp_response(
    data: str, addr: tuple[str, int]
) -> dict[str, Any] | None:
    """Parse an LSSDP response into a device dict."""
    lines = data.split("\r\n")
    if not lines:
        return None

    start_line = lines[0]
    if not (
        start_line.startswith("HTTP/1.1 200") or start_line.startswith("NOTIFY")
    ):
        return None

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()

    usn = headers.get("USN", "")
    if not usn:
        return None

    # USN serves as the MAC/unique identifier
    # PORT header contains the LUCI TCP port
    # TCPPORT header advertises 2020 but that's a different always-open
    # service. The Canton app always uses 50006 as the tunnel port and opens
    # it on-demand via MID_TUNNELING_START — we do the same.
    tcp_port = int(headers.get("PORT", str(DEFAULT_LUCI_PORT)))

    return {
        "host": addr[0],
        "port": tcp_port,
        "tunnel_port": DEFAULT_TUNNEL_PORT,
        "usn": usn,
        "name": headers.get("DeviceName", "Canton Device"),
        "fw_version": headers.get("FWVERSION", ""),
        "model": headers.get("CAST_MODEL", ""),
        "state": headers.get("State", "F"),
        "speaker_type": headers.get("SPEAKERTYPE", "0"),
        "source_list": headers.get("SOURCE_LIST", ""),
        "net_mode": headers.get("NETMODE", ""),
        "wifi_band": headers.get("WIFIBAND", ""),
        "mra_mode": headers.get("MRAMode", ""),
    }


async def discover_devices(
    timeout: float = DISCOVERY_TIMEOUT,
) -> list[dict[str, Any]]:
    """Discover Canton devices on the local network via LSSDP."""
    devices: dict[str, dict[str, Any]] = {}

    msearch = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {LSSDP_MULTICAST_ADDR}:{LSSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"ST: {LSSDP_ST}\r\n"
        "MX: 10\r\n"
        "\r\n"
    )

    loop = asyncio.get_running_loop()

    class LssdpProtocol(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self.transport: asyncio.DatagramTransport | None = None

        def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
            self.transport = transport

        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            try:
                text = data.decode("utf-8", errors="replace")
                device = _parse_lssdp_response(text, addr)
                if device:
                    devices[device["usn"]] = device
            except Exception:
                _LOGGER.debug("Failed to parse LSSDP response from %s", addr)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)

    try:
        transport, _protocol = await loop.create_datagram_endpoint(
            LssdpProtocol, sock=sock
        )

        msg_bytes = msearch.encode("utf-8")
        for delay in (0, 0.5, 1.5):
            if delay > 0:
                await asyncio.sleep(delay)
            transport.sendto(msg_bytes, (LSSDP_MULTICAST_ADDR, LSSDP_PORT))
            transport.sendto(msg_bytes, ("255.255.255.255", LSSDP_PORT))

        await asyncio.sleep(timeout)
    finally:
        transport.close()
        sock.close()

    return list(devices.values())


async def validate_connection(
    host: str, port: int = DEFAULT_LUCI_PORT
) -> dict[str, str] | None:
    """Validate connection to a Canton device. Returns device info or None."""
    protocol = LuciProtocol(host, port)

    try:
        if not await protocol.async_connect():
            return None

        name_resp = await protocol.async_send(MID_DEVICE_NAME, CMD_GET)
        device_name = name_resp.payload if name_resp else "Canton Device"

        await protocol.async_disconnect()

        return {
            "device_name": device_name,
            "host": host,
            "port": str(port),
        }
    except Exception as err:
        _LOGGER.debug("Validation failed for %s:%s: %s", host, port, err)
        try:
            await protocol.async_disconnect()
        except Exception:
            pass
        return None
