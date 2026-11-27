"""Shared fixtures: a fake Canton device on localhost and fast protocol timing."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

# Import before the hass fixture puts its own testing_config first on sys.path
from custom_components import canton
from custom_components.canton import protocol, tunnel_manager

from .fake_device import FakeDevice


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture(autouse=True)
def fast_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink keepalive, timeouts and backoff so outages show up in milliseconds."""
    monkeypatch.setattr(protocol, "KEEPALIVE_INTERVAL", 0.3)
    monkeypatch.setattr(protocol, "COMMAND_TIMEOUT", 0.3)
    monkeypatch.setattr(protocol, "CLOSE_TIMEOUT", 0.5)
    monkeypatch.setattr(tunnel_manager, "SHARED_POLL_INTERVAL", 0.3)
    monkeypatch.setattr(tunnel_manager, "CLOSE_TIMEOUT", 0.5)
    monkeypatch.setattr(canton, "RECONNECT_DELAYS", [0.3])


@pytest.fixture
async def device(socket_enabled: None) -> AsyncIterator[FakeDevice]:
    """A reachable fake device."""
    dev = FakeDevice()
    await dev.start()
    yield dev
    await dev.stop()

