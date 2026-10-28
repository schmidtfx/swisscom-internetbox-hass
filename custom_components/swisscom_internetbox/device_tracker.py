from __future__ import annotations

import datetime as dt

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import HostEntry
from .const import (
    CONF_CONSIDER_HOME,
    DEFAULT_CONSIDER_HOME,
    DEVICE_ICONS,
    DOMAIN,
)
from .coordinator import InternetBoxDataCoordinator
from .entity import InternetBoxDeviceEntity


def consider_home_interval(entry: ConfigEntry) -> dt.timedelta:
    """Return the configured ``consider_home`` grace period for an entry.

    The options flow stores the value as a number of seconds. Fall back to the
    default when the option is unset or unusable instead of raising.
    """
    raw = (entry.options or {}).get(CONF_CONSIDER_HOME)
    if raw is None:
        return DEFAULT_CONSIDER_HOME
    if isinstance(raw, dt.timedelta):
        return raw
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_CONSIDER_HOME
    if seconds < 0:
        return DEFAULT_CONSIDER_HOME
    return dt.timedelta(seconds=seconds)


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
    def __init__(
        self,
        coordinator: InternetBoxDataCoordinator,
        entry: ConfigEntry,
        device: HostEntry,
    ):
        super().__init__(coordinator, entry, device)
        self._attr_name = self._device_name
        # ``HostEntry.type`` is optional: the box omits ``DeviceType`` for plenty
        # of hosts, so never call ``.lower()`` on it unguarded.
        self._attr_icon = DEVICE_ICONS.get(
            (device.type or "").lower(), "mdi:help-network"
        )
        self._consider_home = consider_home_interval(entry)
        self._present = bool(device.active)
        self._last_seen: dt.datetime | None = (
            dt_util.utcnow() if device.active else None
        )

    @callback
    def async_update_device(self) -> None:
        found = self._find()
        # Keep the last known entry around: a device that left the network is
        # simply away, it must not turn every property into an AttributeError.
        if found is not None:
            self._device = found
        self._present = found is not None and bool(found.active)
        if self._present:
            self._last_seen = dt_util.utcnow()

    @property
    def is_connected(self) -> bool:
        if self._present:
            return True
        if self._last_seen is None:
            return False
        # Honour the configured grace period before declaring the device away.
        return dt_util.utcnow() - self._last_seen < self._consider_home

    @property
    def source_type(self):
        return SourceType.ROUTER

    @property
    def ip_address(self) -> str | None:
        return self._device.ip if self._device else None

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def hostname(self) -> str | None:
        return self._device.hostname if self._device else None

    def _find(self) -> HostEntry | None:
        for d in (self.coordinator.data or {}).get("devices") or []:
            if (d.mac or "").lower() == self._mac.lower():
                return d
        return None
