"""The Simple Integration integration."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok