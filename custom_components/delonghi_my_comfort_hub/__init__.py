"""Initialize the Delonghi My Comfort Hub integration."""
import logging
from homeassistant.core import HomeAssistant

from custom_components.delonghi_my_comfort_hub.api import MyComfortHubApi

DOMAIN = "delonghi_my_comfort_hub"
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration using YAML configuration."""

    domain_config = config.get(DOMAIN)

    if not domain_config:
        _LOGGER.error("Domain configuration not found")
        return False

    username = domain_config["username"]
    password = domain_config["password"]
    gigya_api_key = domain_config["gigya_api_key"]

    api = MyComfortHubApi(hass, username, password, gigya_api_key)
    await api.authenticate()

    if not api.is_authenticated():
        _LOGGER.error("Failed to authenticate with Delonghi My Comfort Hub API")
        return False
    
    devices = api.get_devices()
    _LOGGER.info(f"Retrieved devices: {devices}")
    return True