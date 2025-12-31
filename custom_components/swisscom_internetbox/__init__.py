from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import HostEntry, InternetBoxClient
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import InternetBoxDataCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = InternetBoxClient(
        hass,
        host=entry.data[CONF_HOST],
        password=entry.data[CONF_PASSWORD],
        ssl=entry.data[CONF_SSL],
        verify_ssl=entry.data[CONF_VERIFY_SSL],
    )
    coordinator = InternetBoxDataCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a device from a config entry."""
    coordinator: InternetBoxDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    data = coordinator.data or {}

    device_mac = None
    for connection in device_entry.connections:
        if connection[0] == dr.CONNECTION_NETWORK_MAC:
            device_mac = connection[1]
            break

    if device_mac is None:
        return False

    device: HostEntry = None
    for d in data.get("devices", []):
        if d.mac == device_mac:
            device = d
            break

    if not device:
        return True

    return not device.active
