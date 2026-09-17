"""Adaptive tunnel access for Canton Smart Sound devices.

Canton devices accept only ONE connection on the tunnel port at a time — a second
controller (Canton app, Unfolded Circle Remote, another HA instance) takes the slot
over and the previous connection is closed by the device.

The manager therefore works in two modes:

* ``EXCLUSIVE`` — the tunnel is held permanently. State changes arrive as push
  messages, commands are sent on the open connection. Used while nobody else wants
  the tunnel.
* ``SHARED`` — entered as soon as the permanent connection is taken away. Each
  command and each state poll opens a short session (~200 ms) and closes it again,
  so the other controller can work in between. After a backoff the manager tries to
  take the tunnel back.

Connecting never sends ``MID_TUNNELING_START`` unless the plain connect fails: the
device keeps the port open, and the start command would kick whoever is connected.

"""

import asyncio
import logging
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any, AsyncIterator, Awaitable, Callable

from .const import (
    EXCLUSIVE_STABLE_SECONDS,
    SHARED_MODE_BACKOFF,
    SHARED_POLL_INTERVAL,
)
from .protocol import LuciProtocol, TunnelProtocol

_LOG = logging.getLogger(__name__)


class TunnelMode(StrEnum):
    """How the integration uses the device's single tunnel slot."""

    EXCLUSIVE = "exclusive"
    """Tunnel held permanently — instant push updates, blocks other controllers."""

    SHARED = "shared"
    """Short on-demand sessions plus polling — coexists with other controllers."""


class TunnelManager:
    """Manage tunnel access, switching between exclusive and shared mode."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        host: str,
        port: int,
        luci: LuciProtocol,
        on_message: Callable[[tuple[int, int], bytes], None],
        poll: Callable[[], Awaitable[None]],
        log_id: str,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """
        Create the manager.

        :param host: Device address
        :param port: Tunnel port
        :param luci: Connected LUCI protocol, used for the tunnel start fallback
        :param on_message: Callback for push messages on the permanent connection
        :param poll: Coroutine reading the device state, called in shared mode
        :param log_id: Identifier used in log messages
        :param loop: Event loop
        """
        self._host = host
        self._port = port
        self._luci = luci
        self._on_message = on_message
        self._poll = poll
        self._log_id = log_id
        self._loop = loop or asyncio.get_event_loop()

        self._mode = TunnelMode.EXCLUSIVE
        self._tunnel: TunnelProtocol | None = None
        self._lock = asyncio.Lock()
        self._available = False
        self._poll_task: asyncio.Task | None = None
        self._mode_task: asyncio.Task | None = None
        self._shared_level = 0
        self._exclusive_since = 0.0
        self._stopped = False

    @property
    def mode(self) -> TunnelMode:
        """Return the current tunnel mode."""
        return self._mode

    @property
    def available(self) -> bool:
        """Return True if the last tunnel access succeeded."""
        return self._available

    async def start(self) -> None:
        """Take the tunnel if it is free, otherwise start sharing it."""
        self._stopped = False
        async with self._lock:
            if not await self._open_persistent():
                await self._enter_shared()

    async def stop(self) -> None:
        """Release the tunnel and stop all background tasks."""
        self._stopped = True
        await self._cancel(self._poll_task)
        await self._cancel(self._mode_task)
        self._poll_task = None
        self._mode_task = None

        if self._tunnel:
            self._tunnel.on_connection_change = None
            await self._tunnel.async_disconnect()
            self._tunnel = None
        self._available = False

    @asynccontextmanager
    async def session(self) -> AsyncIterator[TunnelProtocol | None]:
        """
        Provide a connected tunnel for one operation.

        Yields the permanent connection in exclusive mode, a short-lived session in
        shared mode, or None if the tunnel cannot be reached.
        """
        async with self._lock:
            if self._tunnel and self._tunnel.is_connected:
                yield self._tunnel
                return

            session = TunnelProtocol(self._host, self._port, self._luci)
            # No connection callback: closing this session is expected, not a takeover
            session.on_message = self._on_message
            if not await session.async_connect(keepalive=False):
                self._available = False
                _LOG.debug("[%s] Tunnel session failed", self._log_id)
                yield None
                return

            self._available = True
            try:
                yield session
            finally:
                await session.async_disconnect()

    # --- internals -----------------------------------------------------------

    async def _open_persistent(self) -> bool:
        """Open the permanent connection used in exclusive mode."""
        tunnel = TunnelProtocol(self._host, self._port, self._luci)
        tunnel.on_message = self._on_message
        tunnel.on_connection_change = self._on_tunnel_connection_change

        if not await tunnel.async_connect():
            return False

        self._tunnel = tunnel
        self._available = True
        self._mode = TunnelMode.EXCLUSIVE
        self._exclusive_since = self._loop.time()
        _LOG.debug("[%s] Holding tunnel exclusively", self._log_id)
        return True

    def _on_tunnel_connection_change(self, connected: bool) -> None:
        """React to the permanent connection being taken over by someone else."""
        if connected or self._stopped:
            return
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self._switch_to_shared())
        )

    async def _switch_to_shared(self) -> None:
        """Give up the permanent connection and poll through short sessions."""
        if self._stopped or self._mode is TunnelMode.SHARED:
            return
        async with self._lock:
            await self._enter_shared()

    async def _enter_shared(self) -> None:
        """Enter shared mode. Caller must hold the lock."""
        # A permanent connection that held for a while counts as success,
        # so the next conflict starts with the short backoff again.
        if (
            self._exclusive_since
            and self._loop.time() - self._exclusive_since >= EXCLUSIVE_STABLE_SECONDS
        ):
            self._shared_level = 0

        self._mode = TunnelMode.SHARED
        if self._tunnel:
            self._tunnel.on_connection_change = None
            await self._tunnel.async_disconnect()
            self._tunnel = None

        delay = SHARED_MODE_BACKOFF[
            min(self._shared_level, len(SHARED_MODE_BACKOFF) - 1)
        ]
        self._shared_level += 1
        _LOG.info(
            "[%s] Tunnel is used by another controller — sharing it "
            "(polling every %ss, retrying exclusive access in %ss)",
            self._log_id,
            SHARED_POLL_INTERVAL,
            delay,
        )

        if self._poll_task is None or self._poll_task.done():
            self._poll_task = self._loop.create_task(self._poll_loop())
        await self._cancel(self._mode_task)
        self._mode_task = self._loop.create_task(self._retry_exclusive(delay))

    async def _retry_exclusive(self, delay: float) -> None:
        """Try to take the tunnel back after the given delay."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if self._stopped or self._mode is not TunnelMode.SHARED:
            return

        async with self._lock:
            if await self._open_persistent():
                _LOG.info(
                    "[%s] Tunnel is free again — back to exclusive mode", self._log_id
                )
                poll_task, self._poll_task = self._poll_task, None
                await self._cancel(poll_task)
                return
            # Still taken: stay shared, next attempt with a longer delay
            await self._enter_shared()

    async def _poll_loop(self) -> None:
        """Refresh the device state regularly while sharing the tunnel."""
        while not self._stopped:
            await asyncio.sleep(SHARED_POLL_INTERVAL)
            try:
                await self._poll()
            except Exception:  # pylint: disable=broad-exception-caught
                _LOG.exception("[%s] State poll failed", self._log_id)

    @staticmethod
    async def _cancel(task: Any) -> None:
        """Cancel and await a task, ignoring cancellation."""
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
