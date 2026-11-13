from aiohttp import ClientError


class BaseError(ClientError):
    pass


class RateError(BaseError):
    pass


class AuthError(BaseError):
    pass


class DeviceSyncError(BaseError):
    """The device did not confirm a change it had to take over MQTT."""
