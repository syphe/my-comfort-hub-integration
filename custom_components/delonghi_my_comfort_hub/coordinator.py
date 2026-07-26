import asyncio
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.delonghi_my_comfort_hub.api import MyComfortHubApi

from homeassistant.core import HomeAssistant

import logging
import json

from homeassistant.components.climate import (
    HVACMode,
)

_LOGGER = logging.getLogger(__name__)

class DelonghiMyComfortHubDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    hvac_mode: HVACMode = HVACMode.OFF
    current_temperature: float = 0
    target_temperature: float | None = None

    def __init__(self, hass: HomeAssistant, api: MyComfortHubApi, device_info: dict):
        """Initialize."""
        self.hass = hass
        self.api = api
        self.device_info = device_info

        super().__init__(hass, _LOGGER, name="Delonghi My Comfort Hub Data Update Coordinator", update_interval=timedelta(minutes=10))

    async def _async_update_data(self):
        _LOGGER.info("Fetching data from Delonghi My Comfort Hub API")

        machine_name = self.device_info.get('machineName')

        async def get_machine_status():
            str_machine_status = await self.api.run_shadow_get(machine_name, 'MachineStatus')
            machine_status = json.loads(str_machine_status)
            self.update_state(machine_status)

        num_attempts = 3
        for attempt in range(num_attempts):
            try:
                await get_machine_status()
                return
            except Exception as e:
                _LOGGER.error("Error fetching data from Delonghi My Comfort Hub API: %s", e)
                if attempt < num_attempts - 1:
                    _LOGGER.info("Retrying after 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    raise e
    
    def update_state(self, machine_status: dict):
        self.machine_status = machine_status

        device_status = int(machine_status["state"]["reported"]["DeviceStatus"])
        room_temp = float(machine_status["state"]["reported"]["RoomTemp"])
        temp_set_point = float(machine_status["state"]["reported"]["TempSetPoint"])

        self.hvac_mode = HVACMode.HEAT if device_status == 1 else HVACMode.OFF
        self.current_temperature = room_temp / 10
        self.target_temperature = temp_set_point

    async def _async_config_entry_first_refresh(self):
        await super()._async_config_entry_first_refresh()

        self.api.listen_for_mqtt_messages(self.device_info.get('machineName'))




