import json
from unittest.mock import MagicMock

from custom_components.swisscom_internetbox.api import HostEntry
from custom_components.swisscom_internetbox.const import DOMAIN
from custom_components.swisscom_internetbox.diagnostics import (
    async_get_config_entry_diagnostics,
)

VEIP0_PATH = "/sysbus/NeMo/Intf/veip0:getNetDevStats"
DSL_PATH = "/sysbus/NeMo/Intf/dsl0:getDSLChannelStats"

RAW_DEVICES = [
    {
        "PhysAddress": "AA:BB:CC:DD:EE:FF",
        "IPAddress": "192.168.1.42",
        "Name": "felix-laptop",
        "Active": True,
        "DeviceType": "Laptop",
    }
]


def _setup(hass) -> MagicMock:
    client = MagicMock()
    client.wan_stats_path = VEIP0_PATH
    client.last_raw_devices = RAW_DEVICES
    client.last_raw_wan_stats = {
        VEIP0_PATH: {"status": {"RxBytes": 825999917481, "TxBytes": 168018344701}},
    }

    coordinator = MagicMock()
    coordinator.client = client
    coordinator.last_update_success = True
    coordinator.update_interval.total_seconds.return_value = 30.0
    coordinator.data = {
        "devices": [
            HostEntry(
                "aa:bb:cc:dd:ee:ff", "192.168.1.42", "felix-laptop", True, "Laptop"
            ),
            HostEntry("11:22:33:44:55:66", "192.168.1.43", "nas", False, "Storage"),
        ],
        "device_info": {
            "ModelName": "InternetBox 5",
            "SoftwareVersion": "22.4.1",
            "SerialNumber": "LK1234567890",
            "ExternalIPAddress": "85.1.2.3",
        },
        "wan_info": {"data": {"LinkState": "up", "LinkType": "ethernet"}},
        "wan_stats": {"rx_bytes": 825999917481, "tx_bytes": 168018344701},
        "wan_rates": {"rx_bytes_per_s": 1000.0, "tx_bytes_per_s": 500.0},
    }

    entry = MagicMock()
    entry.entry_id = "entry-id"
    entry.data = {
        "host": "internetbox.swisscom.ch",
        "password": "hunter2",
        "ssl": True,
        "verify_ssl": False,
    }
    entry.options = {}

    hass.data[DOMAIN] = {"entry-id": coordinator}
    return entry


async def test_diagnostics_keeps_what_a_bug_report_needs(hass) -> None:
    entry = _setup(hass)

    result = await async_get_config_entry_diagnostics(hass, entry)

    # The DSL-vs-fibre story: which object answered, and the untouched reply.
    assert result["wan_stats"]["path"] == VEIP0_PATH
    assert VEIP0_PATH in result["wan_stats"]["replies"]
    assert result["wan_stats"]["rates"] == {
        "rx_bytes_per_s": 1000.0,
        "tx_bytes_per_s": 500.0,
    }
    assert result["device_info"]["ModelName"] == "InternetBox 5"
    assert result["device_info"]["SoftwareVersion"] == "22.4.1"
    assert result["wan_info"]["data"]["LinkType"] == "ethernet"
    assert result["devices"]["count"] == 2
    assert result["devices"]["online"] == 1
    assert result["entry"]["data"]["ssl"] is True
    assert result["entry"]["data"]["verify_ssl"] is False


async def test_diagnostics_redacts_everything_identifying(hass) -> None:
    entry = _setup(hass)

    result = await async_get_config_entry_diagnostics(hass, entry)
    blob = json.dumps(result)

    for secret in (
        "hunter2",
        "internetbox.swisscom.ch",
        "LK1234567890",
        "85.1.2.3",
        "AA:BB:CC:DD:EE:FF",
        "192.168.1.42",
        "felix-laptop",
    ):
        assert secret not in blob


async def test_diagnostics_survives_a_box_that_answered_nothing(hass) -> None:
    entry = _setup(hass)
    coordinator = hass.data[DOMAIN]["entry-id"]
    coordinator.data = None
    coordinator.update_interval = None
    coordinator.client.wan_stats_path = None
    coordinator.client.last_raw_devices = None
    coordinator.client.last_raw_wan_stats = {
        VEIP0_PATH: {"http_status": 401},
        DSL_PATH: {"status": None, "errors": [{"error": 196638, "info": "dsl0"}]},
    }

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["wan_stats"]["path"] is None
    assert result["wan_stats"]["replies"][VEIP0_PATH] == {"http_status": 401}
    assert result["devices"] == {"count": 0, "online": 0, "payload": []}
    assert result["coordinator"]["update_interval_seconds"] is None
