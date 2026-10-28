from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InternetBoxDataCoordinator
from .entity import router_identifier

# NMC:getWANStatus reports LinkState as a free-form string. These are the
# values this firmware family uses for a working uplink; anything else that is
# a non-empty string counts as down, so automations get a usable boolean rather
# than an unknown state on a value we have not seen before.
LINK_STATES_UP = frozenset({"up", "connected", "bound"})

WAN_CONNECTIVITY = BinarySensorEntityDescription(
    key="wan_connectivity",
    name="WAN connectivity",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)


def _link_state_is_up(link_state: object) -> bool | None:
    """Map a LinkState string to a boolean, or None when the box said nothing."""
    if not isinstance(link_state, str) or not link_state.strip():
        return None
    return link_state.strip().lower() in LINK_STATES_UP


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: InternetBoxDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([InternetBoxWanConnectivity(coordinator, entry)])


class InternetBoxWanConnectivity(
    CoordinatorEntity[InternetBoxDataCoordinator], BinarySensorEntity
):
    entity_description = WAN_CONNECTIVITY

    def __init__(self, coordinator: InternetBoxDataCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{WAN_CONNECTIVITY.key}"

        # As in sensor.py: pin only the identifier, so the device's details
        # stay owned by async_update_router_device and nothing goes stale here.
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, router_identifier(entry))}
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        wan_info = data.get("wan_info") or {}
        wan_data = wan_info.get("data") or {}
        return _link_state_is_up(wan_data.get("LinkState"))
