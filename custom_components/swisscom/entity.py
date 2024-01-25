from __future__ import annotations

from abc import abstractmethod

from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .router import SwisscomInternetbox


class SwisscomInternetboxDeviceEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, router: SwisscomInternetbox, device: dict):
        super().__init__(coordinator)
        self._router = router
        self._device = device

        self._attr_unique_id = self._mac
        self._attr_device_info = dr.DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, self._mac)},
            default_name=self._device_name,
            default_model=device["DeviceType"],
            via_device=(DOMAIN, router.unique_id),
        )
        print(self._attr_device_info)

    @abstractmethod
    @callback
    def async_update_device(self) -> None:
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_update_device()
        super()._handle_coordinator_update()
    
    @property
    def _device_name(self):
        name = self._device["Name"]
        if not name or name == "--":
            return self._device["Key"]
        return name
    
    @property
    def _is_active(self):
        return self._device["Active"]
    
    @property
    def _mac(self):
        return self._device["mac"]
        