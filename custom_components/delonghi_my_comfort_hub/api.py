
import requests

from custom_components.delonghi_my_comfort_hub.gigya_api import GigyaApi

AWS_BASE_URL = "https://8q8c9xktb0.execute-api.eu-central-1.amazonaws.com/dlg-prod/"
AWS_OTHER_URL = "https://gax54h1o65.execute-api.us-east-1.amazonaws.com/dlg-prod/"
AWS_DEVICES_URL = AWS_BASE_URL + "devices"
AWS_JOBS_URL = AWS_OTHER_URL + "jobs"

AWS_SOURCE_HEADER = "comfort"

class MyComfortHubApi:
    def __init__(self, username: str, password: str, gigya_api_key: str):
        self.username = username
        self.password = password
        self.gigya_api_key = gigya_api_key
        self.gigya_api = GigyaApi(gigya_api_key)

    async def authenticate(self):
        await self.gigya_api.login(self.username, self.password)

        if not self.gigya_api.is_authenticated():
            raise Exception("Authentication failed with Gigya API")
        
        pass

    def is_authenticated(self) -> bool:
        return self.gigya_api.is_authenticated()

    def get_devices(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.gigya_api.aws_token}",
            "source": AWS_SOURCE_HEADER,
        }
        response = requests.get(AWS_DEVICES_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()