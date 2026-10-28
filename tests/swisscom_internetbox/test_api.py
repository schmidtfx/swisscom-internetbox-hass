from unittest.mock import MagicMock, patch

import pytest
from custom_components.swisscom_internetbox.api import (
    DEFAULT_REQUEST_TIMEOUT,
    InternetBoxClient,
    _describe_error,
    _extract_wan_counters,
)
from sc_inetbox_adapter import InternetboxAdapter
from sc_inetbox_adapter.errors import NoActiveSessionException

# What an InternetBox 5 on fibre answers for the dsl0 object: the call itself
# succeeds, but there is no DSL channel to report on.
FIBRE_DSL_REPLY = {"status": None, "errors": [{"error": 196638, "info": "dsl0"}]}
DSL_REPLY = {
    "status": {
        "stats": {"BytesReceived": 123456, "BytesSent": 7890},
    }
}
NETDEV_REPLY = {"status": {"RxBytes": 555, "TxBytes": 111}}

# The real veip0 reply from an InternetBox 5 on GPON, which is the WAN uplink
# and the object the integration reads on fibre.
VEIP0_REPLY = {
    "status": {
        "RxPackets": 763037066,
        "TxPackets": 386675054,
        "RxBytes": 825999917481,
        "TxBytes": 168018344701,
        "RxErrors": 0,
        "TxErrors": 0,
        "RxDropped": 2,
        "TxDropped": 4,
        "Multicast": 35,
    }
}

VEIP0_PATH = "/sysbus/NeMo/Intf/veip0:getNetDevStats"
DSL_PATH = "/sysbus/NeMo/Intf/dsl0:getDSLChannelStats"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (DSL_REPLY, {"rx_bytes": 123456, "tx_bytes": 7890}),
        (NETDEV_REPLY, {"rx_bytes": 555, "tx_bytes": 111}),
        (VEIP0_REPLY, {"rx_bytes": 825999917481, "tx_bytes": 168018344701}),
        (FIBRE_DSL_REPLY, None),
        ({"status": {}}, None),
        ({}, None),
        (None, None),
    ],
)
def test_extract_wan_counters(payload, expected) -> None:
    assert _extract_wan_counters(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "status": None,
                "errors": [
                    {
                        "error": 196618,
                        "description": "Object or parameter not found",
                        "info": "NeMo/Intf/dsl0",
                    }
                ],
            },
            "error 196618: Object or parameter not found (NeMo/Intf/dsl0)",
        ),
        (
            {
                "status": None,
                "errors": [
                    {
                        "error": 13,
                        "description": "Permission denied",
                        "info": "NeMo/Intf/eth0",
                    }
                ],
            },
            "error 13: Permission denied (NeMo/Intf/eth0)",
        ),
        ({"status": {}}, "no counters in reply"),
        (None, "unexpected reply"),
    ],
)
def test_describe_error(payload, expected) -> None:
    assert _describe_error(payload) == expected


def _client(hass) -> InternetBoxClient:
    client = InternetBoxClient(hass, "my-host", "my-password")
    client._session_ready = True
    client._add_auth_header = MagicMock(return_value={})
    return client


def _response(payload, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


async def test_wan_stats_reads_veip0_on_fibre(hass) -> None:
    """veip0 is the WAN uplink on GPON and is tried first, so one call is enough."""
    client = _client(hass)

    with patch.object(
        InternetBoxClient, "_send_request", return_value=_response(VEIP0_REPLY)
    ) as send_request:
        assert await client.async_get_wan_stats() == {
            "rx_bytes": 825999917481,
            "tx_bytes": 168018344701,
        }
        assert send_request.call_count == 1
        assert send_request.call_args.args[0] == VEIP0_PATH


async def test_wan_stats_falls_back_to_dsl_when_veip0_is_absent(hass) -> None:
    """A DSL box has no veip0, so the dsl0 object has to be used instead."""
    client = _client(hass)
    replies = {
        VEIP0_PATH: _response(None, 404),
        DSL_PATH: _response(DSL_REPLY),
    }

    with patch.object(
        InternetBoxClient, "_send_request", side_effect=lambda path, *_: replies[path]
    ) as send_request:
        assert await client.async_get_wan_stats() == {
            "rx_bytes": 123456,
            "tx_bytes": 7890,
        }
        assert send_request.call_count == 2

        # The working object is remembered, so the next poll is a single call.
        send_request.reset_mock()
        assert await client.async_get_wan_stats() == {
            "rx_bytes": 123456,
            "tx_bytes": 7890,
        }
        assert send_request.call_count == 1
        assert send_request.call_args.args[0] == DSL_PATH


async def test_wan_stats_skips_veip0_when_role_is_blocked(hass) -> None:
    """HTTP 401 is how this firmware refuses an object the webui role may not read."""
    client = _client(hass)
    replies = {
        VEIP0_PATH: _response(None, 401),
        DSL_PATH: _response(FIBRE_DSL_REPLY),
    }

    with patch.object(
        InternetBoxClient, "_send_request", side_effect=lambda path, *_: replies[path]
    ):
        assert await client.async_get_wan_stats() == {}
    assert client._wan_stats_path is None


async def test_wan_stats_empty_when_nothing_answers(hass) -> None:
    client = _client(hass)

    with patch.object(
        InternetBoxClient, "_send_request", return_value=_response(None, 401)
    ):
        assert await client.async_get_wan_stats() == {}
    assert client._wan_stats_path is None


def _posting_client(hass, token: str = "TOKEN") -> InternetBoxClient:
    """A client whose transport is stubbed out at the requests.Session level."""
    client = InternetBoxClient(hass, "my-host", "my-password")
    client._session_ready = True
    client._auth_token = token
    client._session = MagicMock()
    client._session.post.return_value = _response({})
    return client


def test_every_request_carries_a_timeout(hass) -> None:
    """A box that accepts the connection but never replies must not park a
    thread forever: without a deadline, four blocking calls per 30s poll can
    drain Home Assistant's shared executor pool."""
    client = _posting_client(hass)

    client._send_request("/sysbus/NMC:getWANStatus", "{}", {})

    assert client._session.post.call_args.kwargs["timeout"] == DEFAULT_REQUEST_TIMEOUT


def test_inherited_adapter_calls_also_carry_a_timeout(hass) -> None:
    """The adapter's own methods route through the overridden transport."""
    client = _posting_client(hass)
    client._session.post.return_value = _response({"status": {"ok": True}})

    client.get_device_info()
    client.get_devices()

    assert client._session.post.call_count == 2
    for call in client._session.post.call_args_list:
        assert call.kwargs["timeout"] == DEFAULT_REQUEST_TIMEOUT


def test_auth_header_is_fresh_per_call(hass) -> None:
    """Two config entries poll on different executor threads, so a shared
    header dict would let one box's request go out with the other's token."""
    box_a = _posting_client(hass, token="TOKEN-A")
    box_b = _posting_client(hass, token="TOKEN-B")

    headers_a = box_a._add_auth_header()
    headers_b = box_b._add_auth_header()

    assert headers_a == {"X-Context": "TOKEN-A"}
    assert headers_b == {"X-Context": "TOKEN-B"}
    assert headers_a is not headers_b
    # The first caller's dict is untouched by the second.
    assert box_a._add_auth_header() is not headers_a
    assert headers_a == {"X-Context": "TOKEN-A"}


def test_auth_header_never_touches_the_adapters_shared_default(hass) -> None:
    """``_add_auth_header(self, headers={})`` upstream means one dict object
    for every instance ever created; nothing here may write into it."""
    shared_default = InternetboxAdapter._add_auth_header.__defaults__[0]
    assert shared_default == {}

    client = _posting_client(hass, token="TOKEN-A")
    client._session.post.return_value = _response({"status": {}})
    client._add_auth_header()
    client.get_device_info()
    client.get_devices()

    assert shared_default == {}


def test_send_request_does_not_mutate_the_caller_headers(hass) -> None:
    client = _posting_client(hass)
    headers = {"X-Context": "TOKEN"}

    client._send_request("/ws", "{}", headers)

    assert headers == {"X-Context": "TOKEN"}
    sent = client._session.post.call_args.kwargs["headers"]
    assert sent["X-Context"] == "TOKEN"
    assert sent["Content-Type"] == "application/x-sah-ws-4-call+json"


def test_auth_header_still_rejects_a_missing_token(hass) -> None:
    client = InternetBoxClient(hass, "my-host", "my-password")

    with pytest.raises(NoActiveSessionException):
        client._add_auth_header()
