import logging

DOMAIN = "egd_smart_meter"

ATTR_CONSUMPTION = "consumption"
ATTR_PRODUCTION = "production"
ATTR_STATISTICS_IMPORTED = "statistics_imported"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_EAN = "ean"
CONF_START_DATE = "start_date"

DEFAULT_SCAN_INTERVAL = 3600
UPDATE_HOUR = 6

BASE_URL_TOKEN = "https://idm.distribuce24.cz"
BASE_URL_DATA = "https://data.distribuce24.cz/rest"

OAUTH_TOKEN_ENDPOINT = "/oauth/token"

PROFILE_CONSUMPTION = "ICC1"
PROFILE_PRODUCTION = "ISC1"

SENSOR_TYPES = {
    ATTR_CONSUMPTION: "Consumption",
    ATTR_PRODUCTION: "Production",
}

LOGGER = logging.getLogger(__name__)
