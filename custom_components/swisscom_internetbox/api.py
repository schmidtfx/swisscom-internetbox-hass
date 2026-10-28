from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests
import urllib3
from homeassistant.core import HomeAssistant
from sc_inetbox_adapter import InternetboxAdapter
from sc_inetbox_adapter.errors import NoActiveSessionException, SwisscomInetboxException

_LOGGER = logging.getLogger(__name__)

# sc_inetbox_adapter 0.1.2 passes no timeout to requests, so a box that accepts
# the connection but never replies parks an executor thread forever. Four
# blocking calls every poll would eventually drain Home Assistant's shared
# pool, so the transport is overridden below to always carry a deadline.
# (connect, read) in seconds.
DEFAULT_REQUEST_TIMEOUT: tuple[float, float] = (5.0, 10.0)

SAH_CONTENT_TYPE = "application/x-sah-ws-4-call+json"

# The WAN byte counters live behind different sysbus objects depending on the
# physical link. On fibre (InternetBox 5 / GPON) the uplink is veip0; dsl0 only
# exists on DSL lines.
#
# Probing an InternetBox 5 showed that of its 83 NeMo interfaces only two allow
# the webui role to call getNetDevStats: veip0 (the WAN uplink) and bridge (the
# LAN side). Everything else answers HTTP 401. Note that bridge is deliberately
# not listed here: its counters are the WAN's mirrored (what the WAN receives,
# the bridge transmits), so using it would report download as upload.
WAN_STATS_PATHS: tuple[str, ...] = (
    "/sysbus/NeMo/Intf/veip0:getNetDevStats",
    "/sysbus/NeMo/Intf/dsl0:getDSLChannelStats",
)


@dataclass
class HostEntry:
    mac: str
    ip: str | None
    hostname: str | None
    active: bool | None
    type: str | None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _describe_error(payload: Any) -> str | None:
    """Return why a sysbus call carried no counters, for logging.

    A rejected call still answers HTTP 200; the reason is in the ``errors``
    array (e.g. 196618 "Object or parameter not found" for an object that does
    not exist on this link, or 13 "Permission denied" when the webui role may
    not read it).
    """
    if not isinstance(payload, dict):
        return "unexpected reply"

    errors = payload.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        first = errors[0]
        return (
            f"error {first.get('error')}: {first.get('description')}"
            f" ({first.get('info')})"
        )
    if errors:
        return f"error: {errors}"
    return "no counters in reply"


def _extract_wan_counters(payload: Any) -> dict[str, int | None] | None:
    """Normalise a getDSLChannelStats/getNetDevStats reply to rx/tx bytes.

    Returns None when the reply carries no usable counters, which is what a
    fibre box answers for the dsl0 object.
    """
    if not isinstance(payload, dict):
        return None

    status = payload.get("status")
    if not isinstance(status, dict):
        return None

    # getDSLChannelStats nests the counters, getNetDevStats reports them flat.
    stats = status.get("stats")
    if isinstance(stats, dict):
        status = stats

    rx = _as_int(status.get("BytesReceived", status.get("RxBytes")))
    tx = _as_int(status.get("BytesSent", status.get("TxBytes")))
    if rx is None and tx is None:
        return None

    return {"rx_bytes": rx, "tx_bytes": tx}


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
        self._wan_stats_path: str | None = None

        # The normalising helpers above throw away everything a bug report
        # needs. Keep the last untouched reply of each so diagnostics.py can
        # dump it without a second round of requests.
        self.last_raw_devices: Any = None
        self.last_raw_wan_stats: dict[str, Any] = {}

    # -- transport -------------------------------------------------------
    #
    # The methods below replace the adapter's own implementations. They exist
    # for two reasons:
    #
    # * the adapter never passes a ``timeout`` (see DEFAULT_REQUEST_TIMEOUT);
    # * the adapter's header helpers use ``headers={}`` as a default, so a
    #   single dict object is shared by every adapter instance ever created.
    #   ``_add_auth_header`` writes ``X-Context`` into it and hands the same
    #   object back to every caller, so with two config entries polling on
    #   different executor threads one box's request can go out carrying the
    #   other box's token.
    #
    # Everything here therefore builds a fresh dict per request and never
    # mutates what it was given, which also keeps the adapter's shared
    # defaults clean when inherited methods pass them down.

    def _add_auth_header(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        if not self._auth_token:
            raise NoActiveSessionException
        return {**(headers or {}), "X-Context": self._auth_token}

    def _send_ws_request(
        self, payload: str, headers: dict[str, str] | None = None
    ) -> requests.Response:
        return self._send_request("/ws", payload, headers)

    def _send_auth_ws_request(
        self, payload: str, headers: dict[str, str] | None = None
    ) -> requests.Response:
        return self._send_ws_request(payload, self._add_auth_header(headers))

    def _send_request(
        self, path: str, payload: str, headers: dict[str, str] | None = None
    ) -> requests.Response:
        url = f"{self._protocol}://{self._host}{path}"
        request_headers = {**(headers or {}), "Content-Type": SAH_CONTENT_TYPE}
        if not self._verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return self._session.post(
            url,
            headers=request_headers,
            data=payload,
            verify=self._verify_ssl,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )

    # -- session ---------------------------------------------------------

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
        """Release the session on the box, best effort.

        The usual reason a session dies is that the box became unreachable, so
        the logout POST is itself likely to fail. Dropping the local session
        state matters more than the logout succeeding: if ``_session_ready``
        stays set, ``async_ensure_session`` keeps early-returning and every
        later poll reuses a token the box has already forgotten, which only a
        Home Assistant restart would recover from.
        """
        if not self._session_ready:
            self._auth_token = None
            return

        try:
            await self._hass.async_add_executor_job(self.logout_session)
        except Exception:  # teardown must never raise
            _LOGGER.debug("Logout failed; dropping the session anyway", exc_info=True)
        finally:
            self._session_ready = False
            self._auth_token = None

    async def async_get_hosts(self) -> list[HostEntry]:
        await self.async_ensure_session()

        def _get() -> Any:
            return self.get_devices()

        data = await self._hass.async_add_executor_job(_get)
        self.last_raw_devices = data
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

    async def async_get_wan_stats(self) -> dict[str, int | None]:
        """Return the WAN byte counters, whatever the physical link is.

        Probes the known sysbus objects once and remembers the one that
        answered, so the regular poll stays at a single request.
        """
        await self.async_ensure_session()

        def _call(path: str, replies: dict[str, Any]) -> dict[str, int | None] | None:
            headers = self._add_auth_header()
            payload = json.dumps({"parameters": {}})
            response = self._send_request(path, payload, headers)
            if response.status_code != 200:
                replies[path] = {"http_status": response.status_code}
                _LOGGER.debug("%s: HTTP %s", path, response.status_code)
                return None
            try:
                reply = response.json()
            except ValueError:
                replies[path] = {"body": response.text[:200]}
                _LOGGER.debug("%s: reply was not JSON", path)
                return None

            replies[path] = reply
            counters = _extract_wan_counters(reply)
            if counters is None:
                _LOGGER.debug("%s: %s", path, _describe_error(reply))
            return counters

        def _get() -> dict[str, int | None]:
            cached = self._wan_stats_path
            paths = WAN_STATS_PATHS
            if cached:
                paths = (cached, *(p for p in WAN_STATS_PATHS if p != cached))

            # Why the other objects were skipped is the whole story on a
            # DSL-vs-fibre bug report, so keep every reply, not just the hit.
            replies: dict[str, Any] = {}
            self.last_raw_wan_stats = replies

            for path in paths:
                counters = _call(path, replies)
                if counters is None:
                    continue
                if path != cached:
                    _LOGGER.debug("Reading WAN counters from %s", path)
                    self._wan_stats_path = path
                return counters

            # Nothing answered; forget the cached object so a link change
            # (DSL <-> fibre) is picked up on the next poll.
            _LOGGER.debug("No WAN byte counters found, tried: %s", ", ".join(paths))
            self._wan_stats_path = None
            return {}

        return await self._hass.async_add_executor_job(_get)

    @property
    def wan_stats_path(self) -> str | None:
        """The sysbus object the WAN counters are currently read from."""
        return self._wan_stats_path

    @property
    def host(self) -> str:
        return self._host
