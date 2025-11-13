from enum import Enum

SENSITIVE_FIELD_NAMES = [
    "username",
    "password",
]

MAX_IOT_VALUE = 2 ** 16 - 1

NO_COLOR_ID = 9998
CUSTOM_COLOR_ID = 9999
NO_SOUND_ID = 19998


class RestMiniAudioTrack(int, Enum):
    NONE = 0
    Heartbeat = 10124
    Water = 10125
    WhiteNoise = 10126
    Dryer = 10127
    Ocean = 10128
    Wind = 10129
    Rain = 10130
    Birds = 10131


class RestPlusAudioTrack(int, Enum):
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


class RIoTAudioTrack(int, Enum):
    NONE = NO_SOUND_ID
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
    def sound_url_map(cls) -> dict[int, str]:
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


class TimeToRiseTrack(Enum):
    """Time-to-Rise tracks for waking up children peacefully."""
    NONE = 0
    MorningBirdcalls = 31229
    WindChimes = 30555
    AmbientSunrise = 30554
    MagicalMorning = 32210
    PeacefulFlute = 30495
    YukiSaysGoodMorning = 30494
    JoyfulMorning = 30496
    Crickets = 30556
    CalmingCreek = 30553
    ChorusOfBirds = 30552

    @classmethod
    def track_url_map(cls):
        """
        URLs for Time-to-Rise tracks discovered via Contentful GraphQL API.
        These tracks use MP3 format instead of WAV.
        """
        track_map = {
            # @formatter:off
            TimeToRiseTrack.MorningBirdcalls.value:     "https://downloads.ctfassets.net/hlsdh3zwyrtx/6bFP4jzJOs4QYSMRctqn5e/2f90337e25b0345ed2a2bcc9a350ef79/BeRIOTBirds_20220523.mp3",
            TimeToRiseTrack.WindChimes.value:           "https://downloads.ctfassets.net/hlsdh3zwyrtx/RkFSHFj4I2q6QA9DWOdAW/f016c0c57b9ae76c3d62ec71e4d147c9/BeRIOTWindChimesTTR_20220701.mp3",
            TimeToRiseTrack.AmbientSunrise.value:       "https://downloads.ctfassets.net/hlsdh3zwyrtx/dUnnFSCAdfHUHV3KeTyZz/c4220727e18d422383e7c135245b6f03/BeRIOTAmbientSunriseTTR_20220701.mp3",
            TimeToRiseTrack.MagicalMorning.value:       "https://downloads.ctfassets.net/hlsdh3zwyrtx/3ulDMFt5yOz8r8ujEesQg0/d338354cf925f6ee2a5393b4b5ed70d9/RIOT_BeaconTTR_SMA_001_MFV2_20231026.mp3",
            TimeToRiseTrack.PeacefulFlute.value:        "https://downloads.ctfassets.net/hlsdh3zwyrtx/3zcCubh7Eti9GVJsVsWuz0/6b58f52fe3beec005368980b3f846972/BeRIOTFluteTTR_20220607.mp3",
            TimeToRiseTrack.YukiSaysGoodMorning.value:  "https://downloads.ctfassets.net/hlsdh3zwyrtx/5LwHOXdzCEm8QZYmpvisMi/dcdf2af6b83478015e96d4d64754f29b/BeRIOTYukiTTR_20220608.mp3",
            TimeToRiseTrack.JoyfulMorning.value:        "https://downloads.ctfassets.net/hlsdh3zwyrtx/7dHKC0dbi6LN4yNIZ5gRHz/622b9c3b5caabad46d2c56d32488c5f2/BeRIOTGameMusicTTR_20220607.mp3",
            TimeToRiseTrack.Crickets.value:             "https://downloads.ctfassets.net/hlsdh3zwyrtx/3JmbsDSF3Nbtz6iWveVbpI/c13f88d1898d4facb83c8c8d42224c71/BeRIOTCrickets_20220701.mp3",
            TimeToRiseTrack.CalmingCreek.value:         "https://downloads.ctfassets.net/hlsdh3zwyrtx/1hxTc4hs18CaeQIdjHFktM/3b5ea1870012c8b5b049028e77b1e453/BeRIOTCreekTTR_20220701.mp3",
            TimeToRiseTrack.ChorusOfBirds.value:        "https://downloads.ctfassets.net/hlsdh3zwyrtx/3X2vJqiqq73Igqiwwr2Tjf/a29fb2fffe21d8bb08fe9618c59392ce/BeRIOTBirdsChorusTTR_20220701.mp3",
            # @formatter:on
        }
        assert len(track_map) == len(TimeToRiseTrack) - 1, "Missing track URL for one or more TimeToRiseTrack"
        assert set(track_map.keys()) == {track.value for track in TimeToRiseTrack if track != TimeToRiseTrack.NONE}, "Each TimeToRiseTrack must have a unique track URL in the map"
        return track_map


class TimeForBedTrack(Enum):
    """Time-for-Bed tracks for helping children wind down for bedtime."""
    NONE = 0
    CalmingMelody = 30468
    LunarLanding = 30574
    WizardlyWindDown = 32211
    GoodnightAtTheZoo = 30575
    IfYoureSleepyAndYouKnowIt = 30576
    YukiSaysGoodNight = 30467
    AlejandroSaysGoodnight = 31524
    MariSaysGoodnight = 31525
    CountdownToBedtime = 32645
    BedtimeBirdCalls = 30469
    SpringBlossom = 31530
    DreamySnowfall = 31228
    SleighBells = 31227
    GhoulsGoodnight = 32132

    @classmethod
    def track_url_map(cls):
        """
        URLs for Time-for-Bed tracks discovered via Contentful GraphQL API.
        These tracks use MP3 format instead of WAV.
        """
        track_map = {
            # @formatter:off
            TimeForBedTrack.CalmingMelody.value:               "https://downloads.ctfassets.net/hlsdh3zwyrtx/51Ibsd3UCiRHoW0p8oZzOk/1054209064c982306b0b4bb60034544a/BeRIOTLullaby_20220523.mp3",
            TimeForBedTrack.LunarLanding.value:                "https://downloads.ctfassets.net/hlsdh3zwyrtx/5jVMkiO6uZ7OJCPi9ZDGNg/579a1ba92d978db0467d1da5a0c24987/RIOT_BedtimeBeacon_LunarLanding_001_MFV2_20230714.mp3",
            TimeForBedTrack.WizardlyWindDown.value:            "https://downloads.ctfassets.net/hlsdh3zwyrtx/46UjftJMHmZOtaBdUqyKvS/492c5f9ec81e0dc009bb85980f899ec8/RIOT_BeaconTFB_SMA_001_MFV2_20231026.mp3",
            TimeForBedTrack.GoodnightAtTheZoo.value:           "https://downloads.ctfassets.net/hlsdh3zwyrtx/20VnNzs5kQS227wfTt56UG/9a7eb6d20c4cb98d97fed7379f8bc13c/RIOT_BedtimeBeacon_BTZ_001_MFV2_20230714.mp3",
            TimeForBedTrack.IfYoureSleepyAndYouKnowIt.value:   "https://downloads.ctfassets.net/hlsdh3zwyrtx/8WIpBjDrBvoHZkqtjrzRY/cd199f910b3d794984ecf3265a18d54b/RIOT_BedtimeBeacon_IfYoureSleepy_001_MFV2_20230714.mp3",
            TimeForBedTrack.YukiSaysGoodNight.value:           "https://downloads.ctfassets.net/hlsdh3zwyrtx/2yUnMc2rk8fUZDrWNfCRZW/026de8f255908b8533a3a9a61330b708/BeRIOTYuki1_20220523.mp3",
            TimeForBedTrack.AlejandroSaysGoodnight.value:      "https://downloads.ctfassets.net/hlsdh3zwyrtx/4Qc41AnIMq8ciJmksgRJu5/adab0adbd858f3dd89236f43a2d2c0e5/RIOT_BedtimeBeacon_Alejandro_001_MFV2_20230714.mp3",
            TimeForBedTrack.MariSaysGoodnight.value:           "https://downloads.ctfassets.net/hlsdh3zwyrtx/4Ibh018V6UV3OjUsLPHN5o/e4652174e29af36333b99c853c889684/RIOT_BedtimeBeacon_Mari_001_MFV2_20230714.mp3",
            TimeForBedTrack.CountdownToBedtime.value:          "https://downloads.ctfassets.net/hlsdh3zwyrtx/3qqocW29tpRWg0ZhWNbnnM/9e22f2ac2f01a687921d7aa8132804ea/RIOT_Countdown_000_MFV1_20231219.mp3",
            TimeForBedTrack.BedtimeBirdCalls.value:            "https://downloads.ctfassets.net/hlsdh3zwyrtx/6bFP4jzJOs4QYSMRctqn5e/2f90337e25b0345ed2a2bcc9a350ef79/BeRIOTBirds_20220523.mp3",
            TimeForBedTrack.SpringBlossom.value:               "https://downloads.ctfassets.net/hlsdh3zwyrtx/5mzfIGB0UlE9T1NS2rBFwC/b4d85742a671f731c290e501ee32f605/BeRIOT_SpringBlossom_CGV2_20230317.mp3",
            TimeForBedTrack.DreamySnowfall.value:              "https://downloads.ctfassets.net/hlsdh3zwyrtx/6EUTdOKJi9HsAi48mfnP8t/5df4b215d75d2309d3cadc7f6f4b9a10/RIOT_TFB_MerryandBright_CGV1_20221114.mp3",
            TimeForBedTrack.SleighBells.value:                 "https://downloads.ctfassets.net/hlsdh3zwyrtx/5NANP23SRmJ3ltGkDWJUEp/1577ab256deabb4849a4e44587a23544/RIOT_TFB_WinterWonder_CGV1_20221114.mp3",
            TimeForBedTrack.GhoulsGoodnight.value:             "https://downloads.ctfassets.net/hlsdh3zwyrtx/7JhJvrNhqj7OtLbexTZiRM/53e14ea17f92ec3449ac23f1f881cb1e/RIOT_BeaconTFB_GhoulsGoodnight_001_MFV1_20231018.mp3",
            # @formatter:on
        }
        assert len(track_map) == len(TimeForBedTrack) - 1, "Missing track URL for one or more TimeForBedTrack"
        assert set(track_map.keys()) == {track.value for track in TimeForBedTrack if track != TimeForBedTrack.NONE}, "Each TimeForBedTrack must have a unique track URL in the map"
        return track_map


TIME_TO_RISE_TRACKS = list(TimeToRiseTrack)

TIME_FOR_BED_TRACKS = list(TimeForBedTrack)

RIOT_FLAGS_CLOCK_24_HOUR = 1 << 11
RIOT_FLAGS_CLOCK_ON = 1 << 15
RIOT_FLAGS_CLOCK_IGNORE_TAP = 1 << 5
