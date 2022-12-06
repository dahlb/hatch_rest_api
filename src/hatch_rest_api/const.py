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


class RestPlusAudioTrack(Enum):
    NONE = 0
    Stream = 2
    PinkNoise = 3
    Dryer = 4
    Ocean = 5
    Wind = 6
    Rain = 7
    Bird = 9
    Crickets = 10
    Brahms = 11
    Twinkle = 13
    RockABye = 14


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


REST_PLUS_AUDIO_TRACKS = [
    RestPlusAudioTrack.NONE,
    RestPlusAudioTrack.Stream,
    RestPlusAudioTrack.PinkNoise,
    RestPlusAudioTrack.Dryer,
    RestPlusAudioTrack.Ocean,
    RestPlusAudioTrack.Wind,
    RestPlusAudioTrack.Rain,
    RestPlusAudioTrack.Bird,
    RestPlusAudioTrack.Crickets,
    RestPlusAudioTrack.Brahms,
    RestPlusAudioTrack.Twinkle,
    RestPlusAudioTrack.RockABye,
]
