from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEVICE_ICONS, DOMAIN, KEY_COORDINATOR, KEY_ROUTER
from .entity import SwisscomInternetboxDeviceEntity
from .router import SwisscomInternetbox


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """
    Setup device tracker for Swisscom platform
    """
    
    router = hass.data[DOMAIN][entry.entry_id][KEY_ROUTER]
    coordinator = hass.data[DOMAIN][entry.entry_id][KEY_COORDINATOR]
    tracked = set()
    
    @callback
    def new_device_callback() -> None:
        """
        Add new device if needed
        """
        if not coordinator.data:
            return
        
        new_entities = []
        for mac, device in router.devices.items():
            if mac in tracked:
                continue

            new_entities.append("")
            tracked.add(mac)

        async_add_entities(new_entities)
    
    entry.async_on_unload(coordinator.async_add_listener(new_device_callback))

    coordinator.data = True
    new_device_callback()


class SwisscomInternetboxScannerEntity(SwisscomInternetboxDeviceEntity, ScannerEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, router: SwisscomInternetbox, device: dict[str, Any]) -> None:
        super().__init__(coordinator, router, device)
        self._hostname = self.get_hostname()
        self._icon = DEVICE_ICONS.get(device["device_type"], "mdi:help-network")
        self._attr_name = self._device_name

    def get_hostname(self) -> str | None:
        if (hostname := self._device["name"]) == "--":
            return None
        return hostname
    

