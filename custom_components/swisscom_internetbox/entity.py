from __future__ import annotations

from abc import abstractmethod

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .router import SwisscomInternetbox


class SwisscomBaseEntity(CoordinatorEntity):
    """
    SwisscomBaseEntity is the base entity for all Swisscom entities
    """

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._coordinator = coordinator

    @property
    def unique_id(self):
        # https://developers.home-assistant.io/docs/entity_registry_index
        return self._coordinator.get_mac()
    
    @property
    def device_info(self):
        # https://developers.home-assistant.io/docs/device_registry_index
        return {
            "identifiers": {(DOMAIN, self._coordinator.get_mac())},
            "name": self._coordinator.get_device_name(),
            "model": self._coordinator.get_model(),
            "manufacturer": "Swisscom",
            "configuration_url": f"https://{self._coordinator.get_ip_address()}",
            "sw_version": self._coordinator.get_firmware_version(),
        }
    
    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.  False if entity pushes its state to HA"""
        return True


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
        return self._device["PhysAddress"]
        