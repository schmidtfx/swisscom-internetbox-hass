from unittest.mock import Mock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (CONF_HOST, CONF_PASSWORD, CONF_SSL,
                                 CONF_VERIFY_SSL)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.swisscom.const import DOMAIN

DEVICE_INFO = {'Manufacturer': 'Arcadyan',
 'ManufacturerOUI': '1883BF',
 'ModelName': 'IB3-00',
 'Description': 'IB3-00 Arcadyan ch',
 'ProductClass': 'IB3-00',
 'SerialNumber': '5.1P2334B0308410',
 'HardwareVersion': '5.1',
 'SoftwareVersion': '14.00.52',
 'RescueVersion': '13.20.26',
 'ModemFirmwareVersion': '',
 'EnabledOptions': '',
 'AdditionalHardwareVersion': '',
 'AdditionalSoftwareVersion': '',
 'SpecVersion': '1.1',
 'ProvisioningCode': '2cc229db-ef45-47d3-afab-2f71cf2efa82',
 'UpTime': 1314812,
 'FirstUseDate': '2024-01-05T00:00:00Z',
 'DeviceLog': '',
 'VendorConfigFileNumberOfEntries': 0,
 'ManufacturerURL': 'http://www.arcadyan.com',
 'Country': 'ch',
 'ExternalIPAddress': '85.6.164.38',
 'DeviceStatus': 'Up',
 'NumberOfReboots': 3,
 'UpgradeOccurred': False,
 'ResetOccurred': False,
 'RestoreOccurred': False,
 'StandbyOccurred': False,
 'X_SOFTATHOME-COM_AdditionalSoftwareVersions': '',
 'BaseMAC': 'a0:b5:49:c3:94:e0'}


@pytest.fixture(name="service")
def mock_controller_service():
    with patch("custom_components.swisscom.router.InternetboxAdapter") as service_mock:
        service_mock.return_value.create_session = Mock(return_value=200)
        service_mock.return_value.get_device_info = Mock(return_value=DEVICE_INFO)
        service_mock.return_value.ssl = True
        yield service_mock


async def test_config_flow_user(hass: HomeAssistant, service) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "my-host",
            CONF_PASSWORD: "my-password",
            CONF_SSL: True,
            CONF_VERIFY_SSL: True
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE_INFO["SerialNumber"]
    assert result["title"] == f"{DEVICE_INFO['ModelName']} - {DEVICE_INFO['HardwareVersion']}"
    assert result["data"].get(CONF_HOST) == "my-host"
    assert result["data"].get(CONF_SSL) == True
    assert result["data"][CONF_PASSWORD] == "my-password"