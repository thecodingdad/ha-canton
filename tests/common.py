"""Helpers for setting up the integration against the fake device."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.canton.const import DOMAIN

from .fake_device import FakeDevice


async def setup_entry(
    hass: HomeAssistant, device: FakeDevice
) -> tuple[MockConfigEntry, str]:
    """Set up a config entry for the fake device, return it and the media player."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Smart Connect",
        unique_id="CC9093120230",
        data={
            "host": "127.0.0.1",
            "port": device.luci_port,
            "tunnel_port": device.tunnel_port,
            "model": "",
            "fw_version": "1",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_id = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "media_player"
    )
    return entry, entity_id


async def unload_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Unload the entry — must finish quickly, whatever state the device is in."""
    assert await asyncio.wait_for(
        hass.config_entries.async_unload(entry.entry_id), timeout=10
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def wait_until(predicate: Callable[[], bool], timeout: float = 5) -> bool:
    """Poll a condition until it holds or the timeout expires."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


def is_unavailable(hass: HomeAssistant, entity_id: str) -> bool:
    """Return True if the entity is unavailable."""
    return hass.states.get(entity_id).state == STATE_UNAVAILABLE
