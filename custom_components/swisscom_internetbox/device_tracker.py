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

            new_entities.append(SwisscomInternetboxScannerEntity(coordinator, router, device))
            tracked.add(mac)

        async_add_entities(new_entities)
    
    entry.async_on_unload(coordinator.async_add_listener(new_device_callback))

    coordinator.data = True
    new_device_callback()


class SwisscomInternetboxScannerEntity(SwisscomInternetboxDeviceEntity, ScannerEntity):

    _attr_has_entity_name = False

    def __init__(self, coordinator: DataUpdateCoordinator, router: SwisscomInternetbox, device: dict[str, Any]) -> None:
        super().__init__(coordinator, router, device)
        self._hostname = self.get_hostname()
        self._icon = DEVICE_ICONS.get(device["DeviceType"], "mdi:help-network")
        self._attr_name = self._device_name

    def get_hostname(self) -> str | None:
        if (hostname := self._device["Name"]) == "--":
            return None
        return hostname
    
    def async_update_device(self) -> None:
        self._device = self._router.devices[self._mac]

    @property
    def is_connected(self) -> bool:
        return self._is_active
    
    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER
    
    @property
    def mac_address(self) -> str:
        return self._mac
    
    @property
    def ip_address(self) -> str:
        if "IPAddress" in self._device:
            return self._device["IPAddress"]
        return None
    
    @property
    def hostname(self) -> str:
        return self.get_hostname()
    