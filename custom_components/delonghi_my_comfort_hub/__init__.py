"""Initialize the Delonghi My Comfort Hub integration."""
import logging
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.delonghi_my_comfort_hub.api import MyComfortHubApi
from custom_components.delonghi_my_comfort_hub.coordinator import DelonghiMyComfortHubDataUpdateCoordinator

DOMAIN = "delonghi_my_comfort_hub"

PLATFORMS: list[Platform] = {
    Platform.CLIMATE
}

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry):
    _LOGGER.info("Setting up Delonghi My Comfort Hub integration")
    _LOGGER.info(f"Config entry data: {entry.data}")

    username = entry.data.get("username")
    password = entry.data.get("password")
    gigya_api_key = entry.data.get("gigya_api_key")

    api = MyComfortHubApi(hass, entry, username, password, gigya_api_key)
    await api.authenticate()
    if not api.is_authenticated():
        _LOGGER.error("Failed to authenticate with Delonghi My Comfort Hub API")
        return False
    
    devices = await api.get_devices()
    _LOGGER.info(f"Retrieved devices: {devices}")

    if len(devices) == 0:
        _LOGGER.error("No devices found for the authenticated account")
        return False
    
    await api.connect_mqtt()
    
    coordinators = []
    for device in devices:
        coordinator = DelonghiMyComfortHubDataUpdateCoordinator(hass, api, device)
        await coordinator.async_config_entry_first_refresh()
        coordinators.append(coordinator)
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "devices": devices,
        "coordinators": coordinators
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_setup(hass: HomeAssistant, config: dict):
    return True
    # """Set up the integration using YAML configuration."""

    # domain_config = config.get(DOMAIN)

    # if not domain_config:
    #     _LOGGER.error("Domain configuration not found")
    #     return False

    # username = domain_config["username"]
    # password = domain_config["password"]
    # gigya_api_key = domain_config["gigya_api_key"]

    # api = MyComfortHubApi(hass, username, password, gigya_api_key)
    # await api.authenticate()

    # if not api.is_authenticated():
    #     _LOGGER.error("Failed to authenticate with Delonghi My Comfort Hub API")
    #     return False
    
    # devices = await api.get_devices()
    # _LOGGER.info(f"Retrieved devices: {devices}")

    # # Store the api and devices in hass.data so platforms can access them
    # hass.data.setdefault(DOMAIN, {})
    # hass.data[DOMAIN] = {
    #     "api": api,
    #     "devices": devices
    # }

    # # Forward the setup to the relevant platform (e.g., climate)
    # # If using modern config entries, you'd use hass.config_entries.async_forward_entry_setups
    # hass.async_create_task(
    #     hass.helpers.discovery.async_load_platform("climate", DOMAIN, {}, config)
    # )
    # return True