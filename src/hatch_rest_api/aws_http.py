"""HTTP client for the AWS Cognito endpoints used by Hatch devices."""

import json
import logging
from typing import Any

from aiohttp import ClientResponse, ClientSession

from .util_http import request_with_logging

_LOGGER = logging.getLogger(__name__)

API_URL: str = "https://data.hatchbaby.com/"


class AwsHttp:
    """Minimal client for fetching AWS IoT credentials from Cognito."""

    def __init__(self, client_session: ClientSession | None = None) -> None:
        """Create the client, optionally reusing an existing aiohttp session."""
        if client_session is None:
            self.api_session = ClientSession(raise_for_status=True)
        else:
            self.api_session = client_session

    async def cleanup_client_session(self) -> None:
        """Close the underlying aiohttp session."""
        await self.api_session.close()

    @request_with_logging
    async def _post_request_with_logging_and_errors_raised(
        self, url: str, json_body: dict, headers: dict | None = None
    ) -> ClientResponse:
        return await self.api_session.post(url=url, json=json_body, headers=headers)

    async def aws_credentials(
        self,
        region: str,
        identityId: str,  # noqa: N803 - public keyword argument
        aws_token: str,
    ) -> dict[str, Any]:
        """Exchange a Cognito identity token for temporary AWS credentials.

        Args:
            region: AWS region of the Cognito identity pool.
            identityId: Cognito identity id returned by the Hatch API.
            aws_token: Cognito OpenID token returned by the Hatch API.

        Returns:
            The decoded ``GetCredentialsForIdentity`` response.
        """
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
        response: ClientResponse = await self._post_request_with_logging_and_errors_raised(
            url=url, json_body=json_body, headers=headers
        )
        data = await response.read()
        return json.loads(data)
