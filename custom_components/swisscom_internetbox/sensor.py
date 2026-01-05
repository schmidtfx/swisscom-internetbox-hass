from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InternetBoxDataCoordinator


@dataclass(frozen=True)
class InternetBoxSensorDescription(SensorEntityDescription):
    key: str


SENSORS: tuple[InternetBoxSensorDescription, ...] = (
    InternetBoxSensorDescription(
        key="connected_devices", name="Connected devices", icon="mdi:lan-connect"
    ),
    InternetBoxSensorDescription(
        key="online_devices", name="Online devices", icon="mdi:lan-check"
    ),
    InternetBoxSensorDescription(
        key="sw_version", name="Software version", icon="mdi:router-wireless", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    InternetBoxSensorDescription(key="model", name="Model", icon="mdi:router", entity_category=EntityCategory.DIAGNOSTIC,),
    InternetBoxSensorDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-time-four",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        entity_registry_enabled_default=False,
    ),
    InternetBoxSensorDescription(
        key="external_ip", name="External IP", icon="mdi:ip-network", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    InternetBoxSensorDescription(
        key="wan_rx",
        name="WAN received",
        icon="mdi:download",
        unit_of_measurement="B",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    InternetBoxSensorDescription(
        key="wan_tx",
        name="WAN sent",
        icon="mdi:upload",
        unit_of_measurement="B",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    InternetBoxSensorDescription(key="link_state", name="Link state", icon="mdi:link"),
    InternetBoxSensorDescription(key="link_type", name="Link type", icon="mdi:link", entity_category=EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: InternetBoxDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [InternetBoxSensor(coordinator, entry.entry_id, desc) for desc in SENSORS]
    )


class InternetBoxSensor(CoordinatorEntity[InternetBoxDataCoordinator], SensorEntity):
    entity_description: InternetBoxSensorDescription

    def __init__(
        self,
        coordinator: InternetBoxDataCoordinator,
        entry_id: str,
        description: InternetBoxSensorDescription,
    ):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        
        # Group all sensors under the main router device
        self._attr_device_info = self._get_device_info(entry_id)

    def _get_device_info(self, entry_id: str):
        """Create device info for the main router to group all sensors."""
        data = self.coordinator.data or {}
        device_info = data.get("device_info") or {}
        
        # Use the router's serial number or MAC as identifier if available
        serial_number = device_info.get("SerialNumber")
        mac_address = device_info.get("MACAddress")
        
        # Create device identifier
        device_identifier = serial_number or mac_address or entry_id
        
        return {
            "identifiers": {(DOMAIN, device_identifier)},
            "name": device_info.get("ModelName", "Swisscom InternetBox"),
            "manufacturer": "Swisscom",
            "model": device_info.get("ModelName", "InternetBox"),
            "sw_version": device_info.get("SoftwareVersion"),
            "configuration_url": f"http://{self.coordinator._client.host}",
        }

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        device_info = data.get("device_info") or {}
        wan_info = data.get("wan_info") or {}
        dsl_info = data.get("dsl_info") or {}

        if self.entity_description.key == "connected_devices":
            return len(devices)

        if self.entity_description.key == "online_devices":
            actives = [d for d in devices if d.active]
            return len(actives) if actives else None

        if self.entity_description.key == "sw_version":
            return device_info.get("SoftwareVersion")

        if self.entity_description.key == "model":
            return device_info.get("ModelName")

        if self.entity_description.key == "uptime":
            return device_info.get("UpTime")

        if self.entity_description.key == "external_ip":
            return device_info.get("ExternalIPAddress")

        if self.entity_description.key == "wan_rx":
            return dsl_info.get("status", {}).get("stats", {}).get("BytesReceived")

        if self.entity_description.key == "wan_tx":
            return dsl_info.get("status", {}).get("stats", {}).get("BytesSent")

        if self.entity_description.key == "link_state":
            return wan_info.get("data").get("LinkState")

        if self.entity_description.key == "link_type":
            return wan_info.get("data").get("LinkType")

        return None
