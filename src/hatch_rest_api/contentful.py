import asyncio
import logging

from aiohttp import ClientError, ClientResponse, ClientSession

from .errors import RateError

_LOGGER = logging.getLogger(__name__)

# https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/explore?access_token=w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI
API_URL: str = (
    "https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/environments/master"
)
AUTH_TOKEN: str = "w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI"


class Contentful:
    def __init__(self, client_session: ClientSession = None):
        self.api_session = client_session or ClientSession()

    async def cleanup_client_session(self):
        await self.api_session.close()

    async def graphql_query(self, query, auth_token=None, max_retries=3, **variables):
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
                    raise RateError(
                        "GraphQL API rate limit exceeded. Please wait before retrying."
                    )

                response.raise_for_status()

                try:
                    response_json = await response.json()
                except Exception:
                    try:
                        response_text = await response.text()
                        _LOGGER.error(
                            f"Failed to parse JSON response. Status: {response.status}, Content: {response_text[:500]}"
                        )
                    except Exception:
                        _LOGGER.error(
                            f"Failed to parse response. Status: {response.status}"
                        )
                    raise ClientError(
                        f"Invalid response format from GraphQL API (status: {response.status})"
                    )

                if response_json.get("errors"):
                    _LOGGER.error(f"GraphQL query error: {response_json['errors']}")
                    raise ClientError(f"GraphQL query error: {response_json['errors']}")

                return response_json.get("data")

            except RateError:
                retry_count += 1
                if retry_count > max_retries:
                    _LOGGER.error(
                        f"Maximum retries ({max_retries}) exceeded for GraphQL query"
                    )
                    raise

                wait_time = 2**retry_count
                _LOGGER.warning(
                    f"Rate limited. Retrying in {wait_time} seconds (attempt {retry_count}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
