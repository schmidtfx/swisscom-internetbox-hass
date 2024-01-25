from datetime import timedelta

DOMAIN="swisscom"

DEFAULT_HOST_NAME = "internetbox.swisscom.ch"
DEFAULT_NAME = "Swisscom InternetBox"

CONF_CONSIDER_HOME = "consider_home"
DEFAULT_CONSIDER_HOME = timedelta(seconds=180)

MODE_ROUTER = "router"
MODE_AP = "ap"