import json
from pathlib import Path
from unittest.mock import patch

import pytest
from custom_components.swisscom_internetbox import config_flow
from custom_components.swisscom_internetbox.const import (
    CONF_CONSIDER_HOME,
    DEFAULT_CONSIDER_HOME,
    DOMAIN,
)
from homeassistant import config_entries, data_entry_flow
from homeassistant.config_entries import OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SSL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

COMPONENT_PATH = Path(config_flow.__file__).parent

DEVICE_INFO = {
    "Manufacturer": "Arcadyan",
    "ManufacturerOUI": "1883BF",
    "ModelName": "IB3-00",
    "Description": "IB3-00 Arcadyan ch",
    "ProductClass": "IB3-00",
    "SerialNumber": "5.1P2334B0308410",
    "HardwareVersion": "5.1",
    "SoftwareVersion": "14.00.52",
    "RescueVersion": "13.20.26",
    "ModemFirmwareVersion": "",
    "EnabledOptions": "",
    "AdditionalHardwareVersion": "",
    "AdditionalSoftwareVersion": "",
    "SpecVersion": "1.1",
    "ProvisioningCode": "2cc229db-ef45-47d3-afab-2f71cf2efa82",
    "UpTime": 1314812,
    "FirstUseDate": "2024-01-05T00:00:00Z",
    "DeviceLog": "",
    "VendorConfigFileNumberOfEntries": 0,
    "ManufacturerURL": "http://www.arcadyan.com",
    "Country": "ch",
    "ExternalIPAddress": "85.6.164.38",
    "DeviceStatus": "Up",
    "NumberOfReboots": 3,
    "UpgradeOccurred": False,
    "ResetOccurred": False,
    "RestoreOccurred": False,
    "StandbyOccurred": False,
    "X_SOFTATHOME-COM_AdditionalSoftwareVersions": "",
    "BaseMAC": "a0:b5:49:c3:94:e0",
}


@pytest.fixture(name="create_session")
def mock_create_session():
    with patch(
        "custom_components.swisscom_internetbox.api.InternetBoxClient.create_session",
    ) as service_mock:
        service_mock.return_value = 200
        yield service_mock


@pytest.fixture(name="get_device_info")
def mock_get_device_info():
    with patch(
        "custom_components.swisscom_internetbox.api.InternetBoxClient.get_device_info",
    ) as service_mock:
        service_mock.return_value = DEVICE_INFO
        yield service_mock


async def test_config_flow_user(
    hass: HomeAssistant, create_session, get_device_info
) -> None:
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
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE_INFO["SerialNumber"]
    assert (
        result["title"]
        == f"{DEVICE_INFO['ModelName']} - {DEVICE_INFO['HardwareVersion']}"
    )
    assert result["data"].get(CONF_HOST) == "my-host"
    assert result["data"].get(CONF_SSL)
    assert result["data"][CONF_PASSWORD] == "my-password"


USER_INPUT = {
    CONF_HOST: "my-host",
    CONF_PASSWORD: "my-password",
    CONF_SSL: True,
    CONF_VERIFY_SSL: True,
}


async def _submit_user_step(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(USER_INPUT)
    )


async def test_config_flow_login_failure_shows_translated_error(
    hass: HomeAssistant, create_session, get_device_info
) -> None:
    """A failed login shows the `config` error key, not raw English prose."""
    create_session.return_value = 401

    result = await _submit_user_step(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "config"}
    assert get_device_info.call_count == 0


@pytest.mark.parametrize("device_info", [None, {}])
async def test_config_flow_no_device_info(
    hass: HomeAssistant, create_session, get_device_info, device_info
) -> None:
    """A box that returns no device info shows the `info` error key."""
    get_device_info.return_value = device_info

    result = await _submit_user_step(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "info"}


async def test_config_flow_missing_serial_number(
    hass: HomeAssistant, create_session, get_device_info
) -> None:
    """A box without a SerialNumber errors on the form instead of raising."""
    get_device_info.return_value = {
        key: value for key, value in DEVICE_INFO.items() if key != "SerialNumber"
    }

    result = await _submit_user_step(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "info"}


async def test_config_flow_recovers_after_error(
    hass: HomeAssistant, create_session, get_device_info
) -> None:
    """The form stays usable after an error and can still create the entry."""
    get_device_info.return_value = None

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(USER_INPUT)
    )
    assert result["errors"] == {"base": "info"}

    get_device_info.return_value = DEVICE_INFO
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(USER_INPUT)
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE_INFO["SerialNumber"]


async def test_config_flow_errors_are_translation_keys() -> None:
    """Every error key the flow assigns is defined in the translations."""
    strings = json.loads((COMPONENT_PATH / "strings.json").read_text())
    english = json.loads((COMPONENT_PATH / "translations" / "en.json").read_text())

    assert strings == english, "strings.json and translations/en.json have diverged"

    errors = strings["config"]["error"]
    assert config_flow.ERROR_CONFIG in errors
    assert config_flow.ERROR_INFO in errors

    options_data = strings["options"]["step"]["init"]["data"]
    assert CONF_CONSIDER_HOME in options_data


def test_options_flow_handler_is_an_options_flow() -> None:
    """The options handler must derive from OptionsFlow, not ConfigFlow."""
    assert issubclass(config_flow.OptionsFlowHandler, OptionsFlow)


async def test_options_flow(hass: HomeAssistant) -> None:
    """The options flow opens and stores the consider_home value."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=dict(USER_INPUT),
        unique_id=DEVICE_INFO["SerialNumber"],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"]({}) == {
        CONF_CONSIDER_HOME: int(DEFAULT_CONSIDER_HOME.total_seconds())
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CONSIDER_HOME: 300}
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_CONSIDER_HOME: 300}
    assert entry.options == {CONF_CONSIDER_HOME: 300}


async def test_options_flow_defaults_to_stored_value(hass: HomeAssistant) -> None:
    """An already stored option is pre-filled in the form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=dict(USER_INPUT),
        options={CONF_CONSIDER_HOME: 42},
        unique_id=DEVICE_INFO["SerialNumber"],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["data_schema"]({}) == {CONF_CONSIDER_HOME: 42}
