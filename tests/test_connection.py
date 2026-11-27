"""Connection loss, reconnect and unload (issue #3)."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .common import is_unavailable, setup_entry, unload_entry, wait_until
from .fake_device import FakeDevice


@pytest.mark.parametrize("outage", ["go_unreachable", "reboot_away"])
async def test_reconnects_after_outage(
    hass: HomeAssistant, device: FakeDevice, outage: str
) -> None:
    """Entities go unavailable during an outage and recover once the device is back."""
    entry, entity_id = await setup_entry(hass, device)
    hub = entry.runtime_data
    assert not is_unavailable(hass, entity_id)

    await getattr(device, outage)()
    assert await wait_until(lambda: is_unavailable(hass, entity_id)), (
        "outage not detected"
    )

    await device.come_back()
    assert await wait_until(lambda: not is_unavailable(hass, entity_id)), (
        "no reconnect after the device came back"
    )
    assert hub.is_connected
    assert hub.tunnel_mode == "exclusive"

    # The next outage is detected as well
    await device.reboot_away()
    assert await wait_until(lambda: is_unavailable(hass, entity_id))
    await device.come_back()
    assert await wait_until(lambda: not is_unavailable(hass, entity_id))

    await unload_entry(hass, entry)


async def test_hung_firmware_detected(hass: HomeAssistant, device: FakeDevice) -> None:
    """A device that still accepts TCP but stops answering is detected too."""
    entry, entity_id = await setup_entry(hass, device)

    await device.hang()
    assert await wait_until(lambda: is_unavailable(hass, entity_id))

    await device.come_back()
    assert await wait_until(lambda: not is_unavailable(hass, entity_id))

    await unload_entry(hass, entry)


@pytest.mark.parametrize("outage", ["go_unreachable", "reboot_away", "hang"])
async def test_reload_during_outage(
    hass: HomeAssistant, device: FakeDevice, outage: str
) -> None:
    """Reloading while the device is gone ends in setup retry, never stuck in unload."""
    entry, _ = await setup_entry(hass, device)

    await getattr(device, outage)()
    await asyncio.sleep(1.5)  # keepalives notice the loss

    await asyncio.wait_for(hass.config_entries.async_reload(entry.entry_id), 15)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY

    await unload_entry(hass, entry)


async def test_tunnel_shared_with_other_controller(
    hass: HomeAssistant, device: FakeDevice
) -> None:
    """When another controller takes the tunnel, the device stays usable."""
    entry, entity_id = await setup_entry(hass, device)
    hub = entry.runtime_data
    assert hub.tunnel_mode == "exclusive"

    # Canton app takes the single tunnel slot
    _, app = await asyncio.open_connection("127.0.0.1", device.tunnel_port)
    assert await wait_until(lambda: hub.tunnel_mode == "shared", 3)
    await asyncio.sleep(1.0)  # a few shared polls
    assert hub.is_connected
    assert not is_unavailable(hass, entity_id)

    app.close()
    await unload_entry(hass, entry)
