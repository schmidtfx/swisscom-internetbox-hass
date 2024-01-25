from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import (CONF_HOST, CONF_PASSWORD, CONF_SSL,
                                 CONF_VERIFY_SSL)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME,
                    DEFAULT_HOST_NAME, DEFAULT_NAME, DEFAULT_SSL,
                    DEFAULT_VERIFY_SSL, DOMAIN)
from .router import get_api


def _discovery_schema_with_defaults(discovery_info):
    return vol.Schema(_ordered_shared_schema(discovery_info))


def _user_schema_with_defaults(user_input):
    user_schema = {
        vol.Optional(CONF_HOST, default=user_input.get(CONF_HOST, DEFAULT_HOST_NAME)): cv.string,
    }
    user_schema.update(_ordered_shared_schema(user_input))
    return vol.Schema(user_schema)


def _ordered_shared_schema(schema_input):
    return {
        vol.Required(CONF_PASSWORD, default=schema_input.get(CONF_PASSWORD, "")): cv.string,
        vol.Optional(CONF_SSL, default=schema_input.get(CONF_SSL, DEFAULT_SSL)): cv.boolean,
        vol.Optional(CONF_VERIFY_SSL, default=schema_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)): cv.boolean,
    }

class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        settings_schema = vol.Schema({
            vol.Optional(
                CONF_CONSIDER_HOME, 
                default=self.config_entry.options.get(
                    CONF_CONSIDER_HOME, 
                    DEFAULT_CONSIDER_HOME.total_seconds()
                )
            ): int
        })

        return self.async_show_form(step_id="init", data_schema=settings_schema)
    

class SwisscomFlowHandler(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.placeholders = {
            CONF_HOST: DEFAULT_HOST_NAME,
            CONF_SSL: DEFAULT_SSL,
            CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        }
        self.discoverd = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        return OptionsFlowHandler(config_entry)
    
    async def _show_setup_form(self, user_input: dict[str, Any] | None = None, errors = None):
        if user_input is None:
            user_input = {}

        if self.discoverd:
            data_schema = _discovery_schema_with_defaults(user_input)
        else:
            data_schema = _user_schema_with_defaults(user_input)
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors or {},
            description_placeholders=self.placeholders,
        )
    
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}

        if user_input is None:
            return await self._show_setup_form()
        
        host = user_input.get(CONF_HOST, self.placeholders[CONF_HOST])
        ssl = user_input.get(CONF_SSL, self.placeholders[CONF_SSL])
        verify_ssl = user_input.get(CONF_VERIFY_SSL, self.placeholders[CONF_VERIFY_SSL])
        password = user_input[CONF_PASSWORD]

        try:
            api = await self.hass.async_add_executor_job(get_api, password, host, ssl, verify_ssl)
        except Exception as e:
            errors["base"] = "config"
            return await self._show_setup_form(user_input, errors)

        config_data = {
            CONF_PASSWORD: password,
            CONF_HOST: host,
            CONF_SSL: ssl,
            CONF_VERIFY_SSL: verify_ssl,
        }

        info = await self.hass.async_add_executor_job(api.get_device_info)
        if info is None:
            errors["base"] = "info"
            return await self._show_setup_form(user_input, errors)

        await self.async_set_unique_id(info["SerialNumber"], raise_on_progress=False)
        self._abort_if_unique_id_configured(updates=config_data)

        if info.get("ModelName") is not None and info.get("HardwareVersion") is not None:
            name = f"{info['ModelName']} - {info['HardwareVersion']}"
        else:
            name = info.get('ModelName', DEFAULT_NAME)

        return self.async_create_entry(
            title=name,
            data=config_data,
        )
