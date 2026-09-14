from unittest.mock import MagicMock

import pytest
from custom_components.swisscom_internetbox.sensor import SENSORS, InternetBoxSensor

SENSORS_BY_KEY = {desc.key: desc for desc in SENSORS}


def _sensor(key: str, data: dict | None) -> InternetBoxSensor:
    coordinator = MagicMock()
    coordinator.data = data
    return InternetBoxSensor(coordinator, "entry-id", SENSORS_BY_KEY[key])


@pytest.mark.parametrize("key", ["wan_rx", "wan_tx", "link_state", "link_type"])
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
