import logging

from aiohttp import ClientSession, ClientResponse
import json

from .util_http import request_with_logging

_LOGGER = logging.getLogger(__name__)

API_URL: str = "https://data.hatchbaby.com/"


class AwsHttp:
    def __init__(self, client_session: ClientSession = None):
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=True)
        else:
            self.api_session = client_session

    async def cleanup_client_session(self):
        await self.api_session.close()

    @request_with_logging
    async def _post_request_with_logging_and_errors_raised(
        self, url: str, json_body: dict, headers: dict = None
    ) -> ClientResponse:
        return await self.api_session.post(url=url, json=json_body, headers=headers)

    async def aws_credentials(self, region: str, identityId: str, aws_token: str):
        url = f"https://cognito-identity.{region}.amazonaws.com"
        json_body = {
            "IdentityId": identityId,
            "Logins": {
                "cognito-identity.amazonaws.com": aws_token,
            },
        }
        headers = {
            "content-type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
        }
        response: ClientResponse = (
            await self._post_request_with_logging_and_errors_raised(
                url=url, json_body=json_body, headers=headers
            )
        )
        data = await response.read()
        return json.loads(data)
