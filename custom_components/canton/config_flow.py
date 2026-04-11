"""Config flow for Canton Smart Sound integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_FW_VERSION,
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_SOURCE_LIST_MODE,
    CONF_TUNNEL_PORT,
    DEFAULT_LUCI_PORT,
    DEFAULT_TUNNEL_PORT,
    DOMAIN,
    MODEL_AMP_51,
    MODEL_CONNECT_51,
    MODEL_SOUNDBAR_10,
    MODEL_SOUNDBAR_9,
    MODEL_SOUNDBOX_3,
    MODEL_SOUNDDECK_100,
    SOURCE_MODE_INPUTS,
    SOURCE_MODE_PRESETS,
)

_CANTON_MODELS = {
    MODEL_SOUNDBAR_10,
    MODEL_SOUNDBAR_9,
    MODEL_SOUNDDECK_100,
    MODEL_SOUNDBOX_3,
    MODEL_CONNECT_51,
    MODEL_AMP_51,
}
from .protocol import discover_devices, parse_source_list, validate_connection

_LOGGER = logging.getLogger(__name__)

MENU_SCAN = "scan"
MENU_MANUAL = "manual"


class CantonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Canton Smart Sound."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return CantonOptionsFlow(config_entry)

    def __init__(self) -> None:
        self._discovered_devices: list[dict[str, Any]] = []
        self._selected_device: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - menu selection."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[MENU_SCAN, MENU_MANUAL],
        )

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Scan for devices on the network."""
        if user_input is not None:
            # User selected a device
            usn = user_input["device"]
            for device in self._discovered_devices:
                if device["usn"] == usn:
                    self._selected_device = device
                    return await self._async_create_from_device(device)

            return self.async_abort(reason="device_not_found")

        # Perform discovery
        self._discovered_devices = await discover_devices()

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        # Build selection list
        options = [
            SelectOptionDict(
                value=device["usn"],
                label=f"{device['name']} ({device['model']}) - {device['host']}",
            )
            for device in self._discovered_devices
        ]

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual device entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_LUCI_PORT)

            result = await validate_connection(host, port)
            if result is None:
                errors["base"] = "cannot_connect"
            else:
                # Try to find device via LSSDP for USN
                devices = await discover_devices(timeout=3)
                device = next(
                    (d for d in devices if d["host"] == host), None
                )

                if device:
                    return await self._async_create_from_device(device)

                # No LSSDP response, use IP as unique ID fallback
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=result["device_name"],
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_TUNNEL_PORT: DEFAULT_TUNNEL_PORT,
                        CONF_MODEL: "",
                        CONF_FW_VERSION: "",
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): TextSelector(),
                    vol.Optional(CONF_PORT, default=DEFAULT_LUCI_PORT): int,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery of a Canton device."""
        host = discovery_info.host
        props = discovery_info.properties or {}
        model = props.get("md", "")
        friendly_name = props.get("fn", "Canton Device")
        cast_uuid = props.get("id", "")

        # Ignore non-Canton Chromecast devices (Nest speakers, TVs, etc.)
        if model not in _CANTON_MODELS:
            return self.async_abort(reason="not_canton_device")

        # Abort if host is already configured (covers manually-added entries
        # from before auto-discovery existed).
        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == host:
                return self.async_abort(reason="already_configured")

        # Try to fetch LSSDP metadata to get the USN (canonical unique_id).
        devices = await discover_devices(timeout=2)
        device = next((d for d in devices if d["host"] == host), None)

        if device:
            unique_id = device["usn"]
            self._selected_device = device
        elif cast_uuid:
            unique_id = f"chromecast_{cast_uuid}"
            self._selected_device = {
                "host": host,
                "port": DEFAULT_LUCI_PORT,
                "tunnel_port": DEFAULT_TUNNEL_PORT,
                "usn": unique_id,
                "name": friendly_name,
                "model": model,
                "fw_version": "",
            }
        else:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self.context["title_placeholders"] = {
            "name": self._selected_device["name"],
            "model": self._selected_device.get("model") or "Canton",
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered device before creating the entry."""
        assert self._selected_device is not None

        if user_input is not None:
            return await self._async_create_from_device(self._selected_device)

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._selected_device["name"],
                "model": self._selected_device.get("model") or "Canton Smart Sound",
                "host": self._selected_device["host"],
            },
        )

    async def _async_create_from_device(
        self, device: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create a config entry from a discovered device."""
        await self.async_set_unique_id(device["usn"])
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: device["host"]}
        )

        # TCPPORT from LSSDP is the tunnel port
        tunnel_port = int(device.get("tunnel_port", DEFAULT_TUNNEL_PORT))

        return self.async_create_entry(
            title=device["name"],
            data={
                CONF_HOST: device["host"],
                CONF_PORT: device["port"],
                CONF_TUNNEL_PORT: tunnel_port,
                CONF_MODEL: device["model"],
                CONF_FW_VERSION: device["fw_version"],
                "wifi_band": device.get("wifi_band", ""),
            },
        )


class CantonOptionsFlow(OptionsFlow):
    """Handle Canton options."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(
            CONF_SOURCE_LIST_MODE, SOURCE_MODE_INPUTS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOURCE_LIST_MODE, default=current
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=SOURCE_MODE_INPUTS,
                                    label="Inputs",
                                ),
                                SelectOptionDict(
                                    value=SOURCE_MODE_PRESETS,
                                    label="Presets",
                                ),
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )
