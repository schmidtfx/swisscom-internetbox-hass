from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from sc_inetbox_adapter import InternetboxAdapter
from sc_inetbox_adapter.errors import NoActiveSessionException, SwisscomInetboxException


@dataclass
class HostEntry:
    mac: str
    ip: str | None
    hostname: str | None
    active: bool | None
    type: str | None


class InternetBoxClient(InternetboxAdapter):
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        password: str,
        ssl: bool = True,
        verify_ssl: bool = True,
    ):
        super().__init__(
            host=host, admin_password=password, ssl=ssl, verify_ssl=verify_ssl
        )
        self._hass = hass
        self._session_ready = False

    async def async_ensure_session(self) -> None:
        if self._session_ready:
            return

        def _login() -> None:
            status = self.create_session()
            if int(status) != 200:
                raise SwisscomInetboxException(f"Login failed: HTTP {status}")

        await self._hass.async_add_executor_job(_login)
        self._session_ready = True

    async def async_close(self) -> None:
        if not self._session_ready:
            return

        await self._hass.async_add_executor_job(self.logout_session)
        self._session_ready = False

    async def async_get_hosts(self) -> list[HostEntry]:
        await self.async_ensure_session()

        def _get() -> Any:
            return self.get_devices()

        data = await self._hass.async_add_executor_job(_get)
        if isinstance(data, dict) and "error" in data:
            if "authentication" in str(data["error"]).lower():
                raise NoActiveSessionException(data["error"])
            raise SwisscomInetboxException(data["error"])

        devices = []
        for d in data:
            mac = (
                d.get("PhysAddress") or d.get("MACAddress") or d.get("mac") or ""
            ).lower()
            ip = d.get("IPAddress") or d.get("IPAddress6") or d.get("ip")
            name = d.get("Name") or d.get("HostName") or d.get("hostname")
            active = d.get("Active") or d.get("active")
            device_type = d.get("DeviceType")

            if isinstance(active, str):
                active_norm = active.lower() in ("1", "true", "yes", "on")
            elif isinstance(active, (int, bool)):
                active_norm = bool(active)
            else:
                active_norm = None

            if not mac:
                continue

            devices.append(
                HostEntry(
                    mac=mac, ip=ip, hostname=name, active=active_norm, type=device_type
                )
            )

        return devices

    async def async_get_device_info(self) -> dict[str, Any]:
        await self.async_ensure_session()
        return await self._hass.async_add_executor_job(self.get_device_info)

    async def async_get_wan_info(self) -> dict[str, Any]:
        await self.async_ensure_session()

        def _get():
            headers = self._add_auth_header()
            payload = json.dumps({"parameters": {}})
            response = self._send_request("/sysbus/NMC:getWANStatus", payload, headers)
            return response.json()

        return await self._hass.async_add_executor_job(_get)

    async def async_get_dsl_info(self) -> dict[str, Any]:
        await self.async_ensure_session()

        def _get():
            headers = self._add_auth_header()
            payload = json.dumps({"parameters": {}})
            response = self._send_request(
                "/sysbus/NeMo/Intf/dsl0:getDSLChannelStats", payload, headers
            )
            return response.json()

        return await self._hass.async_add_executor_job(_get)
    
    @property
    def host(self) -> str:
        return self._host