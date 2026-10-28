from abc import abstractmethod

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HostEntry
from .const import DOMAIN
from .coordinator import InternetBoxDataCoordinator


def router_identifier(entry: ConfigEntry) -> str:
    """Return the device registry identifier of the router itself.

    Every box-level entity groups under this, and the tracked device entities
    point their ``via_device`` at it, so the two must agree -- including on a
    box that reported no serial number and so left the entry without a
    unique id.
    """
    return entry.unique_id or entry.entry_id


class InternetBoxDeviceEntity(CoordinatorEntity[InternetBoxDataCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: InternetBoxDataCoordinator,
        entry: ConfigEntry,
        device: HostEntry,
    ):
        super().__init__(coordinator)

        self._device = device
        self._attr_unique_id = device.mac
        self._attr_device_info = dr.DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, device.mac)},
            default_name=self._device_name,
            default_model=device.type,
            via_device=(DOMAIN, router_identifier(entry)),
        )

    @abstractmethod
    @callback
    def async_update_device(self) -> None:
        pass

    @callback
    def _handle_coordinator_update(self):
        self.async_update_device()
        super()._handle_coordinator_update()

    @property
    def _device_name(self):
        device = self._device
        if device is None:
            return None
        name = device.hostname
        if not name or name == "--":
            # Fall back to the MAC so the entity always has a usable name, even
            # for a host the box reports without hostname or IP.
            return device.ip or device.mac
        return name

    @property
    def _is_active(self):
        return bool(self._device and self._device.active)

    @property
    def _mac(self):
        return self._device.mac if self._device else None
