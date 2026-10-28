from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import InternetBoxDataCoordinator

# A diagnostics dump gets pasted into a public issue, so everything that
# identifies the household goes: the credentials, the box's own identity, and
# the name, address and MAC of every device on the LAN. What is left is what a
# bug report actually needs -- model, firmware, link type, and the WAN counter
# probe that varies between DSL and fibre.
TO_REDACT = {
    "password",
    "host",
    "DNSServers",
    "ExternalIPAddress",
    "HostName",
    "IPAddress",
    "IPAddress6",
    "KeyPassPhrase",
    "MACAddress",
    "Name",
    "PhysAddress",
    "RemoteGateway",
    "SSID",
    "SerialNumber",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: InternetBoxDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    client = coordinator.client
    data = coordinator.data or {}
    devices = data.get("devices") or []

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "device_info": async_redact_data(data.get("device_info") or {}, TO_REDACT),
        "wan_info": async_redact_data(data.get("wan_info") or {}, TO_REDACT),
        "wan_stats": {
            # Which object answered is the first thing to check on a DSL vs
            # fibre report, and the replies show why the others did not.
            "path": client.wan_stats_path,
            "counters": data.get("wan_stats") or {},
            "rates": data.get("wan_rates") or {},
            "replies": async_redact_data(client.last_raw_wan_stats or {}, TO_REDACT),
        },
        "devices": {
            "count": len(devices),
            "online": sum(1 for device in devices if device.active),
            "payload": async_redact_data(client.last_raw_devices or [], TO_REDACT),
        },
    }
