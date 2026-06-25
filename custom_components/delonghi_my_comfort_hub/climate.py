
import logging

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from custom_components.delonghi_my_comfort_hub.api import MyComfortHubApi
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PRESET_ECO
)

from custom_components.delonghi_my_comfort_hub.coordinator import DelonghiMyComfortHubDataUpdateCoordinator

from homeassistant.helpers.update_coordinator import CoordinatorEntity

DOMAIN = "delonghi_my_comfort_hub"

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities: AddEntitiesCallback,):
    LOGGER.info("Setting up Delonghi My Comfort Hub integration climate platform")

    data = hass.data[DOMAIN][config_entry.entry_id]
    LOGGER.info(f"Retrieved data from hass.data: {data}")

    devices = data.get('devices', [])
    coordinators = data.get('coordinators', [])
    climate_entities = []
    for coordinator in coordinators:
        climate_entity = DelonghiMyComfortHubClimateEntity(coordinator)
        climate_entities.append(climate_entity)
    async_add_entities(climate_entities)

class DelonghiMyComfortHubClimateEntity(CoordinatorEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_ECO]
    _attr_has_entity_name = True
    _attr_min_temp = 15
    _attr_max_temp = 28
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE)
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: DelonghiMyComfortHubDataUpdateCoordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._device_info = coordinator.device_info

        self.name = f"Delonghi {self._device_info.get('machineModel', 'Unknown Device')} ({self._device_info.get('machineName', 'Unknown')})"

        LOGGER.info(f"Created climate entity for device: {self._device_info}")

    @property
    def hvac_mode(self) -> HVACMode:
        return self.coordinator.hvac_mode
    
    @property
    def current_temperature(self) -> float:
        return self.coordinator.current_temperature
    
    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.target_temperature
        
    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature: float = kwargs.get('temperature')
        unit = "C"
        message = f"SetRoomTempRequest_deg{unit}"
        response = await self.coordinator.api.run_templated_command(
            self.coordinator.device_info.get("machineName"),
            message,
            {"Value": int(temperature)},
        )
        if not response is None:
            response_status = response.get("Response")
            if response_status == 'OK':
                self.coordinator.target_temperature = temperature
                self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        value = 1 if hvac_mode == 'heat' else 0
        response = await self.coordinator.api.run_templated_command(
            self.coordinator.device_info.get("machineName"),
            "SetDeviceStatusRequest",
            {"Value": value},
        )

        if not response is None:
            response_status = response.get('Response')
            if response_status == 'OK':
                self.coordinator.hvac_mode = hvac_mode
                self.async_write_ha_state()

    @property
    def preset_mode(self) -> str | None:
        is_eco_mode = self.coordinator.machine_status["state"]["reported"]["PowerLimit"]
        if is_eco_mode == True:
            return PRESET_ECO
        return None

    def set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_ECO:
            self.coordinator.api.run_templated_command(
                self.coordinator.device_info.get('machineName'),
                "SetEcoModeRequest",
                {"Value": 1}
            )
    

    
