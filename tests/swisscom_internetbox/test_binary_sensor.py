from unittest.mock import MagicMock

import pytest
from custom_components.swisscom_internetbox.binary_sensor import (
    InternetBoxWanConnectivity,
)
from custom_components.swisscom_internetbox.const import DOMAIN


def _entity(data: dict | None) -> InternetBoxWanConnectivity:
    coordinator = MagicMock()
    coordinator.data = data
    entry = MagicMock()
    entry.entry_id = "entry-id"
    entry.unique_id = "SERIAL123"
    return InternetBoxWanConnectivity(coordinator, entry)


@pytest.mark.parametrize(
    ("link_state", "expected"),
    [
        ("up", True),
        ("Up", True),
        ("connected", True),
        ("bound", True),
        ("down", False),
        ("disconnected", False),
        # An unseen value counts as down rather than unknown: an automation
        # testing this boolean needs an answer either way.
        ("something-new", False),
        (None, None),
        ("", None),
        ("   ", None),
        (1, None),
    ],
)
def test_link_state_maps_to_a_boolean(link_state, expected) -> None:
    data = {"wan_info": {"data": {"LinkState": link_state}}}

    assert _entity(data).is_on is expected


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"wan_info": None},
        {"wan_info": {}},
        {"wan_info": {"data": None}},
        # getWANStatus answers with status/errors instead of data when it fails.
        {"wan_info": {"status": None, "errors": [{"error": 13}]}},
    ],
)
def test_missing_wan_data_is_unknown(data) -> None:
    assert _entity(data).is_on is None


def test_it_groups_under_the_router_device() -> None:
    """Same identifier the sensors and via_device use, or it lands elsewhere."""
    entity = _entity({})

    assert entity._attr_device_info == {"identifiers": {(DOMAIN, "SERIAL123")}}
    assert entity._attr_unique_id == "entry-id_wan_connectivity"
