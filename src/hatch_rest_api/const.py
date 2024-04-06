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


class RIoTAudioTrack(Enum):
    NONE = 0
    BrownNoise = 10200
    WhiteNoise = 10137
    Ocean = 10138
    Thunderstorm = 10146
    Rain = 10139
    Water = 10142
    Wind = 10141
    Heartbeat = 10144
    Vacuum = 10198
    Dryer = 10143
    Fan = 10145
    ForestLake = 10082
    CalmSea = 10056
    Crickets = 10148
    CampfireLake = 10195
    Birds = 10140
    Brahms = 10192
    Twinkle = 10193
    RockABye = 10194

    @classmethod
    def sound_url_map(cls):
        """
        Hard-coded list, as some of these values are not returned by the 'sounds' API. These were found from manually browsing the app and playing each
        song, collecting the necessary values (name, id, url) from the Home Assistant debug logs for the `ha_hatch` custom component integration.
        Ideally, the API would return everything, but since Hatch does not appear to have public API documentation, this is the best we can do for now.
        If the API returns different URLs for any of the media (wav files), this map will automatically be updated below.
        See https://github.com/dahlb/ha_hatch/issues/95#issuecomment-2017905731 for more details.
        """
        sound_map = {
            # @formatter:off
            RIoTAudioTrack.BrownNoise.value:   "https://assets.ctfassets.net/hlsdh3zwyrtx/Bqk8q7mjFcSa8B1Ovgllp/e9701ae7df057a31b89a4cd2830ef0dc/Brown_Noise_2_20210412.wav",
            RIoTAudioTrack.WhiteNoise.value:   "https://assets.ctfassets.net/hlsdh3zwyrtx/2XkUiUT4vu1E69WMT3bxPo/099169855661de3b439135ad2fbd8098/003_pinknoise16.wav",
            RIoTAudioTrack.Ocean.value:        "https://assets.ctfassets.net/hlsdh3zwyrtx/3R5xnLn3hFpC6LGyDemp2U/15bab94907d16d34aaf5ce3cf5f27624/Crashing_Ocean_Waves_20210412.wav",
            RIoTAudioTrack.Thunderstorm.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/6orVWuV5mD15gNXHrBMgk4/ec9c0dab057698072870efc72d8d41fa/Thunderstorm_20210412.wav",
            RIoTAudioTrack.Rain.value:         "https://assets.ctfassets.net/hlsdh3zwyrtx/2K1xgB9CuO4tWuIxAOQ9p3/0d70a8f8b39d9f35c775f4e83923228f/Steady_Rain_20210412.wav",
            RIoTAudioTrack.Water.value:        "https://assets.ctfassets.net/hlsdh3zwyrtx/6SZPz15cBTaKWiXEtH2hwh/93f26a88f355bf4ca57f2a24fd6af510/002_waterstreamsmallclose16.wav",
            RIoTAudioTrack.Wind.value:         "https://assets.ctfassets.net/hlsdh3zwyrtx/6PG39YsVGqAE8CXdUZ2LJV/e869572e1a7423c086dfcaedda33a868/006_wind16.wav",
            RIoTAudioTrack.Heartbeat.value:    "https://assets.ctfassets.net/hlsdh3zwyrtx/2DydcI6HZ5KsqtnLWlSoNr/f2e93d60ffa12cf5fb303ed010e5df1d/001_heartbeat.wav",
            RIoTAudioTrack.Vacuum.value:       "https://assets.ctfassets.net/hlsdh3zwyrtx/5mg3e3BtpIn0YaQfOVVNRJ/528e94cfd7232481637fd3ce7c7141f2/Industrial_Vacuum_Cleaner_20191220.wav",
            RIoTAudioTrack.Dryer.value:        "https://assets.ctfassets.net/hlsdh3zwyrtx/4BsUei9xw0Qd1qrLOiPUCg/dc159c335c3fefa5c684b75e155eeed3/004_dryerclothes16.wav",
            RIoTAudioTrack.Fan.value:          "https://assets.ctfassets.net/hlsdh3zwyrtx/ndDbe0uTgVEiTBukiSIVP/14aede254b6bbfcff108c18b76d75f6a/FanNoise_20191122.wav",
            RIoTAudioTrack.ForestLake.value:   "https://downloads.ctfassets.net/hlsdh3zwyrtx/2WgzZNttwX5RK4twPtMCsS/64de4333300711282b42046020fc3aa0/Forest_Lake_20191220.wav",
            RIoTAudioTrack.CalmSea.value:      "https://assets.ctfassets.net/hlsdh3zwyrtx/1LelwPIVm5YZle7WP42u2X/b26f1d8a35b4c083a0bb65c9e323b7a7/Calm_Sea_20191220.wav",
            RIoTAudioTrack.Crickets.value:     "https://assets.ctfassets.net/hlsdh3zwyrtx/5X1S7xtEHyZab67wRbsEda/92f8bc6c927a384bd2262ebc6999465a/010_crickets16.wav",
            RIoTAudioTrack.CampfireLake.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/6Gb9MNlL9VcMcUmo4jzCSv/c457b63210359467e729fe7c1d624edd/Campfire_Lake_2_20210412.wav",
            RIoTAudioTrack.Birds.value:        "https://assets.ctfassets.net/hlsdh3zwyrtx/7zIxpw8gUhJQeI7fLaxNpz/0da0956663ac277e30886b256b1ade08/Morning_Birds_20210412.wav",
            RIoTAudioTrack.Brahms.value:       "https://assets.ctfassets.net/hlsdh3zwyrtx/2XXRwK0Xqw1KLBr28RIkSe/ee6af976c9980823389134eeded7f07b/011_brahms16.wav",
            RIoTAudioTrack.Twinkle.value:      "https://assets.ctfassets.net/hlsdh3zwyrtx/69qMR6Wp2hPD7gk7hSfRl5/25af4cefe997d5ba4070e71ae21e7eb3/013_twinkle16.wav",
            RIoTAudioTrack.RockABye.value:     "https://assets.ctfassets.net/hlsdh3zwyrtx/7lY2LJerpBhO7vravoQ14J/debcf202883c61eaa384ee826dec4026/014_rockabye16.wav",
            # @formatter:on
        }
        # TODO: Move the below asserts into a unit test (project needs unit tests added).
        assert len(sound_map) == len(RIoTAudioTrack) - 1, "Missing sound URL for one or more RIotAudioTrack"
        assert set(sound_map.keys()) == {track.value for track in RIoTAudioTrack if track != RIoTAudioTrack.NONE}, "Each RIotAudioTrack must have a unique sound URL in the map"
        return sound_map


REST_MINI_AUDIO_TRACKS = list(RestMiniAudioTrack)

REST_PLUS_AUDIO_TRACKS = list(RestPlusAudioTrack)

REST_IOT_AUDIO_TRACKS = list(RIoTAudioTrack)

RIOT_FLAGS_CLOCK_24_HOUR = 2048
RIOT_FLAGS_CLOCK_ON = 32768
