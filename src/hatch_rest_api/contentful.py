"""Client for Hatch content served from the Contentful GraphQL API."""

import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientResponseError, ClientSession

from .errors import RateError
from .util_http import DEFAULT_RATE_LIMIT_RETRIES, retry_when_rate_limited

_LOGGER = logging.getLogger(__name__)

# https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/explore?access_token=w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI
API_URL: str = "https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/environments/master"
AUTH_TOKEN: str = "w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI"  # noqa: S105 - public token


class Contentful:
    """Minimal client for the Contentful GraphQL API used by the Hatch app."""

    rate_limit_retries: int = DEFAULT_RATE_LIMIT_RETRIES

    def __init__(
        self,
        client_session: ClientSession | None = None,
        rate_limit_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
    ) -> None:
        """Create the client.

        Args:
            client_session: aiohttp session to reuse; one is created if omitted.
            rate_limit_retries: How many times to retry a rate-limited query before
                raising ``RateError``. 0 disables retries.
        """
        self.rate_limit_retries = rate_limit_retries
        self.api_session = client_session or ClientSession()

    async def cleanup_client_session(self) -> None:
        """Close the underlying aiohttp session."""
        await self.api_session.close()

    async def graphql_query(
        self,
        query: str,
        auth_token: str | None = None,
        max_retries: int | None = None,
        **variables: Any,
    ) -> Any:
        """Run a GraphQL query, retrying with backoff when rate limited.

        Args:
            query: GraphQL query document.
            auth_token: Optional Hatch auth token sent as ``X-HatchBaby-Auth``.
            max_retries: Retries after a rate-limit response; defaults to the client's
                ``rate_limit_retries``.
            **variables: GraphQL variables for the query.

        Returns:
            The ``data`` member of the GraphQL response.

        Raises:
            ClientError: If the response is not JSON or contains GraphQL errors.
            RateError: If still rate limited after ``max_retries`` retries.
        """
        retries = self.rate_limit_retries if max_retries is None else max_retries

        async def attempt() -> Any:
            headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
            if auth_token:
                headers["X-HatchBaby-Auth"] = auth_token

            try:
                response: ClientResponse = await self.api_session.post(
                    url=API_URL,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
            except ClientResponseError as err:
                # A caller's session made with raise_for_status=True raises on the 429.
                if err.status == 429:
                    _LOGGER.warning("Rate limited (429) for GraphQL query")
                    raise RateError("GraphQL API rate limit exceeded.") from err
                raise
            if response.status == 429:
                _LOGGER.warning("Rate limited (429) for GraphQL query")
                raise RateError("GraphQL API rate limit exceeded. Please wait before retrying.")

            response.raise_for_status()

            try:
                response_json = await response.json()
            except Exception as err:
                try:
                    response_text = await response.text()
                    _LOGGER.error(
                        "Failed to parse JSON response. Status: %s, Content: %s",
                        response.status,
                        response_text[:500],
                    )
                except Exception:  # noqa: BLE001 - best-effort diagnostics only
                    _LOGGER.error("Failed to parse response. Status: %s", response.status)
                raise ClientError(
                    f"Invalid response format from GraphQL API (status: {response.status})"
                ) from err

            if response_json.get("errors"):
                _LOGGER.error("GraphQL query error: %s", response_json["errors"])
                raise ClientError(f"GraphQL query error: {response_json['errors']}")

            return response_json.get("data")

        return await retry_when_rate_limited(attempt, retries, "GraphQL query")
