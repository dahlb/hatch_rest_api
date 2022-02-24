from enum import Enum

SENSITIVE_FIELD_NAMES = [
    "username",
    "password",
]

MAX_IOT_VALUE = 65535


class RestMiniAudioTrack(Enum):
    NONE = 0
    Heartbeat = 10124
    Water = 10125
    WhiteNoise = 10126
    Dryer = 10127
    Ocean = 10128
    Wind = 10129
    Rain = 10130
    Birds = 10131


REST_MINI_AUDIO_TRACKS = [
    RestMiniAudioTrack.NONE,
    RestMiniAudioTrack.WhiteNoise,
    RestMiniAudioTrack.Ocean,
    RestMiniAudioTrack.Rain,
    RestMiniAudioTrack.Water,
    RestMiniAudioTrack.Wind,
    RestMiniAudioTrack.Birds,
    RestMiniAudioTrack.Dryer,
    RestMiniAudioTrack.Heartbeat,
]
