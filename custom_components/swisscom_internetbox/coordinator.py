from __future__ import annotations

import datetime as dt
import logging
from time import monotonic

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from sc_inetbox_adapter.errors import NoActiveSessionException

from .api import InternetBoxClient
from .const import DEFAULT_POLL_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)

RATE_KEYS: tuple[tuple[str, str], ...] = (
    ("rx_bytes", "rx_bytes_per_s"),
    ("tx_bytes", "tx_bytes_per_s"),
)


def _byte_rates(
    previous: dict[str, int | None] | None,
    previous_at: float | None,
    current: dict[str, int | None],
    now: float,
) -> dict[str, float]:
    """Bytes per second between two WAN counter samples.

    A rate is left out entirely (rather than reported as zero) whenever it
    cannot be derived, so the sensor goes unknown instead of lying: on the
    first poll, for a counter the box did not report, and for a counter that
    went backwards.
    """
    if not previous or previous_at is None:
        return {}

    elapsed = now - previous_at
    if elapsed <= 0:
        return {}

    rates: dict[str, float] = {}
    for counter, key in RATE_KEYS:
        before = previous.get(counter)
        after = current.get(counter)
        # rx and tx are guarded separately: _extract_wan_counters returns one
        # set and the other None when the box reports only one of them.
        if before is None or after is None:
            continue
        delta = after - before
        if delta < 0:
            # Both counters restart at 0 when the box reboots. That is not a
            # transfer rate, and the next poll re-establishes the baseline.
            continue
        rates[key] = delta / elapsed

    return rates


class InternetBoxDataCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, client: InternetBoxClient):
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=dt.timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS),
        )
        self._client = client
        self._last_stats: dict[str, int | None] | None = None
        self._last_stats_at: float | None = None

    @property
    def client(self) -> InternetBoxClient:
        """The API client, so entry teardown can release the session."""
        return self._client

    async def _async_update_data(self) -> dict:
        try:
            devices = await self._client.async_get_hosts()
            info = await self._client.async_get_device_info()
            wan_info = await self._client.async_get_wan_info()
            wan_stats = await self._client.async_get_wan_stats()

            # Timed here rather than off the poll interval: a slow or skipped
            # poll makes the real gap longer than update_interval.
            now = monotonic()
            wan_rates = _byte_rates(
                self._last_stats, self._last_stats_at, wan_stats, now
            )
            self._last_stats = wan_stats
            self._last_stats_at = now

            return {
                "devices": devices,
                "device_info": info,
                "wan_info": wan_info,
                "wan_stats": wan_stats,
                "wan_rates": wan_rates,
            }
        except NoActiveSessionException as err:
            await self._client.async_close()
            raise UpdateFailed("Session expired; will re-authenticate") from err
        except Exception as ex:
            raise UpdateFailed(str(ex)) from ex
