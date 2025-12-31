from __future__ import annotations

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DEVICE_ICONS
from .coordinator import InternetBoxDataCoordinator
from .api import HostEntry
from .entity import InternetBoxDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: InternetBoxDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    tracked = set()

    @callback
    def new_device_callback() -> None:
        """
        Add new device if needed
        """
        if not coordinator.data:
            return
        
        new_entities = []
        for dev in coordinator.data.get("devices", []):
            if not dev.mac or dev.mac in tracked:
                continue

            new_entities.append(InternetBoxDeviceTracker(coordinator, entry, dev))
            tracked.add(dev.mac)

        async_add_entities(new_entities)
    
    entry.async_on_unload(coordinator.async_add_listener(new_device_callback))
    new_device_callback()


class InternetBoxDeviceTracker(InternetBoxDeviceEntity, ScannerEntity):
    def __init__(self, coordinator: InternetBoxDataCoordinator, entry: ConfigEntry, device: HostEntry):
        super().__init__(coordinator, entry, device)
        self._attr_name = self._device_name
        self._attr_icon = DEVICE_ICONS.get(device.type.lower(), "mdi:help-network")

    @callback
    def async_update_device(self):
        self._device = self._find()

    @property
    def is_connected(self) -> bool:
        return self._device.active
    
    @property
    def source_type(self):
        return SourceType.ROUTER
    
    @property
    def ip_address(self) -> str | None:
        return self._device.ip
    
    @property
    def mac_address(self) -> str:
        return self._mac
    
    @property
    def hostname(self) -> str | None:
        return self._device.hostname
    
    def _find(self) -> HostEntry | None:
        for d in (self.coordinator.data.get("devices") or []):
            if (d.mac or "").lower() == self._mac.lower():
                return d
        return None
