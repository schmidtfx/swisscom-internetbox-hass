from homeassistant.const import Platform
import datetime as dt

DOMAIN = "swisscom_internetbox"
PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]

CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_SSL = "ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_HOST_NAME = "internetbox.swisscom.ch"
DEFAULT_NAME = "Swisscom InternetBox"
DEFAULT_SSL = True
DEFAULT_VERIFY_SSL = True

CONF_CONSIDER_HOME = "consider_home"
DEFAULT_CONSIDER_HOME = dt.timedelta(seconds=180)

DEFAULT_POLL_INTERVAL_SECONDS = 30

DEVICE_ICONS = {
    "iphone": "mdi:cellphone",
    "android phone": "mdi:cellphone",
    "smartphone": "mdi:cellphone",
    "speaker": "mdi:speaker",
    "hifi": "mdi:speaker",
    "laptop": "mdi:laptop",
}