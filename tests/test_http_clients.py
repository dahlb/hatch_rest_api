"""The Contentful and AWS Cognito HTTP clients send the right requests and handle errors."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientError
import pytest

from hatch_rest_api import AwsHttp, RateError
from hatch_rest_api.contentful import API_URL, AUTH_TOKEN, Contentful


def _response(
    status: int = 200, body: Any = None, json_error: Exception | None = None
) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.raise_for_status = MagicMock()
    if json_error is not None:
        response.json = AsyncMock(side_effect=json_error)
    else:
        response.json = AsyncMock(return_value=body)
    response.text = AsyncMock(return_value="<html>not json</html>")
    response.read = AsyncMock(return_value=json.dumps(body).encode())
    return response


def _session(*responses: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post = AsyncMock(side_effect=list(responses))
    return session


# ---- Contentful ------------------------------------------------------------------


async def test_graphql_query_returns_data() -> None:
    """A successful query returns the data member and sends the query and variables."""
    session = _session(_response(body={"data": {"soundCollection": {"items": []}}}))
    contentful = Contentful(client_session=session)

    data = await contentful.graphql_query("query Q { x }", auth_token="hatch-token", product="v5")

    assert data == {"soundCollection": {"items": []}}
    kwargs = session.post.call_args.kwargs
    assert kwargs["url"] == API_URL
    assert kwargs["json"] == {"query": "query Q { x }", "variables": {"product": "v5"}}
    assert kwargs["headers"] == {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "X-HatchBaby-Auth": "hatch-token",
    }


async def test_graphql_query_without_hatch_token() -> None:
    """With no Hatch token only the Contentful bearer token is sent."""
    session = _session(_response(body={"data": {}}))
    await Contentful(client_session=session).graphql_query("query Q { x }")
    assert session.post.call_args.kwargs["headers"] == {"Authorization": f"Bearer {AUTH_TOKEN}"}


async def test_graphql_errors_raise() -> None:
    """GraphQL errors in the response raise ClientError."""
    session = _session(_response(body={"errors": [{"message": "bad field"}]}))
    with pytest.raises(ClientError, match="bad field"):
        await Contentful(client_session=session).graphql_query("query Q { x }")


async def test_non_json_response_raises() -> None:
    """A body that isn't JSON raises ClientError."""
    session = _session(_response(json_error=ValueError("no json")))
    with pytest.raises(ClientError, match="Invalid response format"):
        await Contentful(client_session=session).graphql_query("query Q { x }")


async def test_rate_limit_is_retried_with_backoff() -> None:
    """A 429 is retried after an exponential backoff, then succeeds."""
    session = _session(_response(status=429), _response(status=429), _response(body={"data": 1}))
    with patch("hatch_rest_api.util_http.asyncio.sleep", new=AsyncMock()) as sleep:
        data = await Contentful(client_session=session).graphql_query("query Q { x }")

    assert data == 1
    assert [call.args[0] for call in sleep.await_args_list] == [2, 4]


async def test_rate_limit_gives_up_after_max_retries() -> None:
    """After max_retries rate-limited retries, RateError is raised."""
    session = _session(*(_response(status=429) for _ in range(3)))
    with (
        patch("hatch_rest_api.util_http.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RateError),
    ):
        await Contentful(client_session=session).graphql_query("query Q { x }", max_retries=2)
    assert session.post.await_count == 3


async def test_contentful_closes_its_session() -> None:
    """cleanup_client_session closes the aiohttp session."""
    session = MagicMock()
    session.close = AsyncMock()
    await Contentful(client_session=session).cleanup_client_session()
    session.close.assert_awaited_once_with()


# ---- AWS Cognito -----------------------------------------------------------------


async def test_aws_credentials_request() -> None:
    """aws_credentials calls Cognito GetCredentialsForIdentity and decodes the reply."""
    credentials = {"Credentials": {"AccessKeyId": "AKIA", "SecretKey": "s", "SessionToken": "t"}}
    session = _session(_response(body=credentials))

    result = await AwsHttp(client_session=session).aws_credentials(
        region="us-west-2", identityId="identity-1", aws_token="openid-token"
    )

    assert result == credentials
    kwargs = session.post.call_args.kwargs
    assert kwargs["url"] == "https://cognito-identity.us-west-2.amazonaws.com"
    assert kwargs["json"] == {
        "IdentityId": "identity-1",
        "Logins": {"cognito-identity.amazonaws.com": "openid-token"},
    }
    assert kwargs["headers"] == {
        "content-type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
    }


async def test_aws_http_closes_its_session() -> None:
    """cleanup_client_session closes the aiohttp session."""
    session = MagicMock()
    session.close = AsyncMock()
    await AwsHttp(client_session=session).cleanup_client_session()
    session.close.assert_awaited_once_with()
