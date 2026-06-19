
import logging

from homeassistant.core import HomeAssistant

LOGGER = logging.getLogger(__name__)

def setup_platform(hass: HomeAssistant, config: dict, add_entities, discovery_info=None):
    """Set up the Delonghi My Comfort Hub climate platform."""
    # This function is required by Home Assistant but can be left empty
    LOGGER.info("Setting up Delonghi My Comfort Hub climate platform")
    pass