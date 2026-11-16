"""Client for Hatch content served from the Contentful GraphQL API."""

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .errors import RateError

_LOGGER = logging.getLogger(__name__)

# https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/explore?access_token=w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI
API_URL: str = "https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/environments/master"
AUTH_TOKEN: str = "w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI"  # noqa: S105 - public token


class Contentful:
    """Minimal client for the Contentful GraphQL API used by the Hatch app."""

    def __init__(self, client_session: ClientSession | None = None) -> None:
        """Create the client, optionally reusing an existing aiohttp session."""
        self.api_session = client_session or ClientSession()

    async def cleanup_client_session(self) -> None:
        """Close the underlying aiohttp session."""
        await self.api_session.close()

    async def graphql_query(
        self,
        query: str,
        auth_token: str | None = None,
        max_retries: int = 3,
        **variables: Any,
    ) -> Any:
        """Run a GraphQL query, retrying with backoff when rate limited.

        Args:
            query: GraphQL query document.
            auth_token: Optional Hatch auth token sent as ``X-HatchBaby-Auth``.
            max_retries: Number of retries after a rate-limit response.
            **variables: GraphQL variables for the query.

        Returns:
            The ``data`` member of the GraphQL response.

        Raises:
            ClientError: If the response is not JSON or contains GraphQL errors.
            RateError: If still rate limited after ``max_retries`` retries.
        """
        retry_count = 0
        while True:
            try:
                headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
                if auth_token:
                    headers["X-HatchBaby-Auth"] = auth_token

                response: ClientResponse = await self.api_session.post(
                    url=API_URL,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
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

            except RateError:
                retry_count += 1
                if retry_count > max_retries:
                    _LOGGER.error("Maximum retries (%s) exceeded for GraphQL query", max_retries)
                    raise

                wait_time = 2**retry_count
                _LOGGER.warning(
                    "Rate limited. Retrying in %s seconds (attempt %s/%s)",
                    wait_time,
                    retry_count,
                    max_retries,
                )
                await asyncio.sleep(wait_time)
