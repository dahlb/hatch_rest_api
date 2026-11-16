"""Exceptions raised by the Hatch Rest API client."""

from aiohttp import ClientError


class BaseError(ClientError):
    """Base class for all errors raised by this library."""


class RateError(BaseError):
    """Raised when the Hatch API rate limits a request."""


class AuthError(BaseError):
    """Raised when the Hatch API rejects the supplied credentials."""
