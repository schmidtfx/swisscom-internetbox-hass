from __future__ import annotations

import datetime as dt
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sc_inetbox_adapter.errors import NoActiveSessionException

from .api import InternetBoxClient
from .const import DEFAULT_POLL_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class InternetBoxDataCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, client: InternetBoxClient):
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=dt.timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS),
        )
        self._client = client

    async def _async_update_data(self) -> dict:
        try:
            devices = await self._client.async_get_hosts()
            info = await self._client.async_get_device_info()
            wan_info = await self._client.async_get_wan_info()
            dsl_info = await self._client.async_get_dsl_info()

            return {
                "devices": devices,
                "device_info": info,
                "wan_info": wan_info,
                "dsl_info": dsl_info,
            }
        except NoActiveSessionException as err:
            await self._client.async_close()
            raise UpdateFailed("Session expired; will re-authenticate") from err
        except Exception as ex:
            raise UpdateFailed(str(ex)) from ex
