import os
import argparse
import json
import ssl
import time
import uuid

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv

load_dotenv()

GIGYA_BASE_URL = "https://accounts.eu1.gigya.com"
GIGYA_LOGIN_ENDPOINT = f"{GIGYA_BASE_URL}/accounts.login"
GIGYA_GET_JWT_ENDPOINT = f"{GIGYA_BASE_URL}/accounts.getJWT"

GIGYA_API_KEY = os.getenv("GIGYA_API_KEY")

# appliance_kit AWSConstants: EU + PRODUCTION (not identity_kit manifest URLs)
AWS_BASE_URL = "https://8q8c9xktb0.execute-api.eu-central-1.amazonaws.com/dlg-prod/"
AWS_OTHER_URL = "https://gax54h1o65.execute-api.us-east-1.amazonaws.com/dlg-prod/"
AWS_DEVICES_URL = AWS_BASE_URL + "devices"
AWS_JOBS_URL = AWS_OTHER_URL + "jobs"

# From manifest: com.delonghigroup.appliance_kit.APP_KIT_SOURCE = comfort
AWS_SOURCE_HEADER = "comfort"

# appliance_kit MqttConfig: EU + PRODUCTION
MQTT_HOST = "a2612mo23mfrw1-ats.iot.eu-central-1.amazonaws.com"
MQTT_AUTHORIZER = "dlg-prod-token-authorizer"
MQTT_WS_PATH = f"/mqtt?x-amz-customauthorizer-name={MQTT_AUTHORIZER}"

SESSION_EXPIRATION = 7776000


def gigya_login(login_id: str, password: str) -> dict:
    payload = {
        "loginID": login_id,
        "password": password,
        "targetEnv": "mobile",
        "include": "id_token,profile,data,preferences",
        "sessionExpiration": SESSION_EXPIRATION,
        "format": "json",
        "apiKey": GIGYA_API_KEY,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post(GIGYA_LOGIN_ENDPOINT, data=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def gigya_get_jwt(session_token: str, session_secret: str) -> dict:
    # App exchanges session credentials for a dedicated JWT before AWS calls.
    headers = {
        "Authorization": f"Bearer {session_token}",
    }
    params = {
        "secret": session_secret,
        "expiration": SESSION_EXPIRATION,
        "apiKey": GIGYA_API_KEY,
        "httpStatusCodes": "true",
    }
    response = requests.post(GIGYA_GET_JWT_ENDPOINT, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def extract_session_credentials(login_response: dict) -> tuple[str, str]:
    session_info = login_response.get("sessionInfo") or {}
    session_token = session_info.get("sessionToken")
    session_secret = session_info.get("sessionSecret")
    if not session_token or not session_secret:
        raise ValueError("Login response missing sessionInfo.sessionToken or sessionInfo.sessionSecret")
    return session_token, session_secret


def extract_aws_token(jwt_response: dict) -> str:
    token = jwt_response.get("idToken") or jwt_response.get("id_token")
    if not token:
        raise ValueError("getJWT response missing idToken")
    return token


def list_devices(aws_token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {aws_token}",
        "source": AWS_SOURCE_HEADER,
    }
    response = requests.get(AWS_DEVICES_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

def list_jobs(aws_token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {aws_token}",
        "source": AWS_SOURCE_HEADER,
    }
    response = requests.get(AWS_JOBS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def login_and_get_token() -> str:
    username = os.getenv("DELONGHI_USERNAME")
    password = os.getenv("DELONGHI_PASSWORD")
    if not username or not password:
        raise ValueError("DELONGHI_USERNAME and DELONGHI_PASSWORD must be set in .env")

    login_response = gigya_login(username, password)
    session_token, session_secret = extract_session_credentials(login_response)
    jwt_response = gigya_get_jwt(session_token, session_secret)
    return extract_aws_token(jwt_response)


def extract_devices(devices_response: dict) -> list[dict]:
    devices = devices_response.get("devices") or devices_response.get("owned") or devices_response.get("items")
    if isinstance(devices, list):
        return devices
    if isinstance(devices_response, list):
        return devices_response
    return []


def mqtt_topics(machine_name: str) -> dict[str, str]:
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


def create_mqtt_client(aws_token: str, on_message=None) -> mqtt.Client:
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


def mqtt_connect(aws_token: str, on_message=None) -> mqtt.Client:
    client = create_mqtt_client(aws_token, on_message=on_message)
    client.connect(MQTT_HOST, port=443, keepalive=20)
    client.loop_start()
    return client


def subscribe_default_topics(client: mqtt.Client, machine_name: str) -> None:
    topics = mqtt_topics(machine_name)
    for key in (
        "status_get_accepted",
        "status_update_accepted",
        "capabilities_get_accepted",
        "capabilities_update_accepted",
        "command_request",
        "command_response",
        "presence_connected",
        "presence_disconnected",
        "jobs_status",
    ):
        topic = topics[key]
        result, mid = client.subscribe(topic, qos=0)
        print(f"Subscribed {topic}: result={result}, mid={mid}")


def publish_json(client: mqtt.Client, topic: str, payload: dict | None) -> None:
    body = json.dumps(payload) if payload is not None else "{}"
    result = client.publish(topic, payload=body, qos=1)
    print(f"Published {topic}: result={result.rc}, mid={result.mid}, payload={body}")


def run_monitor(aws_token: str, machine_name: str) -> None:
    client = mqtt_connect(aws_token)
    try:
        subscribe_default_topics(client, machine_name)
        publish_json(client, mqtt_topics(machine_name)["status_get"], None)
        publish_json(client, mqtt_topics(machine_name)["capabilities_get"], None)
        print("Listening. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    finally:
        client.loop_stop()
        client.disconnect()


def run_shadow_get(aws_token: str, machine_name: str, shadow_name: str) -> None:
    received = {"done": False}
    accepted_topic = f"$aws/things/{machine_name}/shadow/name/{shadow_name}/get/accepted"
    rejected_topic = f"$aws/things/{machine_name}/shadow/name/{shadow_name}/get/rejected"

    def on_message(topic: str, payload: str) -> None:
        if topic in {accepted_topic, rejected_topic}:
            received["done"] = True

    client = mqtt_connect(aws_token, on_message=on_message)
    try:
        client.subscribe(accepted_topic, qos=0)
        client.subscribe(rejected_topic, qos=0)
        time.sleep(1)
        publish_json(client, f"$aws/things/{machine_name}/shadow/name/{shadow_name}/get", None)
        deadline = time.time() + 15
        while time.time() < deadline and not received["done"]:
            time.sleep(0.25)
    finally:
        client.loop_stop()
        client.disconnect()


def run_send_command(aws_token: str, machine_name: str, command: dict) -> None:
    command.setdefault("RequestId", uuid.uuid4().hex)
    received = {"done": False}
    response_topic = mqtt_topics(machine_name)["command_response"]

    def on_message(topic: str, payload: str) -> None:
        if topic == response_topic:
            received["done"] = True

    client = mqtt_connect(aws_token, on_message=on_message)
    try:
        client.subscribe(response_topic, qos=0)
        time.sleep(1)
        publish_json(client, mqtt_topics(machine_name)["command_request"], command)
        deadline = time.time() + 20
        while time.time() < deadline and not received["done"]:
            time.sleep(0.25)
    finally:
        client.loop_stop()
        client.disconnect()


def build_app_command(
    message: str,
    values: dict,
    app_id: str = "comfort",
    app_id_key: str = "AppId",
    request_id_key: str = "RequestId",
) -> dict:
    command = {
        app_id_key: app_id,
        "Message": message,
        request_id_key: uuid.uuid4().hex,
    }
    command.update(values)
    return command


def run_templated_command(
    aws_token: str,
    machine_name: str,
    message: str,
    values: dict,
    app_id: str,
    app_id_key: str,
    request_id_key: str,
    dry_run: bool,
) -> None:
    command = build_app_command(
        message=message,
        values=values,
        app_id=app_id,
        app_id_key=app_id_key,
        request_id_key=request_id_key,
    )
    print(json.dumps(command, indent=2, sort_keys=True))
    if dry_run:
        return
    run_send_command(aws_token, machine_name, command)


def add_template_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-id", default="comfort")
    parser.add_argument("--app-id-key", choices=["AppId", "AppID", "appId", "appID"], default="AppId")
    parser.add_argument("--request-id-key", choices=["RequestId", "RequestID", "requestId", "requestID"], default="RequestId")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="My Comfort Hub API/MQTT test client")
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("list-devices")
    subparsers.add_parser("list-jobs")

    monitor = subparsers.add_parser("monitor")
    monitor.add_argument("machine_name")

    shadow_get = subparsers.add_parser("shadow-get")
    shadow_get.add_argument("machine_name")
    shadow_get.add_argument("shadow_name", choices=["MachineStatus", "MachineCapabilities"])

    send_command = subparsers.add_parser("send-command")
    send_command.add_argument("machine_name")
    send_command.add_argument("json_payload", help='JSON object to publish, for example {"Command":"..."}')

    set_temp = subparsers.add_parser("set-temp")
    set_temp.add_argument("machine_name")
    set_temp.add_argument("temperature", type=float)
    set_temp.add_argument("--unit", choices=["C", "F"], default="C")
    set_temp.add_argument("--field", default="temp")
    add_template_options(set_temp)

    set_power = subparsers.add_parser("set-power")
    set_power.add_argument("machine_name")
    set_power.add_argument("state", choices=["ON", "OFF", "on", "off"])
    set_power.add_argument("--field", default="DeviceStatus")
    add_template_options(set_power)

    set_eco = subparsers.add_parser("set-eco")
    set_eco.add_argument("machine_name")
    set_eco.add_argument("state", choices=["on", "off", "true", "false", "1", "0"])
    set_eco.add_argument("--field", default="isEcoMode")
    add_template_options(set_eco)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()

    if args.command in (None, "list-devices"):
        token = login_and_get_token()
        devices = list_devices(token)
        print(json.dumps(devices, indent=2, sort_keys=True))
        parsed_devices = extract_devices(devices)
        if parsed_devices:
            print("\nMachine names:")
            for device in parsed_devices:
                print(f"- {device.get('machineName')}")
    elif args.command == "list-jobs":
        token = login_and_get_token()
        print(json.dumps(list_jobs(token), indent=2, sort_keys=True))
    elif args.command == "monitor":
        token = login_and_get_token()
        run_monitor(token, args.machine_name)
    elif args.command == "shadow-get":
        token = login_and_get_token()
        run_shadow_get(token, args.machine_name, args.shadow_name)
    elif args.command == "send-command":
        token = login_and_get_token()
        payload = json.loads(args.json_payload)
        if not isinstance(payload, dict):
            raise ValueError("json_payload must be a JSON object")
        run_send_command(token, args.machine_name, payload)
    elif args.command == "set-temp":
        token = "" if args.dry_run else login_and_get_token()
        message = f"SetRoomTempRequest_deg{args.unit}"
        run_templated_command(
            token,
            args.machine_name,
            message,
            {args.field: args.temperature},
            args.app_id,
            args.app_id_key,
            args.request_id_key,
            args.dry_run,
        )
    elif args.command == "set-power":
        token = "" if args.dry_run else login_and_get_token()
        run_templated_command(
            token,
            args.machine_name,
            "SetDeviceStatusRequest",
            {args.field: args.state.upper()},
            args.app_id,
            args.app_id_key,
            args.request_id_key,
            args.dry_run,
        )
    elif args.command == "set-eco":
        token = "" if args.dry_run else login_and_get_token()
        state = args.state.lower() in {"on", "true", "1"}
        run_templated_command(
            token,
            args.machine_name,
            "SetEcoModeRequest",
            {args.field: state},
            args.app_id,
            args.app_id_key,
            args.request_id_key,
            args.dry_run,
        )
