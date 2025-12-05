import contextlib
import logging

from .types import SoundContent, SimpleSoundContent
from .util import (
    convert_to_percentage,
    safely_get_json_value,
    convert_from_percentage,
    convert_from_hex,
    convert_to_hex,
)
from .const import (
    NO_SOUND_ID,
    NO_COLOR_ID,
    CUSTOM_COLOR_ID,
    RIoTAudioTrack,
    RestBabyAudioTrack,
)
from .shadow_client_subscriber import ShadowClientSubscriberMixin

_LOGGER = logging.getLogger(__name__)


class RestBaby(ShadowClientSubscriberMixin):
    audio_track: RestBabyAudioTrack = None
    firmware_version: str = None
    volume: int = 0

    is_online: bool = False
    current_playing: str = "none"
    current_id: int = 0
    current_step: int = 0
    battery_level: int = None
    color_id: int = NO_COLOR_ID
    sound_id: int = NO_SOUND_ID
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    brightness: int = 0
    charging_status: int = None  # Expected values: 0= Not Charging, 3= Charging, plugged in, 5= Charging, on base

    def _update_local_state(self, state):
        _LOGGER.debug(f"update local state: {self.device_name}, {state}")
        if safely_get_json_value(state, "deviceInfo.f") is not None:
            self.firmware_version = safely_get_json_value(state, "deviceInfo.f")
        if safely_get_json_value(state, "deviceInfo.b") is not None:
            self.battery_level = safely_get_json_value(state, "deviceInfo.b", int)
        if safely_get_json_value(state, "deviceInfo.powerStatus") is not None:
            self.charging_status = safely_get_json_value(state, "deviceInfo.powerStatus", int)
        if safely_get_json_value(state, "current.playing") is not None:
            self.current_playing = safely_get_json_value(state, "current.playing")
        if safely_get_json_value(state, "current.srId") is not None:
            self.current_id = safely_get_json_value(state, "current.srId")
        if safely_get_json_value(state, "current.step") is not None:
            self.current_step = safely_get_json_value(state, "current.step")
        if safely_get_json_value(state, "connected") is not None:
            self.is_online = safely_get_json_value(state, "connected", bool)
        if safely_get_json_value(state, "current.sound.v") is not None:
            self.volume = convert_to_percentage(
                safely_get_json_value(state, "current.sound.v", int)
            )
        if safely_get_json_value(state, "current.sound.id", int) is not None:
            self.sound_id = safely_get_json_value(state, "current.sound.id", int)
            with contextlib.suppress(ValueError):
                self.audio_track = RestBabyAudioTrack(self.sound_id)
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

        _LOGGER.debug(f"new state:{self}")
        self.publish_updates()

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            "firmware_version": self.firmware_version,
            "is_online": self.is_online,
            "current_playing": self.current_playing,
            "current_id": self.current_id,
            "current_step": self.current_step,
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
        }

    def __str__(self):
        return f"{self.__repr__()}"

    @property
    def is_on(self):
        return self.is_light_on or self.is_playing

    @property
    def is_light_on(self):
        return self.color_id != NO_COLOR_ID and self.color_id != 0

    @property
    def is_playing(self):
        return self.sound_id != NO_SOUND_ID

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

    # favorite_name_id is expected to be a string of name-id since name alone isn't unique
    def set_favorite(self, favorite_name_id: str):
        _LOGGER.debug(f"Setting favorite: {favorite_name_id}")
        fav_id = int(favorite_name_id.rsplit("-", 1)[1])
        self._update({"current": {"srId": fav_id, "step": 1, "playing": "routine"}})

    def set_audio_track(self, audio_track: RestBabyAudioTrack, volume: int = None):
        _LOGGER.debug(f"Setting audio track: {audio_track}")
        if audio_track == RestBabyAudioTrack.NONE:
            self.turn_off()
            return

        sound_url_map = RestBabyAudioTrack.sound_url_map()
        # Update the map with any changes from the API (in case URLs have changed)
        sound_url_map.update({
            sound.get('id'): sound.get('wavUrl') for sound in self.sounds
            if sound.get('id') and sound.get('wavUrl')
        })
        _LOGGER.debug(f'Available Sounds: {sound_url_map}')
        
        # Use provided volume or current volume
        volume_to_use = volume if volume is not None else self.volume
        self._update({"current": {"playing": "remote", "step": 0, "sound": {
                "id": audio_track.value,
                "url": sound_url_map[audio_track.value],
                "mute": False,
                "until": "indefinite",
                "duration": 0,
                "v": convert_from_percentage(volume_to_use),
            }}})

    def set_sound(self, sound_or_id_or_title: SoundContent | SimpleSoundContent | str | int | None, duration: int = 0, until="indefinite"):
        """
        Set a sound by passing SoundContent item from self.sounds, id, or title.
        """
        if sound_or_id_or_title is None or sound_or_id_or_title == NO_SOUND_ID or sound_or_id_or_title == "none":
            self.turn_off()
            return

        if isinstance(sound_or_id_or_title, int):
            sound = self.sounds_by_id.get(sound_or_id_or_title)
        elif isinstance(sound_or_id_or_title, str):
            sound = self.sounds_by_name.get(sound_or_id_or_title)
        else:
            # Assume it's a SoundContent or SimpleSoundContent object
            sound = sound_or_id_or_title

        if not sound or not isinstance(sound, dict) or not sound.get('id') or (not sound.get('wavUrl') and not sound.get('mp3Url')):
            _LOGGER.error(f"Sound not found: {sound_or_id_or_title}")
            return

        _LOGGER.debug(f"Setting sound: {sound.get('title') or sound['id']}")
        self._update(
            {
                "current": {
                    "playing": "remote",
                    "step": 0,
                    "sound": {
                        "id": sound["id"],
                        "mute": False,
                        "url": sound.get("wavUrl") or sound.get("mp3Url"),
                        "duration": duration,
                        "until": until,
                        "v": convert_from_percentage(self.volume),
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
                    "step": 0,
                    "sound": {"mute": False, "url": sound_url, "v": convert_from_percentage(self.volume), "duration": 0, "until": "indefinite"},
                }
            }
        )

    def turn_off(self):
        _LOGGER.debug("Turning off sound")
        self._update({"current": {"srId": 0, "step": 0, "playing": "none"}})

    def turn_light_off(self):
        _LOGGER.debug("Turning light off")
        # if favorite is playing then light can be turned off without turning off sound
        if self.current_playing == "routine":
            self._update(
                {
                    "current": {
                        "color": {
                            "id": NO_COLOR_ID,
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
                            "id": NO_COLOR_ID,
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
        new_color_id = CUSTOM_COLOR_ID
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
        else:
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
