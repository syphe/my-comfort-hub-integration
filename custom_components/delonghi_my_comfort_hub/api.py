
import json
import logging
import logging
import secrets
import string
import time
import asyncio
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.delonghi_my_comfort_hub.gigya_api import GigyaApi
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.delonghi_my_comfort_hub.mqtt_client import MqttClient

from paho.mqtt.client import MQTTMessage

AWS_BASE_URL = "https://8q8c9xktb0.execute-api.eu-central-1.amazonaws.com/dlg-prod/"
AWS_OTHER_URL = "https://gax54h1o65.execute-api.us-east-1.amazonaws.com/dlg-prod/"
AWS_DEVICES_URL = AWS_BASE_URL + "devices"
AWS_JOBS_URL = AWS_OTHER_URL + "jobs"

AWS_SOURCE_HEADER = "comfort"

APP_ID = "comfort"

LOGGER = logging.getLogger(__name__)

class MyComfortHubApi:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, username: str, password: str, gigya_api_key: str):
        self.hass = hass
        self.entry = entry
        self.username = username
        self.password = password
        self.gigya_api_key = gigya_api_key
        self.gigya_api = GigyaApi(hass, gigya_api_key)
        self.mqtt_client = MqttClient()

    async def authenticate(self):
        await self.gigya_api.login(self.username, self.password)

        if not self.gigya_api.is_authenticated():
            raise Exception("Authentication failed with Gigya API")
        pass

    async def connect_mqtt(self):
        def on_message(topic: str, payload: str) -> None:
            self.on_mqtt_message(topic, payload)
        self.mqtt_client_client = await self.mqtt_client.mqtt_connect(self.gigya_api.aws_token, on_message)

    def on_mqtt_message(self, topic: str, payload: str) -> None:
        LOGGER.info(f'received mqtt message {topic} {payload}')

        json_payload = json.loads(payload)

        if re.match(r"\$aws/things/.*/shadow/name/MachineStatus/get/accepted", topic): 
            machine_name = topic.split('/')[2]
            LOGGER.info(f"Received MachineStatus get accepted for machine {machine_name}: {json_payload}")

            domain = self.hass.data.get("delonghi_my_comfort_hub", {})
            coordinators = domain.get(self.entry.entry_id, {}).get("coordinators", [])
            for coordinator in coordinators:
                if coordinator.device_info.get("machineName") == machine_name:
                    LOGGER.info(f"Found matching coordinator for machine {machine_name}, updating state")
                    # coordinator.update_state(json_payload)
                    # self.hass.add_job(coordinator.async_update_listeners)
                    break
            return

        machine_name = topic.split('/')[0]
        message = json_payload.get("Message", None)
        response = json_payload.get("Response", None)

        if message == "SetRoomTempRequest_degC" and response == "OK":
            value = float(json_payload.get("Value", None))
            LOGGER.info(f"Successfully set room temperature to {value}°C")
            
            domain = self.hass.data.get("delonghi_my_comfort_hub", {})
            LOGGER.info(f"Retrieved domain data: {domain}")
            coordinators = domain.get(self.entry.entry_id, {}).get("coordinators", [])
            LOGGER.info(f"Retrieved coordinators: {coordinators}")
            for coordinator in coordinators:
                if coordinator.device_info.get("machineName") == machine_name:
                    LOGGER.info(f"Found matching coordinator for machine {machine_name}, refreshing data")
                    coordinator.target_temperature = value
                    self.hass.add_job(coordinator.async_update_listeners)
                    break

        if message == "SetDeviceStatusRequest" and response == "OK":
            value = int(json_payload.get("Value", None))
            hvac_mode = "heat" if value == 1 else "off"
            LOGGER.info(f"Successfully set device status to {hvac_mode}")

            domain = self.hass.data.get("delonghi_my_comfort_hub", {})
            coordinators = domain.get(self.entry.entry_id, {}).get("coordinators", [])
            for coordinator in coordinators:
                if coordinator.device_info.get("machineName") == machine_name:
                    LOGGER.info(f"Found matching coordinator for machine {machine_name}, refreshing data")
                    coordinator.hvac_mode = hvac_mode
                    self.hass.add_job(coordinator.async_update_listeners)
                    break
        


    def is_authenticated(self) -> bool:
        return self.gigya_api.is_authenticated()

    async def get_devices(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.gigya_api.aws_token}",
            "source": AWS_SOURCE_HEADER,
            "Accept": "application/json"
        }
        session = async_get_clientsession(self.hass)
        async with session.get(AWS_DEVICES_URL, headers=headers, timeout=30) as response:
            response.raise_for_status()
            response_data = await response.json(content_type=None)

        return response_data.get("ownedByMe", [])

    async def run_shadow_get(self, machine_name: str, shadow_name: str) -> str:
        accepted_topic = f"$aws/things/{machine_name}/shadow/name/{shadow_name}/get/accepted"
        rejected_topic = f"$aws/things/{machine_name}/shadow/name/{shadow_name}/get/rejected"

        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def on_message(client, topic: str, message: MQTTMessage) -> None:
            LOGGER.info(f"Received MQTT message on topic {message.topic}: {message.payload}")
            future.set_result(message.payload)

        # client = await self.mqtt_client.mqtt_connect(self.gigya_api.aws_token, on_message=on_message)
        try:
            self.mqtt_client_client.subscribe(accepted_topic, qos=0)
            self.mqtt_client_client.subscribe(rejected_topic, qos=0)

            self.mqtt_client_client.message_callback_add(accepted_topic, on_message)
            self.mqtt_client_client.message_callback_add(rejected_topic, on_message)

            self.mqtt_client.publish_json(self.mqtt_client_client, f"$aws/things/{machine_name}/shadow/name/{shadow_name}/get", None)

            await asyncio.wait_for(future, timeout=30)

            return future.result()
        finally:
            # client.loop_stop()
            # client.disconnect()
            self.mqtt_client_client.message_callback_remove(accepted_topic)
            self.mqtt_client_client.message_callback_remove(rejected_topic)
            pass

    async def run_templated_command(
        self,
        machine_name: str,
        message: str,
        values: dict,
    ) -> None:
        command = self.build_app_command(
            message=message,
            values=values,
        )
        LOGGER.info(json.dumps(command, indent=2, sort_keys=True))
        return await self.run_send_command(machine_name, command)

    def build_app_command(
        self,
        message: str,
        values: dict,
    ) -> dict:
        command = {
            "AppId": APP_ID,
            "Message": message,
            "RequestId": ''.join(secrets.choice(string.ascii_letters) for _ in range(5)),
            "TimeStamp": f"{time.strftime('%H:%M:%S')} - {time.strftime('%d.%m.%Y')}",
        }
        command.update(values)
        return command
    
    async def run_send_command(self, machine_name: str, command: dict) -> None:
        response_topic = self.mqtt_topics(machine_name)["command_response"]

        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def on_message(client: MqttClient, topic: str, message: MQTTMessage) -> None:
            future.set_result(message.payload)

        # client = self.mqtt_connect(aws_token, on_message=on_message)
        try:
            self.mqtt_client_client.subscribe(response_topic, qos=0)
            self.mqtt_client_client.message_callback_add(response_topic, on_message)

            self.mqtt_client.publish_json(self.mqtt_client_client, self.mqtt_topics(machine_name)["command_request"], command)

            await asyncio.wait_for(future, timeout=30)
        finally:
            self.mqtt_client_client.message_callback_remove(response_topic)
            pass

        result = future.result()
        return json.loads(result) if not result is None else None
    
    def mqtt_topics(self, machine_name: str) -> dict[str, str]:
        shadow_prefix = f"$aws/things/{machine_name}/shadow/name"
        return {
            "status_get": f"{shadow_prefix}/MachineStatus/get",
            "status_get_accepted": f"{shadow_prefix}/MachineStatus/get/accepted",
            "status_update_accepted": f"{shadow_prefix}/MachineStatus/update/accepted",
            "capabilities_get": f"{shadow_prefix}/MachineCapabilities/get",
            "capabilities_get_accepted": f"{shadow_prefix}/MachineCapabilities/get/accepted",
            "capabilities_update_accepted": f"{shadow_prefix}/MachineCapabilities/update/accepted",
            "command_request": f"{machine_name}/commands/request",
            "command_response": f"{machine_name}/commands/response",
            "presence_connected": f"$aws/events/presence/connected/{machine_name}",
            "presence_disconnected": f"$aws/events/presence/disconnected/{machine_name}",
            "jobs_status": f"app/machine/{machine_name}/jobs/status",
        }

    def listen_for_mqtt_messages(self, machine_name: str):
        LOGGER.info(f"Subscribing to MQTT topics for machine {machine_name}")
        self.mqtt_client_client.subscribe(self.mqtt_topics(machine_name)["command_response"], qos=0)
        self.mqtt_client_client.subscribe(self.mqtt_topics(machine_name)["status_update_accepted"], qos=0)
        self.mqtt_client_client.subscribe(self.mqtt_topics(machine_name)["presence_connected"], qos=0)
        self.mqtt_client_client.subscribe(self.mqtt_topics(machine_name)["presence_disconnected"], qos=0)