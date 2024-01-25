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
    def __init__(self, coordinator: DataUpdateCoordinator, router: SwisscomInternetbox, device: dict):
        super().__init__(coordinator)
        self._router = router
        self._device = device

    @abstractmethod
    @callback
    def async_update_device(self) -> None:
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_update_device()
        return super()._handle_coordinator_update()