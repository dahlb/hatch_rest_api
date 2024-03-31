import logging

from .types import SoundContent

from .util import (
    convert_to_percentage,
    safely_get_json_value,
    convert_from_percentage,
    convert_from_hex,
    convert_to_hex,
)
from .const import RIOT_FLAGS_CLOCK_ON, RIOT_FLAGS_CLOCK_24_HOUR, RIoTAudioTrack
from .shadow_client_subscriber import ShadowClientSubscriberMixin

_LOGGER = logging.getLogger(__name__)


class RestIot(ShadowClientSubscriberMixin):
    audio_track: RIoTAudioTrack = None
    firmware_version: str = None
    volume: int = 0

    is_online: bool = False
    current_playing: str = "none"

    battery_level: int = None
    color_id: int = 9998
    sound_id: int = 19998
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    brightness: int = 0
    charging_status: int = None  # Expected values: 0= Not Charging, 3= Charging, plugged in, 5= Charging, on base
    clock: int = None
    flags: int = None
    toddler_lock: bool = False
    toddler_lock_mode: str = None

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "deviceInfo.b") is not None:
            self.battery_level = safely_get_json_value(state, "deviceInfo.b", int)
        if safely_get_json_value(state, "deviceInfo.powerStatus") is not None:
            self.charging_status = safely_get_json_value(
                state, "deviceInfo.powerStatus", int
            )
        if safely_get_json_value(state, "toddlerLockOn") is not None:
            self.toddler_lock = safely_get_json_value(state, "toddlerLockOn", bool)
        if safely_get_json_value(state, "toddlerLock.turnOnMode") is not None:
            self.toddler_lock_mode = safely_get_json_value(
                state, "toddlerLock.turnOnMode", str
            )
        if safely_get_json_value(state, "current.playing") is not None:
            self.current_playing = safely_get_json_value(state, "current.playing")
        if safely_get_json_value(state, "connected") is not None:
            self.is_online = safely_get_json_value(state, "connected", bool)
        if safely_get_json_value(state, "current.sound.v") is not None:
            self.volume = convert_to_percentage(
                safely_get_json_value(state, "current.sound.v", int)
            )
        if safely_get_json_value(state, "current.sound.id", int) is not None:
            self.sound_id = safely_get_json_value(state, "current.sound.id", int)
            self.audio_track = RIoTAudioTrack(self.sound_id)
        if safely_get_json_value(state, "current.color.id") is not None:
            self.color_id = safely_get_json_value(state, "current.color.id", int)
        if safely_get_json_value(state, "current.color.w") is not None:
            self.white = safely_get_json_value(state, "current.color.w", int)
        if safely_get_json_value(state, "current.color.r") is not None:
            self.red = convert_to_hex(
                safely_get_json_value(state, "current.color.r", int)
            )
        if safely_get_json_value(state, "current.color.g") is not None:
            self.green = convert_to_hex(
                safely_get_json_value(state, "current.color.g", int)
            )
        if safely_get_json_value(state, "current.color.b") is not None:
            self.blue = convert_to_hex(
                safely_get_json_value(state, "current.color.b", int)
            )
        if safely_get_json_value(state, "current.color.i") is not None:
            self.brightness = convert_to_percentage(
                safely_get_json_value(state, "current.color.i", int)
            )
        if safely_get_json_value(state, "clock.i") is not None:
            self.clock = convert_to_percentage(
                safely_get_json_value(state, "clock.i", int)
            )
        if safely_get_json_value(state, "clock.flags") is not None:
            self.flags = safely_get_json_value(state, "clock.flags", int)

        _LOGGER.debug(f"new state:{self}")
        self.publish_updates()

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "firmware_version": self.firmware_version,
            "is_online": self.is_online,
            "is_on": self.is_on,
            "battery_level": self.battery_level,
            "is_playing": self.is_playing,
            "audio_track": self.audio_track,
            "sound_id": self.sound_id,
            "volume": self.volume,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "brightness": self.brightness,
            "document_version": self.document_version,
            "charging_status": self.charging_status,
            "clock": self.clock,
            "flags": self.flags,
            "is_clock_on": self.is_clock_on,
            "is_clock_24h": self.is_clock_24h,
            "toddler_lock": self.toddler_lock,
            "toddler_lock_mode": self.toddler_lock_mode,
        }

    def __str__(self):
        return f"{self.__repr__()}"

    @property
    def is_on(self):
        return self.is_light_on or self.is_playing

    @property
    def is_light_on(self):
        return self.color_id != 9998 and self.color_id != 0

    @property
    def is_playing(self):
        return self.sound_id != 19998

    @property
    def is_clock_on(self):
        return self.flags is not None and self.flags & RIOT_FLAGS_CLOCK_ON

    @property
    def is_clock_24h(self):
        return self.flags is not None and self.flags & RIOT_FLAGS_CLOCK_24_HOUR

    def favorite_names(self, active_only: bool = True):
        names = []
        for favorite in self.favorites:
            if active_only and favorite["active"]:
                names.append(f"{favorite['name']}-{favorite['id']}")
            else:
                names.append(f"{favorite['name']}-{favorite['id']}")
        return names

    def set_volume(self, percentage: int):
        _LOGGER.debug(f"Setting volume: {percentage}")
        self._update({"current": {"sound": {"v": convert_from_percentage(percentage)}}})

    # Expected string value for mode is "never" or "always". The API also supports "custom" for defining a time range
    def set_toddler_lock(self, on: bool):
        _LOGGER.debug(f"Setting Toddler On Lock: {on}")
        mode = "always" if on else "never"
        self._update({"toddlerLock": {"turnOnMode": mode}})

    def set_clock(self, brightness: int = 0):
        _LOGGER.debug(f"Setting clock on: {brightness}")
        self._update(
            {
                "clock": {
                    "flags": self.flags | RIOT_FLAGS_CLOCK_ON,
                    "i": convert_from_percentage(brightness),
                }
            }
        )

    def turn_clock_off(self):
        _LOGGER.debug("Turn off clock")
        self._update({"clock": {"flags": self.flags ^ RIOT_FLAGS_CLOCK_ON, "i": 655}})

    # favorite_name_id is expected to be a string of name-id since name alone isn't unique
    def set_favorite(self, favorite_name_id: str):
        _LOGGER.debug(f"Setting favorite: {favorite_name_id}")
        fav_id = int(favorite_name_id.rsplit("-", 1)[1])
        self._update({"current": {"srId": fav_id, "step": 1, "playing": "routine"}})

    def set_audio_track(self, audio_track: RIoTAudioTrack):
        _LOGGER.debug(f"Setting audio track: {audio_track}")
        if audio_track == RIoTAudioTrack.NONE:
            self.turn_off()
            return
        # Hard-coded list, as some of these values are not returned by the 'sounds' API. These were found from manually browsing the app and playing each
        # song, collecting the necessary values (name, id, url) from the Home Assistant debug logs for the `ha_hatch` custom component integration.
        # Ideally, the API would return everything, but since Hatch does not appear to have public API documentation, this is the best we can do for now.
        # If the API returns different URLs for any of the media (wav files), this map will automatically be updated below.
        # See https://github.com/dahlb/ha_hatch/issues/95#issuecomment-2017905731 for more details.
        sound_url_map = {
            RIoTAudioTrack.BrownNoise.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/Bqk8q7mjFcSa8B1Ovgllp/e9701ae7df057a31b89a4cd2830ef0dc/Brown_Noise_2_20210412.wav",
            RIoTAudioTrack.WhiteNoise.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/2XkUiUT4vu1E69WMT3bxPo/099169855661de3b439135ad2fbd8098/003_pinknoise16.wav",
            RIoTAudioTrack.Ocean.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/3R5xnLn3hFpC6LGyDemp2U/15bab94907d16d34aaf5ce3cf5f27624/Crashing_Ocean_Waves_20210412.wav",
            RIoTAudioTrack.Thunderstorm.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/6orVWuV5mD15gNXHrBMgk4/ec9c0dab057698072870efc72d8d41fa/Thunderstorm_20210412.wav",
            RIoTAudioTrack.Rain.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/2K1xgB9CuO4tWuIxAOQ9p3/0d70a8f8b39d9f35c775f4e83923228f/Steady_Rain_20210412.wav",
            RIoTAudioTrack.Water.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/6SZPz15cBTaKWiXEtH2hwh/93f26a88f355bf4ca57f2a24fd6af510/002_waterstreamsmallclose16.wav",
            RIoTAudioTrack.Wind.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/6PG39YsVGqAE8CXdUZ2LJV/e869572e1a7423c086dfcaedda33a868/006_wind16.wav",
            RIoTAudioTrack.Heartbeat.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/2DydcI6HZ5KsqtnLWlSoNr/f2e93d60ffa12cf5fb303ed010e5df1d/001_heartbeat.wav",
            RIoTAudioTrack.Vacuum.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/5mg3e3BtpIn0YaQfOVVNRJ/528e94cfd7232481637fd3ce7c7141f2/Industrial_Vacuum_Cleaner_20191220.wav",
            RIoTAudioTrack.Dryer.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/4BsUei9xw0Qd1qrLOiPUCg/dc159c335c3fefa5c684b75e155eeed3/004_dryerclothes16.wav",
            RIoTAudioTrack.Fan.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/ndDbe0uTgVEiTBukiSIVP/14aede254b6bbfcff108c18b76d75f6a/FanNoise_20191122.wav",
            RIoTAudioTrack.ForestLake.value: "https://downloads.ctfassets.net/hlsdh3zwyrtx/2WgzZNttwX5RK4twPtMCsS/64de4333300711282b42046020fc3aa0/Forest_Lake_20191220.wav",
            RIoTAudioTrack.CalmSea.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/1LelwPIVm5YZle7WP42u2X/b26f1d8a35b4c083a0bb65c9e323b7a7/Calm_Sea_20191220.wav",
            RIoTAudioTrack.Crickets.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/5X1S7xtEHyZab67wRbsEda/92f8bc6c927a384bd2262ebc6999465a/010_crickets16.wav",
            RIoTAudioTrack.CampfireLake.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/6Gb9MNlL9VcMcUmo4jzCSv/c457b63210359467e729fe7c1d624edd/Campfire_Lake_2_20210412.wav",
            # RIoTAudioTrack.CampfireLake.value: "https://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3",
            RIoTAudioTrack.Birds.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/7zIxpw8gUhJQeI7fLaxNpz/0da0956663ac277e30886b256b1ade08/Morning_Birds_20210412.wav",
            RIoTAudioTrack.Brahms.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/2XXRwK0Xqw1KLBr28RIkSe/ee6af976c9980823389134eeded7f07b/011_brahms16.wav",
            RIoTAudioTrack.Twinkle.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/69qMR6Wp2hPD7gk7hSfRl5/25af4cefe997d5ba4070e71ae21e7eb3/013_twinkle16.wav",
            RIoTAudioTrack.RockABye.value: "https://assets.ctfassets.net/hlsdh3zwyrtx/7lY2LJerpBhO7vravoQ14J/debcf202883c61eaa384ee826dec4026/014_rockabye16.wav",
        }
        # update the map with any changes from the API
        sound_url_map.update({
            sound.get('id'): sound.get('wavUrl') for sound in self.sounds
        })
        _LOGGER.debug(f'Available Sounds: {sound_url_map}')
        self._update({"current": {"playing": "remote", "step": 1, "sound": {
                "id": audio_track.value,
                "url": sound_url_map[audio_track.value],
                "mute": False,
                "until": "indefinite",
            }}})

    def set_sound(self, sound: SoundContent, duration: int = 0, until="indefinite"):
        """
        Pass a SoundContent item from self.sounds
        """
        _LOGGER.debug(f"Setting sound: {sound['title']}")
        self._update(
            {
                "current": {
                    "playing": "remote",
                    "sound": {
                        # not clear if this is the right ID, but it also doesn't appear to matter?
                        "id": sound["contentId"],
                        "mute": False,
                        "url": sound.get("wavUrl") or sound.get("mp3Url"),
                        "duration": duration,
                        "until": until,
                    },
                }
            }
        )

    def set_sound_url(self, sound_url: str = 'http://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3'):
        """
        appears to work with some but not all public wav and mp3 urls

        i.e. http://codeskulptor-demos.commondatastorage.googleapis.com/GalaxyInvaders/theme_01.mp3
        """
        _LOGGER.debug(f"Setting sound URL: {sound_url}")
        self._update(
            {
                "current": {
                    "playing": "remote",
                    "sound": {"mute": False, "url": sound_url},
                }
            }
        )

    def turn_off(self):
        _LOGGER.debug("Turning off sound")
        self._update({"current": {"srId": 0, "step": 0, "playing": "none"}})

    def turn_light_off(self):
        _LOGGER.debug("Turning light off")
        # 9999 = custom color 9998 = turn off
        # if favorite is playing then light can be turned off without turning off sound
        if self.current_playing == "routine":
            self._update(
                {
                    "current": {
                        "color": {
                            "id": 9998,
                            "r": 0,
                            "g": 0,
                            "b": 0,
                            "w": 0,
                        }
                    }
                }
            )
        if self.current_playing == "remote":
            self._update(
                {
                    "current": {
                        "playing": "none",
                        "color": {
                            "id": 9998,
                            "r": 0,
                            "g": 0,
                            "b": 0,
                            "w": 0,
                        },
                    }
                }
            )

    def set_color(
        self, red: int, green: int, blue: int, white: int = 0, brightness: int = 0
    ):
        # 9999 = custom color 9998 = turn off
        new_color_id: int = 9999
        _LOGGER.debug(
            f"red: {red} green: {green} blue: {blue} brightness: {brightness} white: {white}"
        )
        # If there is no sound playing, and you want to turn on the light the playing value has to be set to remote
        if self.current_playing == "none":
            self._update(
                {
                    "current": {
                        "srId": 0,
                        "step": 0,
                        "playing": "remote",
                        "color": {
                            "id": new_color_id,
                            "r": convert_from_hex(red),
                            "g": convert_from_hex(green),
                            "b": convert_from_hex(blue),
                            "i": convert_from_percentage(brightness),
                            "w": white,
                        },
                    }
                }
            )
        self._update(
            {
                "current": {
                    "color": {
                        "id": new_color_id,
                        "r": convert_from_hex(red),
                        "g": convert_from_hex(green),
                        "b": convert_from_hex(blue),
                        "i": convert_from_percentage(brightness),
                        "w": white,
                    }
                }
            }
        )
