import logging
import voluptuous as vol

from homeassistant import config_entries

from custom_components.delonghi_my_comfort_hub.api import MyComfortHubApi

DOMAIN="delonghi_my_comfort_hub"

_LOGGER = logging.getLogger(__name__)

class DelonghiMyComfortHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Delonghi My Comfort Hub."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.username = None
        self.password = None
        self.gigya_api_key = None

    async def async_step_user(self, user_input=None):
        _LOGGER.debug("Starting user step of config flow with input: %s", user_input)

        if not user_input is None:
            username = user_input.get("username")
            password = user_input.get("password")
            gigya_api_key = user_input.get("gigya_api_key")

            api = MyComfortHubApi(self.hass, username, password, gigya_api_key)
            await api.authenticate()
            if not api.is_authenticated():
                _LOGGER.error("Authentication failed with provided credentials")
                return self.async_show_form(
                    step_id="user",
                    data_schema=self.get_schema(),
                    errors={"base": "invalid_credentials"}
                )
            _LOGGER.info("Authentication successful, creating config entry")
            devices = await api.get_devices()
            _LOGGER.info(f"Retrieved devices: {devices}")

            if len(devices) == 0:
                _LOGGER.error("No devices found for the authenticated account")
                return self.async_show_form(
                    step_id="user",
                    data_schema=self.get_schema(),
                    errors={"base": "no_devices"}
                )
            
            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Delonghi My Comfort Hub ({username})",
                data={
                    "username": username,
                    "password": password,
                    "gigya_api_key": gigya_api_key
                }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self.get_schema()
        )
    
    def get_schema(self):
        return vol.Schema({
            vol.Required("username"): str,
            vol.Required("password"): str,
            vol.Required("gigya_api_key"): str,
        })