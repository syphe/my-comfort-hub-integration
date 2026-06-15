import os

import requests
from dotenv import load_dotenv

load_dotenv()

GIGYA_BASE_URL = "https://accounts.eu1.gigya.com"
GIGYA_LOGIN_ENDPOINT = f"{GIGYA_BASE_URL}/accounts.login"
GIGYA_GET_JWT_ENDPOINT = f"{GIGYA_BASE_URL}/accounts.getJWT"

GIGYA_API_KEY = os.getenv("GIGYA_API_KEY")

# appliance_kit AWSConstants: EU + PRODUCTION (not identity_kit manifest URLs)
AWS_BASE_URL = "https://8q8c9xktb0.execute-api.eu-central-1.amazonaws.com/dlg-prod/"
AWS_DEVICES_URL = AWS_BASE_URL + "devices"

# From manifest: com.delonghigroup.appliance_kit.APP_KIT_SOURCE = comfort
AWS_SOURCE_HEADER = "comfort"

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


if __name__ == "__main__":
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")

    login_response = gigya_login(username, password)
    print("Gigya login response:", login_response)

    session_token, session_secret = extract_session_credentials(login_response)
    jwt_response = gigya_get_jwt(session_token, session_secret)
    print("Gigya getJWT response:", jwt_response)

    token = extract_aws_token(jwt_response)
    print("Using AWS Bearer token:", token)

    devices = list_devices(token)
    print("Devices response:", devices)
