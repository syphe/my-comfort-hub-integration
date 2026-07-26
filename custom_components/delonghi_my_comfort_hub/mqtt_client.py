from paho.mqtt import client as mqtt
import time
import uuid
import ssl
import json
import asyncio

MQTT_HOST = "a2612mo23mfrw1-ats.iot.eu-central-1.amazonaws.com"
MQTT_AUTHORIZER = "dlg-prod-token-authorizer"
MQTT_WS_PATH = f"/mqtt?x-amz-customauthorizer-name={MQTT_AUTHORIZER}"

class MqttClient:
    def __init__(self):
        pass

    def create_mqtt_client(self, aws_token: str, on_message=None) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=uuid.uuid4().hex[:20],
            protocol=mqtt.MQTTv5,
            transport="websockets",
        )
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.ws_set_options(path=MQTT_WS_PATH)
        client.username_pw_set(
            username=f"x-amz-customauthorizer-name={MQTT_AUTHORIZER}",
            password=aws_token,
        )

        def handle_connect(client, userdata, flags, reason_code, properties):
            print(f"MQTT connected: {reason_code}")

        def handle_disconnect(client, userdata, flags, reason_code, properties):
            print(f"MQTT disconnected: {reason_code}")

        def handle_message(client, userdata, message):
            payload = message.payload.decode("utf-8", errors="replace")
            print(f"\n[{message.topic}]")
            try:
                print(json.dumps(json.loads(payload), indent=2, sort_keys=True))
            except json.JSONDecodeError:
                print(payload)
            if on_message:
                on_message(message.topic, payload)

        client.on_connect = handle_connect
        client.on_disconnect = handle_disconnect
        client.on_message = handle_message
        
        return client

    async def mqtt_connect(self, aws_token: str, on_message=None) -> mqtt.Client:
        def create_client_and_connect():
            client = self.create_mqtt_client(aws_token, on_message=on_message)
            client.connect(MQTT_HOST, port=443, keepalive=30)
            client.loop_start()

            while not client.is_connected():
                time.sleep(0.25)
            return client

        client = await asyncio.to_thread(create_client_and_connect)

        return client
    

    def publish_json(self, client: mqtt.Client, topic: str, payload: dict | None) -> None:
        body = json.dumps(payload) if payload is not None else "{}"
        result = client.publish(topic, payload=body, qos=1)
        print(f"Published {topic}: result={result.rc}, mid={result.mid}, payload={body}")