from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfDataRate, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, CONF_SSL, DEFAULT_NAME, DEFAULT_SSL, DOMAIN
from .coordinator import InternetBoxDataCoordinator
from .entity import router_identifier


@dataclass(frozen=True)
class InternetBoxSensorDescription(SensorEntityDescription):
    key: str


SENSORS: tuple[InternetBoxSensorDescription, ...] = (
    InternetBoxSensorDescription(
        key="connected_devices",
        name="Connected devices",
        icon="mdi:lan-connect",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    InternetBoxSensorDescription(
        key="online_devices",
        name="Online devices",
        icon="mdi:lan-check",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    InternetBoxSensorDescription(
        key="sw_version",
        name="Software version",
        icon="mdi:router-wireless",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    InternetBoxSensorDescription(
        key="model",
        name="Model",
        icon="mdi:router",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    InternetBoxSensorDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-time-four",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        entity_registry_enabled_default=False,
    ),
    InternetBoxSensorDescription(
        key="external_ip",
        name="External IP",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    InternetBoxSensorDescription(
        key="wan_rx",
        name="WAN received",
        icon="mdi:download",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    InternetBoxSensorDescription(
        key="wan_tx",
        name="WAN sent",
        icon="mdi:upload",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    # Derived from the counters above over the poll interval, so these cost no
    # extra request. Enabled by default, unlike the raw counters: the rate is
    # what belongs on a dashboard.
    InternetBoxSensorDescription(
        key="wan_rx_rate",
        name="Download speed",
        icon="mdi:download-network",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    InternetBoxSensorDescription(
        key="wan_tx_rate",
        name="Upload speed",
        icon="mdi:upload-network",
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    InternetBoxSensorDescription(key="link_state", name="Link state", icon="mdi:link"),
    InternetBoxSensorDescription(
        key="link_type",
        name="Link type",
        icon="mdi:link",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


def _configuration_url(entry: ConfigEntry) -> str | None:
    """Build the "Visit device" URL from the entry, honouring the SSL setting."""
    host = entry.data.get(CONF_HOST)
    if not host:
        return None
    scheme = "https" if entry.data.get(CONF_SSL, DEFAULT_SSL) else "http"
    return f"{scheme}://{host}"


def router_device_info(entry: ConfigEntry, data: dict | None) -> dict:
    """Describe the router device from the latest coordinator data."""
    device_info = (data or {}).get("device_info") or {}
    model = device_info.get("ModelName")

    return {
        "identifiers": {(DOMAIN, router_identifier(entry))},
        "name": model or DEFAULT_NAME,
        "manufacturer": "Swisscom",
        "model": model or "InternetBox",
        "sw_version": device_info.get("SoftwareVersion"),
        "configuration_url": _configuration_url(entry),
    }


@callback
def async_update_router_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: InternetBoxDataCoordinator,
) -> None:
    """Create or refresh the router device entry.

    Called again on every coordinator update so that a firmware upgrade is
    reflected in the device registry without reloading the config entry.
    """
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **router_device_info(entry, coordinator.data),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: InternetBoxDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_update_router_device(hass, entry, coordinator)
    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: async_update_router_device(hass, entry, coordinator)
        )
    )

    async_add_entities(
        [InternetBoxSensor(coordinator, entry, desc) for desc in SENSORS]
    )


class InternetBoxSensor(CoordinatorEntity[InternetBoxDataCoordinator], SensorEntity):
    entity_description: InternetBoxSensorDescription

    def __init__(
        self,
        coordinator: InternetBoxDataCoordinator,
        entry: ConfigEntry,
        description: InternetBoxSensorDescription,
    ):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Group all sensors under the main router device. Only the identifier
        # is pinned here; the device's details are owned (and kept fresh) by
        # async_update_router_device, so nothing goes stale on this entity.
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, router_identifier(entry))}
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        devices = data.get("devices") or []
        device_info = data.get("device_info") or {}
        wan_info = data.get("wan_info") or {}
        wan_data = wan_info.get("data") or {}
        wan_stats = data.get("wan_stats") or {}
        wan_rates = data.get("wan_rates") or {}

        if self.entity_description.key == "connected_devices":
            return len(devices)

        if self.entity_description.key == "online_devices":
            # 0 is a valid measurement ("nobody home"); never report unknown.
            return sum(1 for d in devices if d.active)

        if self.entity_description.key == "sw_version":
            return device_info.get("SoftwareVersion")

        if self.entity_description.key == "model":
            return device_info.get("ModelName")

        if self.entity_description.key == "uptime":
            return device_info.get("UpTime")

        if self.entity_description.key == "external_ip":
            return device_info.get("ExternalIPAddress")

        if self.entity_description.key == "wan_rx":
            return wan_stats.get("rx_bytes")

        if self.entity_description.key == "wan_tx":
            return wan_stats.get("tx_bytes")

        if self.entity_description.key == "wan_rx_rate":
            return wan_rates.get("rx_bytes_per_s")

        if self.entity_description.key == "wan_tx_rate":
            return wan_rates.get("tx_bytes_per_s")

        if self.entity_description.key == "link_state":
            return wan_data.get("LinkState")

        if self.entity_description.key == "link_type":
            return wan_data.get("LinkType")

        return None
