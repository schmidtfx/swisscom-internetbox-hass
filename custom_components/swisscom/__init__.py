"""The Simple Integration integration."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, KEY_COORDINATOR, KEY_ROUTER, PLATFORMS
from .router import SwisscomInternetbox

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Simple Integration component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Simple Integration from a config entry."""

    router = SwisscomInternetbox(hass, entry)
    await router.async_setup()

    hass.data.setdefault(DOMAIN, {})

    entry.async_on_unload(entry.add_update_listener(update_listener))

    async def async_update_devices() -> bool:
        if router.track_devices:
            return await router.async_update_device_trackers()
        return False

    coordinator = DataUpdateCoordinator(
        hass, 
        _LOGGER,
        name=f"Internetbox Devices",
        update_method=async_update_devices,
        update_interval=SCAN_INTERVAL,
    )

    if router.track_devices:
        await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        KEY_ROUTER: router,
        KEY_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    router = hass.data[DOMAIN][entry.entry_id][KEY_ROUTER]

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    if not router.track_devices:
        router_id = None
        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        for device in devices:
            if device.via_device_id is None:
                router_id = device.id
                continue
            device_registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)

        entity_registry = er.async_get(hass)
        entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        for entity_entry in entries:
            if entity_entry.device_id is not router_id:
                entity_registry.async_remove(entity_entry.entity_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a device from a config entry."""
    router = hass.data[DOMAIN][config_entry.entry_id][KEY_ROUTER]

    device_mac = None
    for connection in device_entry.connections:
        if connection[0] == dr.CONNECTION_NETWORK_MAC:
            device_mac = connection[1]
            break

    if device_mac is None:
        return False

    if device_mac not in router.devices:
        return True

    return not router.devices[device_mac]["Active"]