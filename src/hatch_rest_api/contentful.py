import logging

from aiohttp import ClientSession, ClientResponse, ClientError

_LOGGER = logging.getLogger(__name__)

# https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/explore?access_token=w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI
API_URL: str = "https://graphql.contentful.com/content/v1/spaces/hlsdh3zwyrtx/environments/master"
AUTH_TOKEN: str = "w81AL3BhokPlPGus5Pbs2UjK9hOEH-WYoJ4OOpOQpUI"


class Contentful:
    def __init__(self, client_session: ClientSession = None):
        self.api_session = client_session or ClientSession()

    async def cleanup_client_session(self):
        await self.api_session.close()

    async def graphql_query(self, query, **variables):
        response: ClientResponse = (
            await self.api_session.post(
                url=API_URL,
                json={
                    "query": query,
                    "variables": variables
                },
                headers={
                    "Authorization": f"Bearer {AUTH_TOKEN}",
                }
            )
        )
        response.raise_for_status()
        response_json = await response.json()
        if response_json.get("errors"):
            _LOGGER.error(f"GraphQL query error: {response_json['errors']}")
            raise ClientError(f"GraphQL query error: {response_json['errors']}")
        return response_json.get("data")
