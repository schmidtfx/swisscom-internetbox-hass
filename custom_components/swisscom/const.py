from datetime import timedelta

from homeassistant.const import Platform

PLATFORMS = [
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
]

DOMAIN="swisscom"

DEFAULT_HOST_NAME = "internetbox.swisscom.ch"
DEFAULT_NAME = "Swisscom InternetBox"
DEFAULT_SSL = True
DEFAULT_VERIFY_SSL = True

CONF_CONSIDER_HOME = "consider_home"
DEFAULT_CONSIDER_HOME = timedelta(seconds=180)

MODE_ROUTER = "router"
MODE_AP = "ap"

KEY_ROUTER = "router"
KEY_COORDINATOR = "coordinator"

DEVICE_ICONS = {

}