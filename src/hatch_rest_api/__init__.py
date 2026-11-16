"""Public package exports for the Hatch Rest API client."""

from .aws_http import AwsHttp
from .const import (
    REST_BABY_AUDIO_TRACKS,
    REST_IOT_AUDIO_TRACKS,
    REST_MINI_AUDIO_TRACKS,
    REST_PLUS_AUDIO_TRACKS,
    TIME_FOR_BED_TRACKS,
    TIME_TO_RISE_TRACKS,
    RestBabyAudioTrack,
    RestMiniAudioTrack,
    RestPlusAudioTrack,
    RIoTAudioTrack,
    TimeForBedTrack,
    TimeToRiseTrack,
)
from .errors import AuthError, BaseError, RateError
from .hatch import Hatch
from .rest_baby import RestBaby
from .rest_iot import RestIot
from .rest_mini import RestMini
from .rest_plus import RestPlus
from .restore_iot import RestoreIot
from .restore_v4 import RestoreV4
from .restore_v5 import RestoreV5
from .scheduled_routine import ScheduledRoutineAlarm
from .util_bootstrap import get_rest_devices

RestDevice = RestMini | RestPlus | RestIot | RestBaby | RestoreIot | RestoreV4 | RestoreV5

__all__ = [
    "REST_BABY_AUDIO_TRACKS",
    "REST_IOT_AUDIO_TRACKS",
    "REST_MINI_AUDIO_TRACKS",
    "REST_PLUS_AUDIO_TRACKS",
    "TIME_FOR_BED_TRACKS",
    "TIME_TO_RISE_TRACKS",
    "AuthError",
    "AwsHttp",
    "BaseError",
    "Hatch",
    "RIoTAudioTrack",
    "RateError",
    "RestBaby",
    "RestBabyAudioTrack",
    "RestDevice",
    "RestIot",
    "RestMini",
    "RestMiniAudioTrack",
    "RestPlus",
    "RestPlusAudioTrack",
    "RestoreIot",
    "RestoreV4",
    "RestoreV5",
    "ScheduledRoutineAlarm",
    "TimeForBedTrack",
    "TimeToRiseTrack",
    "get_rest_devices",
]
