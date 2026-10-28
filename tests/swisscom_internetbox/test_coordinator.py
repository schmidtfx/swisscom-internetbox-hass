"""Coordinator session-recovery behaviour.

The scenario these guard is the one that used to need a Home Assistant
restart: the box goes away, the session dies with it, and the recovery path
has to drop the local session state even though it cannot reach the box to
log out properly.
"""

from unittest.mock import patch

import pytest
from custom_components.swisscom_internetbox.api import InternetBoxClient
from custom_components.swisscom_internetbox.coordinator import (
    InternetBoxDataCoordinator,
)
from homeassistant.helpers.update_coordinator import UpdateFailed
from sc_inetbox_adapter.errors import NoActiveSessionException


def _client(hass) -> InternetBoxClient:
    client = InternetBoxClient(hass, "my-host", "my-password")
    client._session_ready = True
    client._auth_token = "TOKEN"
    return client


async def test_expired_session_is_dropped(hass) -> None:
    """A dead session has to be cleared so the next poll re-authenticates."""
    client = _client(hass)
    coordinator = InternetBoxDataCoordinator(hass, client)

    with (
        patch.object(
            InternetBoxClient, "get_devices", side_effect=NoActiveSessionException
        ),
        patch.object(InternetBoxClient, "logout_session", return_value=200) as logout,
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    assert logout.call_count == 1
    assert client._session_ready is False
    assert client._auth_token is None


async def test_expired_session_is_dropped_when_logout_fails(hass) -> None:
    """Regression: an unreachable box used to leave the client wedged.

    ``async_close()`` POSTs a logout, and the box being gone is the usual
    reason the session expired in the first place. That POST raising must not
    swallow the ``UpdateFailed`` nor leave ``_session_ready`` set, otherwise
    ``async_ensure_session`` early-returns forever and only a restart helps.
    """
    client = _client(hass)
    coordinator = InternetBoxDataCoordinator(hass, client)

    with (
        patch.object(
            InternetBoxClient, "get_devices", side_effect=NoActiveSessionException
        ),
        patch.object(
            InternetBoxClient, "logout_session", side_effect=OSError("box unreachable")
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    assert client._session_ready is False
    assert client._auth_token is None


async def test_dropped_session_re_authenticates_on_the_next_poll(hass) -> None:
    """The point of clearing the flag: the next poll logs back in."""
    client = _client(hass)

    with patch.object(
        InternetBoxClient, "logout_session", side_effect=OSError("box unreachable")
    ):
        await client.async_close()

    with patch.object(InternetBoxClient, "create_session", return_value=200) as login:
        await client.async_ensure_session()

    assert login.call_count == 1
    assert client._session_ready is True


async def test_close_is_a_no_op_without_a_session(hass) -> None:
    client = InternetBoxClient(hass, "my-host", "my-password")

    with patch.object(InternetBoxClient, "logout_session") as logout:
        await client.async_close()

    assert logout.call_count == 0
    assert client._auth_token is None


async def test_coordinator_exposes_its_client(hass) -> None:
    """``async_unload_entry`` needs this to release the session on unload."""
    client = _client(hass)
    assert InternetBoxDataCoordinator(hass, client).client is client


async def test_other_errors_still_become_update_failed(hass) -> None:
    client = _client(hass)
    coordinator = InternetBoxDataCoordinator(hass, client)

    with (
        patch.object(
            InternetBoxClient, "get_devices", side_effect=OSError("box unreachable")
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    # Not a session problem, so the session is left alone.
    assert client._session_ready is True
