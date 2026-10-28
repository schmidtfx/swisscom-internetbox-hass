from unittest.mock import MagicMock, patch

import pytest
from custom_components.swisscom_internetbox.const import (
    CONF_HOST,
    CONF_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.swisscom_internetbox.sensor import (
    SENSORS,
    InternetBoxSensor,
    async_update_router_device,
    router_device_info,
    router_identifier,
)

SENSORS_BY_KEY = {desc.key: desc for desc in SENSORS}


def _entry(
    *, unique_id: str | None = "SERIAL123", host: str = "192.168.1.1", ssl: bool = True
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-id"
    entry.unique_id = unique_id
    entry.data = {CONF_HOST: host, CONF_SSL: ssl, CONF_VERIFY_SSL: True}
    return entry


def _sensor(key: str, data: dict | None, entry: MagicMock | None = None):
    coordinator = MagicMock()
    coordinator.data = data
    return InternetBoxSensor(coordinator, entry or _entry(), SENSORS_BY_KEY[key])


def _host(active: bool) -> MagicMock:
    host = MagicMock()
    host.active = active
    return host


@pytest.mark.parametrize(
    "key", ["wan_rx", "wan_tx", "wan_rx_rate", "wan_tx_rate", "link_state", "link_type"]
)
@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        # A box that reports nothing useful must not raise, it must go unknown.
        {"wan_info": {"status": None}, "wan_stats": {}},
        {"wan_info": {"data": None}, "wan_stats": None},
    ],
)
def test_native_value_tolerates_missing_wan_data(key, data) -> None:
    assert _sensor(key, data).native_value is None


def test_wan_counters_come_from_wan_stats() -> None:
    data = {"wan_stats": {"rx_bytes": 42, "tx_bytes": 7}}

    assert _sensor("wan_rx", data).native_value == 42
    assert _sensor("wan_tx", data).native_value == 7


def test_throughput_comes_from_wan_rates() -> None:
    data = {"wan_rates": {"rx_bytes_per_s": 1000.0, "tx_bytes_per_s": 500.0}}

    assert _sensor("wan_rx_rate", data).native_value == 1000.0
    assert _sensor("wan_tx_rate", data).native_value == 500.0


def test_throughput_is_unknown_until_a_rate_can_be_derived() -> None:
    """The counters are there from the first poll, a rate needs two."""
    data = {"wan_stats": {"rx_bytes": 42, "tx_bytes": 7}, "wan_rates": {}}

    assert _sensor("wan_rx", data).native_value == 42
    assert _sensor("wan_rx_rate", data).native_value is None
    assert _sensor("wan_tx_rate", data).native_value is None


@pytest.mark.parametrize(
    ("devices", "expected"),
    [
        ([], 0),
        ([_host(False), _host(False)], 0),
        ([_host(True), _host(False)], 1),
        ([_host(True), _host(True)], 2),
    ],
)
def test_online_devices_counts_zero_instead_of_unknown(devices, expected) -> None:
    sensor = _sensor("online_devices", {"devices": devices})

    assert sensor.native_value == expected


def test_online_devices_is_zero_without_any_data() -> None:
    assert _sensor("online_devices", None).native_value == 0


def test_unique_id_is_derived_from_the_entry_id() -> None:
    assert _sensor("model", {})._attr_unique_id == "entry-id_model"


def test_sensor_links_to_the_router_device_by_identifier_only() -> None:
    device_info = _sensor("model", {})._attr_device_info

    # Only the identifier is pinned, so nothing can go stale on the entity.
    assert device_info == {"identifiers": {(DOMAIN, "SERIAL123")}}


def test_router_identifier_matches_the_entry_unique_id() -> None:
    # entity.py points via_device at the entry unique id; stay consistent.
    assert router_identifier(_entry(unique_id="SERIAL123")) == "SERIAL123"


def test_router_identifier_falls_back_to_the_entry_id() -> None:
    assert router_identifier(_entry(unique_id=None)) == "entry-id"


def test_configuration_url_uses_https_when_ssl_is_enabled() -> None:
    info = router_device_info(_entry(ssl=True), {})

    assert info["configuration_url"] == "https://192.168.1.1"


def test_configuration_url_uses_http_when_ssl_is_disabled() -> None:
    info = router_device_info(_entry(ssl=False), {})

    assert info["configuration_url"] == "http://192.168.1.1"


def test_router_device_info_defaults_when_the_box_reports_nothing() -> None:
    info = router_device_info(_entry(), None)

    assert info["identifiers"] == {(DOMAIN, "SERIAL123")}
    assert info["manufacturer"] == "Swisscom"
    assert info["name"] == "Swisscom InternetBox"
    assert info["model"] == "InternetBox"
    assert info["sw_version"] is None


def test_router_device_info_follows_the_coordinator_data() -> None:
    data = {"device_info": {"ModelName": "Internet-Box 3", "SoftwareVersion": "1.2.3"}}

    info = router_device_info(_entry(), data)

    assert info["name"] == "Internet-Box 3"
    assert info["model"] == "Internet-Box 3"
    assert info["sw_version"] == "1.2.3"


def test_router_device_is_refreshed_from_the_latest_coordinator_data() -> None:
    entry = _entry()
    coordinator = MagicMock()
    coordinator.data = {"device_info": {"SoftwareVersion": "1.0.0"}}
    registry = MagicMock()

    with patch(
        "custom_components.swisscom_internetbox.sensor.dr.async_get",
        return_value=registry,
    ):
        async_update_router_device(MagicMock(), entry, coordinator)

        # A firmware upgrade between polls must reach the device registry.
        coordinator.data = {"device_info": {"SoftwareVersion": "2.0.0"}}
        async_update_router_device(MagicMock(), entry, coordinator)

    versions = [
        call.kwargs["sw_version"]
        for call in registry.async_get_or_create.call_args_list
    ]
    assert versions == ["1.0.0", "2.0.0"]
    assert (
        registry.async_get_or_create.call_args.kwargs["config_entry_id"] == "entry-id"
    )
