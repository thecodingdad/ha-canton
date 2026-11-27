"""Fake Canton device: LUCI and tunnel servers on localhost.

Answers the commands the integration sends during setup and polling. The tunnel
accepts a single connection at a time, like the real device: a new connection
kicks the previous one.
"""

from __future__ import annotations

import asyncio
import struct

LUCI_HEADER_SIZE = 10
TUNNEL_HEADER_SIZE = 7

TUNNEL_RESPONSES: dict[tuple[int, int], bytes] = {
    (6, 2): bytes([1]),  # standby: on
    (2, 2): bytes([1, 1, 1, 2, 2, 1]),  # source info
    (7, 2): bytes([0] * 11),  # presets
    (3, 2): bytes([1, 1, 1]),  # source / play mode
    (4, 2): bytes([0, 0, 0, 10]),  # eq
    (12, 2): bytes([20, 70]),  # volume
    (9, 2): bytes([0]),  # mute
}
TUNNEL_MENU_GET = (5, 2)
MID_VOLUME = 64


class FakeDevice:
    """LUCI + tunnel server that can drop off the network and come back."""

    def __init__(self) -> None:
        self.luci_port = 0
        self.tunnel_port = 0
        # Accept and read, but never answer (hung firmware, packets dropped)
        self.silent = False
        self._servers: list[asyncio.Server] = []
        self._writers: set[asyncio.StreamWriter] = set()
        self._tunnel_writer: asyncio.StreamWriter | None = None

    async def start(self) -> None:
        """Listen on the LUCI and tunnel ports (the same ones after a restart)."""
        luci = await asyncio.start_server(self._luci, "127.0.0.1", self.luci_port)
        tunnel = await asyncio.start_server(
            self._tunnel, "127.0.0.1", self.tunnel_port
        )
        self.luci_port = luci.sockets[0].getsockname()[1]
        self.tunnel_port = tunnel.sockets[0].getsockname()[1]
        self._servers = [luci, tunnel]

    async def stop(self) -> None:
        """Stop listening and drop all connections."""
        await self._stop_listening()
        self._drop_connections()

    async def go_unreachable(self) -> None:
        """Device vanishes: open connections get no answers, new ones fail."""
        self.silent = True
        await self._stop_listening()

    async def reboot_away(self) -> None:
        """Device restarts: open connections are reset, new ones fail."""
        await self.stop()

    async def hang(self) -> None:
        """Firmware hangs: TCP connections are accepted, nothing is answered."""
        self.silent = True

    async def come_back(self) -> None:
        """Device is back — after a restart it knows nothing of old connections."""
        self._drop_connections()
        self.silent = False
        if not self._servers:
            await self.start()

    async def _stop_listening(self) -> None:
        for server in self._servers:
            server.close()
        self._servers = []

    def _drop_connections(self) -> None:
        for writer in list(self._writers):
            writer.transport.abort()
        self._writers.clear()

    async def _luci(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(LUCI_HEADER_SIZE)
                # Requests are little-endian, responses big-endian
                _, cmd_type, mid, _, _, plen = struct.unpack("<HBHBHH", header)
                if plen:
                    await reader.readexactly(plen)
                if self.silent:
                    continue
                payload = b"20" if mid == MID_VOLUME else b""
                writer.write(
                    struct.pack(">HBHBHH", 0, cmd_type, mid, 0, 0, len(payload))
                    + payload
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    async def _tunnel(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if self._tunnel_writer is not None:
            self._tunnel_writer.transport.abort()
        self._tunnel_writer = writer
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(TUNNEL_HEADER_SIZE)
                cmd = (header[3], header[4])
                plen = (header[5] << 8) | header[6]
                payload = await reader.readexactly(plen) if plen else b""
                if self.silent:
                    continue
                if cmd == TUNNEL_MENU_GET:
                    resp = payload[:4] + bytes([0])
                else:
                    resp = TUNNEL_RESPONSES.get(cmd)
                if resp is None:
                    continue
                writer.write(
                    bytes(
                        [0xFF, 0xAA, 0x00, *cmd, len(resp) >> 8, len(resp) & 0xFF]
                    )
                    + resp
                )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            if self._tunnel_writer is writer:
                self._tunnel_writer = None
            writer.close()
