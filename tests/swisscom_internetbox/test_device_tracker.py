from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import custom_components.swisscom_internetbox as integration
import pytest
from custom_components.swisscom_internetbox import device_tracker
from custom_components.swisscom_internetbox.api import HostEntry
from custom_components.swisscom_internetbox.const import (
    CONF_CONSIDER_HOME,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_CONSIDER_HOME,
)
from custom_components.swisscom_internetbox.device_tracker import (
    InternetBoxDeviceTracker,
    consider_home_interval,
)

MAC = "AA:BB:CC:DD:EE:FF"


class _Clock:
    """A tickable stand-in for ``dt_util.utcnow`` so grace periods are testable."""

    def __init__(self, start: dt.datetime) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += dt.timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock(dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC))
    monkeypatch.setattr(device_tracker.dt_util, "utcnow", fake)
    return fake


def _host(**overrides) -> HostEntry:
    fields = {
        "mac": MAC,
        "ip": "192.168.1.5",
        "hostname": "laptop",
        "active": True,
        "type": "Laptop",
    }
    fields.update(overrides)
    return HostEntry(**fields)


def _entry(options: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.options = {} if options is None else options
    entry.entry_id = "entry-id"
    entry.unique_id = "entry-unique-id"
    return entry


def _tracker(
    device: HostEntry | None = None, options: dict | None = None
) -> InternetBoxDeviceTracker:
    device = _host() if device is None else device
    coordinator = MagicMock()
    coordinator.data = {"devices": [device]}
    return InternetBoxDeviceTracker(coordinator, _entry(options), device)


# --- #4: a host without DeviceType must not blow up entity construction ------


@pytest.mark.parametrize("device_type", [None, "", "Totally Unknown Thing"])
def test_icon_falls_back_when_device_type_is_missing(device_type) -> None:
    assert _tracker(_host(type=device_type)).icon == "mdi:help-network"


def test_icon_is_derived_from_a_known_device_type() -> None:
    assert _tracker(_host(type="Laptop")).icon == "mdi:laptop"


def test_device_without_type_is_still_fully_usable() -> None:
    tracker = _tracker(_host(type=None))

    assert tracker.is_connected is True
    assert tracker.mac_address == MAC
    assert tracker.ip_address == "192.168.1.5"
    assert tracker.hostname == "laptop"


def test_device_without_hostname_or_ip_falls_back_to_mac() -> None:
    tracker = _tracker(_host(hostname="--", ip=None))

    assert tracker._device_name == MAC


# --- #5: a device leaving the network must degrade, not raise ----------------


def test_departed_device_keeps_last_known_values_and_goes_away() -> None:
    tracker = _tracker(options={CONF_CONSIDER_HOME: 0})
    assert tracker.is_connected is True

    tracker.coordinator.data = {"devices": []}
    tracker.async_update_device()

    assert tracker.is_connected is False
    # Last known details survive, so the entity attributes stay meaningful.
    assert tracker.ip_address == "192.168.1.5"
    assert tracker.hostname == "laptop"
    assert tracker.mac_address == MAC
    assert tracker._device_name == "laptop"


def test_update_tolerates_missing_coordinator_data() -> None:
    tracker = _tracker(options={CONF_CONSIDER_HOME: 0})

    for data in (None, {}, {"devices": None}):
        tracker.coordinator.data = data
        tracker.async_update_device()
        assert tracker.is_connected is False
        assert tracker.hostname == "laptop"


def test_device_reported_inactive_is_not_connected() -> None:
    tracker = _tracker(_host(active=False), options={CONF_CONSIDER_HOME: 0})

    assert tracker.is_connected is False


def test_device_coming_back_is_connected_again() -> None:
    tracker = _tracker(options={CONF_CONSIDER_HOME: 0})

    tracker.coordinator.data = {"devices": []}
    tracker.async_update_device()
    assert tracker.is_connected is False

    returned = _host(ip="192.168.1.9")
    tracker.coordinator.data = {"devices": [returned]}
    tracker.async_update_device()

    assert tracker.is_connected is True
    assert tracker.ip_address == "192.168.1.9"


def test_match_is_case_insensitive_on_mac() -> None:
    tracker = _tracker(options={CONF_CONSIDER_HOME: 0})

    tracker.coordinator.data = {"devices": [_host(mac=MAC.lower())]}
    tracker.async_update_device()

    assert tracker.is_connected is True


# --- #11: the consider_home grace period must actually be honoured -----------


def test_consider_home_interval_reads_the_option() -> None:
    assert consider_home_interval(_entry({CONF_CONSIDER_HOME: 42})) == dt.timedelta(
        seconds=42
    )


@pytest.mark.parametrize("raw", [{}, {CONF_CONSIDER_HOME: None}])
def test_consider_home_interval_defaults_when_unset(raw) -> None:
    assert consider_home_interval(_entry(raw)) == DEFAULT_CONSIDER_HOME


@pytest.mark.parametrize("raw", ["not-a-number", -5])
def test_consider_home_interval_defaults_on_garbage(raw) -> None:
    assert consider_home_interval(_entry({CONF_CONSIDER_HOME: raw})) == (
        DEFAULT_CONSIDER_HOME
    )


def test_device_stays_home_for_the_consider_home_window(clock) -> None:
    tracker = _tracker(options={CONF_CONSIDER_HOME: 180})
    tracker.coordinator.data = {"devices": []}
    tracker.async_update_device()

    # A single missed poll must not flip the tracker to not_home.
    assert tracker.is_connected is True

    clock.tick(179)
    assert tracker.is_connected is True

    clock.tick(2)
    assert tracker.is_connected is False


def test_last_seen_is_refreshed_while_the_device_is_around(clock) -> None:
    tracker = _tracker(options={CONF_CONSIDER_HOME: 60})

    clock.tick(50)
    tracker.async_update_device()

    # The grace period restarts from the latest sighting, not from setup.
    clock.tick(50)
    tracker.coordinator.data = {"devices": []}
    tracker.async_update_device()
    assert tracker.is_connected is True

    clock.tick(61)
    assert tracker.is_connected is False


def test_device_absent_from_the_very_first_poll_is_never_home(clock) -> None:
    tracker = _tracker(_host(active=False), options={CONF_CONSIDER_HOME: 180})

    assert tracker.is_connected is False
    clock.tick(1)
    assert tracker.is_connected is False


# --- #11: the options update listener must be registered ---------------------


async def test_async_setup_entry_registers_the_update_listener() -> None:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()

    entry = _entry()
    entry.data = {
        CONF_HOST: "internetbox.swisscom.ch",
        CONF_PASSWORD: "secret",
        CONF_SSL: True,
        CONF_VERIFY_SSL: True,
    }
    entry.add_update_listener.return_value = "unsubscribe"

    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()

    with (
        patch.object(integration, "InternetBoxClient"),
        patch.object(
            integration, "InternetBoxDataCoordinator", return_value=coordinator
        ),
    ):
        assert await integration.async_setup_entry(hass, entry) is True

    entry.add_update_listener.assert_called_once_with(integration.update_listener)
    entry.async_on_unload.assert_called_once_with("unsubscribe")
