from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.swisscom_internetbox.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

DEVICE_INFO = {
    "ModelName": "InternetBox 5",
    "SoftwareVersion": "22.4.1",
    "SerialNumber": "LK1234567890",
    "UpTime": 12345,
    "ExternalIPAddress": "85.1.2.3",
}
WAN_INFO = {"data": {"LinkState": "up", "LinkType": "ethernet"}}


def _client() -> MagicMock:
    client = MagicMock()
    client.host = "internetbox.swisscom.ch"
    client.wan_stats_path = "/sysbus/NeMo/Intf/veip0:getNetDevStats"
    client.last_raw_devices = []
    client.last_raw_wan_stats = {}
    client.async_get_hosts = AsyncMock(return_value=[])
    client.async_get_device_info = AsyncMock(return_value=DEVICE_INFO)
    client.async_get_wan_info = AsyncMock(return_value=WAN_INFO)
    client.async_get_wan_stats = AsyncMock(
        return_value={"rx_bytes": 1_000_000, "tx_bytes": 100_000}
    )
    client.async_close = AsyncMock()
    return client


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "internetbox.swisscom.ch",
            "password": "hunter2",
            "ssl": True,
            "verify_ssl": True,
        },
        unique_id="LK1234567890",
    )


async def test_entry_sets_up_every_platform(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    client = _client()

    with patch(
        "custom_components.swisscom_internetbox.InternetBoxClient",
        return_value=client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.software_version").state == "22.4.1"
    assert hass.states.get("binary_sensor.wan_connectivity").state == "on"

    # Derived from two counter samples, so it is unknown after a single poll.
    assert hass.states.get("sensor.download_speed").state == "unknown"


async def test_unload_releases_the_session(hass) -> None:
    """The box holds a bounded number of webui contexts."""
    entry = _entry()
    entry.add_to_hass(hass)
    client = _client()

    with patch(
        "custom_components.swisscom_internetbox.InternetBoxClient",
        return_value=client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert client.async_close.await_count == 1
    assert hass.states.get("binary_sensor.wan_connectivity").state == "unavailable"
