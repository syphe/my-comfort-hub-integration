from homeassistant.core import HomeAssistant
import requests

from homeassistant.helpers.aiohttp_client import async_get_clientsession

GIGYA_BASE_URL = "https://accounts.eu1.gigya.com"
GIGYA_LOGIN_ENDPOINT = f"{GIGYA_BASE_URL}/accounts.login"
GIGYA_GET_JWT_ENDPOINT = f"{GIGYA_BASE_URL}/accounts.getJWT"

SESSION_EXPIRATION = 7776000

class GigyaApi:
    def __init__(self, hass: HomeAssistant, api_key: str):
        self.hass = hass
        self.api_key = api_key

    async def login(self, login_id: str, password: str) -> dict:
        payload = {
            "loginID": login_id,
            "password": password,
            "targetEnv": "mobile",
            "include": "id_token,profile,data,preferences",
            "sessionExpiration": SESSION_EXPIRATION,
            "format": "json",
            "apiKey": self.api_key,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        session = async_get_clientsession(self.hass)
        async with session.post(GIGYA_LOGIN_ENDPOINT, data=payload, headers=headers, timeout=30) as response:
            response.raise_for_status()
            response_data = await response.json(content_type=None)

        if response_data.get("statusCode") != 200:
            raise Exception(f"Login failed: {response_data.get('errorDetails', 'Unknown error')}")
        
        self.login_response_data = response_data
        session_token, session_secret = self.extract_session_credentials()
        jwt_response = await self.get_jwt(session_token, session_secret)
        self.aws_token = self.extract_aws_token(jwt_response)

    async def get_jwt(self, session_token: str, session_secret: str) -> dict:
        # App exchanges session credentials for a dedicated JWT before AWS calls.
        headers = {
            "Authorization": f"Bearer {session_token}",
            "Accept": "application/json"
        }
        params = {
            "secret": session_secret,
            "expiration": SESSION_EXPIRATION,
            "apiKey": self.api_key,
            "httpStatusCodes": "true",
        }
        session = async_get_clientsession(self.hass)
        async with session.post(GIGYA_GET_JWT_ENDPOINT, headers=headers, params=params, timeout=30) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

    def is_authenticated(self) -> bool:
        return hasattr(self, "aws_token") and self.aws_token is not None
    
    def extract_session_credentials(self) -> tuple[str, str]:
        session_info = self.login_response_data.get("sessionInfo") or {}
        session_token = session_info.get("sessionToken")
        session_secret = session_info.get("sessionSecret")
        if not session_token or not session_secret:
            raise ValueError("Login response missing sessionInfo.sessionToken or sessionInfo.sessionSecret")
        return session_token, session_secret
    
    def extract_aws_token(self, jwt_response: dict) -> str:
        token = jwt_response.get("idToken") or jwt_response.get("id_token")
        if not token:
            raise ValueError("getJWT response missing idToken")
        return token

       
