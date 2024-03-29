import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_HOST, CONF_PASSWORD, CONF_SSL,
                                 CONF_VERIFY_SSL)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from sc_inetbox_adapter import InternetboxAdapter

from .const import (CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME, DOMAIN,
                    MODE_ROUTER)

_LOGGER = logging.getLogger(__name__)


def get_api(password: str, host: str, ssl: bool, verify_ssl: bool):
    api: InternetboxAdapter = InternetboxAdapter(password)
    res = api.create_session()
    return api


class SwisscomInternetbox:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        assert entry.unique_id

        self.hass = hass
        self.entry = entry

        self._info = None
        self.mode = MODE_ROUTER
        
        self.track_devices = True

        self._consider_home = entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME.total_seconds())
        self._consider_home = timedelta(seconds=self._consider_home)

        self.api: InternetboxAdapter = None
        self.api_lock = asyncio.Lock()

        self.devices: dict[str, Any] = {}

    async def _setup(self) -> bool:
        self.api = await self.hass.async_add_executor_job(get_api, self._password, self._host, self._ssl, self._verify_ssl)
        self._info = await self._get_device_info()
        if not self._info:
            return False

        enabled_entries = [
            entry for entry in self.hass.config_entries.async_entries(DOMAIN) if entry.disabled_by is None
        ]
        self.track_devices = self.mode == MODE_ROUTER or len(enabled_entries) == 1
        _LOGGER.debug(f"Swisscom InternetBox track_devices={self.track_devices}, device mode {self.mode}")
        return True
    
    async def async_setup(self) -> bool:
        async with self.api_lock:
            if not await self._setup():
                return False
            
        if self.track_devices:
            device_registry = dr.async_get(self.hass)
            devices = dr.async_entries_for_config_entry(device_registry, self.entry_id)
            for device_entry in devices:
                if device_entry.via_device_id is None:
                    continue

                device_mac = dict(device_entry.connections)[dr.CONNECTION_NETWORK_MAC]
                self.devices[device_mac] = {
                    "PhysAddress": device_mac,
                    "Name": device_entry.name,
                    "Active": False,
                    "last_seen": dt_util.utcnow() - timedelta(days=365),
                    "ModelName": None,
                    "DeviceType": None,
                    "link_rate": None,
                    "IPAddress": None,
                    "ssid": None,
                    "conn_ap_mac": None,
                    "allow_or_block": None,
                }
        return True
    
    async def _create_session(self):
        return await self.hass.async_add_executor_job(self.api.create_session)
    

    async def _get_device_info(self):
        await self._create_session()
        return await self.hass.async_add_executor_job(self.api.get_device_info)
    
    async def _get_devices(self):
        await self._create_session()
        return await self.hass.async_add_executor_job(self.api.get_devices)
    
    async def async_update_device_trackers(self, now=None) -> bool:
        new_devices = False
        devices = await self._get_devices() or []
        now = dt_util.utcnow()
        year_ago = now - timedelta(days=365)
        
        for device in devices:
            if device["DeviceType"] == "":
                continue

            device_mac = dr.format_mac(device["PhysAddress"])

            if not self.devices.get(device_mac):
                new_devices = True

            last_seen = self.devices.get(device_mac, {}).get("last_seen", year_ago)
            self.devices[device_mac] = device
            self.devices[device_mac]["PhysAddress"] = device_mac

            self.devices[device_mac]["last_seen"] = now if device["Active"] else last_seen
            
        for device in self.devices.values():
            device["Active"] = (now - device["last_seen"]) <= self._consider_home        

        return new_devices
    
    @property
    def entry_id(self):
        return self.entry.entry_id
    
    @property
    def unique_id(self):
        return self.entry.unique_id
    
    @property
    def _host(self):
        return self.entry.data[CONF_HOST]
    
    @property
    def _ssl(self):
        return self.entry.data[CONF_SSL]
    
    @property
    def _verify_ssl(self):
        return self.entry.data[CONF_VERIFY_SSL]
    
    @property
    def _password(self):
        return self.entry.data[CONF_PASSWORD]