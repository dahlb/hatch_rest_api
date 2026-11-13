import asyncio
import json
import logging
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiohttp import ClientError

from .const import (
    RESTORE_COLOR_NAMES,
    RESTORE_SOUND_NAMES,
    RIOT_FLAGS_CLOCK_24_HOUR,
    RIOT_FLAGS_CLOCK_ON,
)
from .errors import AuthError, DeviceSyncError, RateError
from .hatch import RESTORE_ALARM_API_URLS
from .scheduled_routine import weekdays_to_days_of_week
from .shadow_client_subscriber import ShadowClientSubscriberMixin
from .util import convert_from_percentage, convert_to_percentage, safely_get_json_value

if TYPE_CHECKING:
    from .hatch import Hatch

_LOGGER = logging.getLogger(__name__)

RESTORE_PLAYING_NONE = "none"
RESTORE_PLAYING_ROUTINE = "routine"
RESTORE_PLAYING_REMOTE = "remote"

# restoreClock.turnOffMode. "always" is accepted and reported back but has no
# effect on this model; clear the clock flag to turn the display off instead.
RESTORE_CLOCK_MODE_ALWAYS_ON = "never"
RESTORE_CLOCK_MODE_OFF_AT_NIGHT = "custom"

RESTORE_DEFAULT_COLOR_ID = 229  # Warm White
RESTORE_DEFAULT_SOUND_ID = 10040  # Light Rain
RESTORE_DEFAULT_BRIGHTNESS = 50
RESTORE_DEFAULT_VOLUME = 25

# How long the device gets to confirm a new list of alarm ids.
ALARM_SYNC_TIMEOUT = 20.0
ALARM_SYNC_POLL_INTERVAL = 0.25
ALARM_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _percentage(value: Any) -> int:
    return convert_to_percentage(int(value))


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        raise TypeError(f"expected a list, got {type(value).__name__}")
    return [int(item) for item in value]


# How each reported shadow key maps onto an attribute:
# (attribute, dotted shadow path, converter)
RESTORE_STATE_FIELDS: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
    ("firmware_version", "deviceInfo.f", str),
    ("hardware_version", "deviceInfo.hwVersion", str),
    ("is_online", "connected", bool),
    ("rssi", "rssi", int),
    ("timezone", "timezone", str),
    ("current_playing", "content.playing", str),
    ("current_step", "content.step", int),
    ("routine_id", "content.routineId", int),
    ("paused", "content.paused", bool),
    ("alarm_id", "content.alarmId", int),
    ("alarm_ids", "content.alarmIds", _int_list),
    ("requested_alarm_ids", "content.requested.alarms.ids", _int_list),
    ("requested_alarms_status", "content.requested.alarms.status", str),
    ("sound_id", "sound.id", int),
    ("volume", "sound.v", _percentage),
    ("sound_enabled", "sound.enabled", bool),
    ("color_id", "color.id", int),
    ("brightness", "color.i", _percentage),
    ("color_enabled", "color.enabled", bool),
    ("default_sound_id", "deviceDefaults.soundId", int),
    ("default_volume", "deviceDefaults.v", _percentage),
    ("default_color_id", "deviceDefaults.colorId", int),
    ("default_brightness", "deviceDefaults.i", _percentage),
    ("clock_brightness", "restoreClock.i", _percentage),
    ("clock_turn_on_at", "restoreClock.turnOnAt", str),
    ("clock_turn_off_at", "restoreClock.turnOffAt", str),
    ("clock_flags", "restoreClock.flags", int),
    ("clock_turn_off_mode", "restoreClock.turnOffMode", str),
    ("alarms_disabled", "alarmsDisabled", bool),
    ("snooze_duration", "snoozeDuration", int),
    ("alarm_duration", "alarmDuration", int),
    ("alarm_ramp_duration", "alarmRampDuration", int),
)

# Playback mode the light and sound need: on its own, a light or sound write
# is stored but nothing happens until something is playing.
REMOTE_CONTENT = {"playing": RESTORE_PLAYING_REMOTE, "paused": False, "offset": 0, "step": 0}
STOPPED_CONTENT = {"playing": RESTORE_PLAYING_NONE, "paused": False, "offset": 0, "step": 0}


def _merge_shadow_state(previous: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Return ``previous`` with ``changes`` merged in, without mutating either.

    Shadow update notifications only carry the keys that changed, so the full
    picture has to be accumulated from the initial get plus every update.
    """
    merged = deepcopy(previous)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_shadow_state(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def restore_alarm_wake_time(alarm: dict[str, Any] | None) -> time | None:
    """The time of day an alarm goes off, from its "YYYY-MM-DD HH:MM:SS" time."""
    if not alarm:
        return None
    try:
        return datetime.strptime(str(alarm.get("time")), ALARM_TIME_FORMAT).time()
    except ValueError:
        return None


async def fetch_restore_alarms(
    api: "Hatch",
    auth_token: str,
    mac: str,
    preferred_url: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch a Restore's alarms from whichever alarm API host answers.

    Returns the alarms and the base URL that served them, so writes can use the
    same host.
    """
    urls = [preferred_url] if preferred_url else []
    urls += [url for url in RESTORE_ALARM_API_URLS if url not in urls]
    last_error: Exception | None = None
    for url in urls:
        try:
            alarms = await api.restore_alarms(auth_token=auth_token, mac=mac, base_url=url)
        except (RateError, AuthError):
            raise
        except (ClientError, KeyError, TypeError, ValueError) as error:
            _LOGGER.debug(f"restore alarms not served by {url}: {error!r}")
            last_error = error
            continue
        if not isinstance(alarms, list):
            last_error = ClientError(f"unexpected alarm payload from {url}")
            continue
        return alarms, url
    raise last_error or ClientError("no restore alarm API host configured")


class Restore(ShadowClientSubscriberMixin):
    """The original Hatch Restore, Hatch product code ``restore``.

    Hatch sold two first generation Restores. The later one reports itself as
    ``restoreIot`` and is handled by RestoreIot. This one is older and lays its
    shadow out differently: what is playing lives under ``content``, the sound
    and light sit at the top level as ``sound`` and ``color``, and the clock is
    ``restoreClock``. RestoreIot keeps all of that under ``current`` and
    ``clock`` instead, so the two cannot share a parser.

    Every write below was checked on a real device; docs/restore.md lists the
    checks. Alarms are not in the shadow: they live in Hatch's alarm API, and
    the device only holds the ids of the alarms it should load.
    """

    firmware_version: str | None = None
    hardware_version: str | None = None
    is_online: bool = False
    rssi: int | None = None
    timezone: str | None = None

    current_playing: str = RESTORE_PLAYING_NONE
    current_step: int = 0
    routine_id: int | None = None
    paused: bool = False
    alarm_id: int | None = None
    requested_alarms_status: str | None = None

    sound_id: int | None = None
    volume: int = 0
    sound_enabled: bool | None = None

    color_id: int | None = None
    brightness: int = 0
    color_enabled: bool | None = None

    default_sound_id: int | None = None
    default_volume: int | None = None
    default_color_id: int | None = None
    default_brightness: int | None = None

    clock_brightness: int | None = None
    clock_turn_on_at: str | None = None
    clock_turn_off_at: str | None = None
    clock_flags: int | None = None
    clock_turn_off_mode: str | None = None

    alarms_disabled: bool | None = None
    snooze_duration: int | None = None
    alarm_duration: int | None = None
    alarm_ramp_duration: int | None = None

    def __init__(self, *args, routines: list | None = None, **kwargs):
        # Set before the mixin subscribes: the shadow callbacks fire on an
        # awscrt thread and may arrive as soon as refresh() has been sent.
        self.shadow_state: dict[str, Any] = {}
        self.alarm_ids: list[int] = []
        self.requested_alarm_ids: list[int] = []
        # Fetched on a best effort basis; None means the fetch failed or was
        # skipped, [] means Hatch returned none.
        self.routines = routines
        # The device zeroes sound.v whenever playback stops, so the volume to
        # start the next sound at has to be remembered here.
        self.last_volume = RESTORE_DEFAULT_VOLUME
        # Alarms, from Hatch's alarm API. Deliberately not named "alarms":
        # that attribute belongs to the scheduled-routine alarm models.
        self.restore_alarms: list[dict[str, Any]] = []
        self.restore_alarms_loaded = False
        self.alarm_capable = False
        self.alarm_api_url: str | None = None
        self._alarm_api: Hatch | None = None
        self._alarm_auth_token: str | None = None
        super().__init__(*args, **kwargs)

    # ---- shadow state -----------------------------------------------------

    def _update_local_state(self, state):
        # Probe logging: which keys this model reports is not documented
        # anywhere, so log every report verbatim, in a form that can be copied
        # out of the log and parsed.
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                f"restore raw shadow state for {self.device_name}: "
                f"{json.dumps(state, default=str, sort_keys=True)}"
            )
        self.shadow_state = _merge_shadow_state(self.shadow_state, state)

        for attribute, path, convert in RESTORE_STATE_FIELDS:
            value = safely_get_json_value(state, path)
            if value is None:
                continue
            try:
                setattr(self, attribute, convert(value))
            except (TypeError, ValueError):
                # One unexpected value should not cost the rest of the report.
                _LOGGER.debug(
                    f"{self.device_name}: ignoring {path}={value!r}, "
                    f"not convertible with {convert.__name__}"
                )
        if self.volume > 0:
            self.last_volume = self.volume

        _LOGGER.debug(f"new state:{self}")
        self.publish_updates()

    def __repr__(self):
        return {
            "device_name": self.device_name,
            "thing_name": self.thing_name,
            "mac": self.mac,
            **{
                attribute: getattr(self, attribute)
                for attribute, _, _ in RESTORE_STATE_FIELDS
            },
            "is_on": self.is_on,
            "is_playing": self.is_playing,
            "is_light_on": self.is_light_on,
            "is_sound_on": self.is_sound_on,
            "color_name": self.color_name,
            "sound_name": self.sound_name,
            "last_volume": self.last_volume,
            "document_version": self.document_version,
            "routines": self.routines,
            "restore_alarms": self.restore_alarms,
            "restore_alarms_loaded": self.restore_alarms_loaded,
            "alarm_api_url": self.alarm_api_url,
            "shadow_state": self.shadow_state,
        }

    def __str__(self):
        return f"{self.__repr__()}"

    # ---- read-only views ----------------------------------------------------

    @property
    def is_playing(self) -> bool:
        """Whether a routine, or anything started from the app, is running."""
        return self.current_playing != RESTORE_PLAYING_NONE

    @property
    def is_on(self) -> bool:
        return self.is_playing

    @property
    def is_light_on(self) -> bool:
        return self.is_playing and bool(self.color_enabled)

    @property
    def is_sound_on(self) -> bool:
        return self.is_playing and bool(self.sound_enabled)

    @property
    def color_name(self) -> str | None:
        return RESTORE_COLOR_NAMES.get(self.color_id)

    @property
    def sound_name(self) -> str | None:
        return RESTORE_SOUND_NAMES.get(self.sound_id)

    @property
    def is_clock_on(self) -> bool | None:
        if self.clock_flags is None:
            return None
        return bool(self.clock_flags & RIOT_FLAGS_CLOCK_ON)

    @property
    def is_clock_24h(self) -> bool | None:
        if self.clock_flags is None:
            return None
        return bool(self.clock_flags & RIOT_FLAGS_CLOCK_24_HOUR)

    @property
    def routine(self) -> dict[str, Any] | None:
        """The routine the device runs: the one it reports, else the first."""
        routines = [
            routine
            for routine in self.routines or []
            if isinstance(routine, dict) and routine.get("type", "routine") == "routine"
        ]
        return next(
            (routine for routine in routines if routine.get("id") == self.routine_id),
            routines[0] if routines else None,
        )

    @property
    def routine_steps(self) -> list[str]:
        """Names of the routine's steps; step n of the device is entry n - 1."""
        routine = self.routine
        if routine is None:
            return []
        return [
            str(step.get("name") or f"Step {number}").strip()
            for number, step in enumerate(routine.get("steps") or [], start=1)
            if isinstance(step, dict)
        ]

    # ---- routine ------------------------------------------------------------

    def turn_on_routine(self, step: int = 1):
        """Start the bedtime routine at ``step`` (1 is its first step)."""
        if step < 1:
            raise ValueError(f"routine steps start at 1, got {step}")
        _LOGGER.debug(f"Turning on routine step {step} for {self.device_name}")
        self._set_content(RESTORE_PLAYING_ROUTINE, step)

    def turn_off(self):
        _LOGGER.debug(f"Turning off {self.device_name}")
        self._set_content(RESTORE_PLAYING_NONE, 0)

    def _set_content(self, playing: str, step: int):
        # The full content block, as homebridge-hatch-baby-rest sends it; a
        # partial one is not known to work on this model.
        self._update(
            {
                "content": {
                    "playing": playing,
                    "paused": False,
                    "offset": 0,
                    "step": step,
                }
            }
        )

    # ---- light --------------------------------------------------------------

    def turn_light_on(self, color_id: int | None = None, brightness: int | None = None):
        """Turn the light on, starting remote playback if nothing plays."""
        color = {
            "enabled": True,
            "id": color_id or self._light_color_id(),
            "i": convert_from_percentage(
                brightness if brightness is not None else self._light_brightness()
            ),
        }
        desired: dict[str, Any] = {"color": color}
        if not self.is_playing:
            desired["content"] = dict(REMOTE_CONTENT)
            desired["sound"] = {"enabled": False}
        _LOGGER.debug(f"Turning light on for {self.device_name}: {desired}")
        self._update(desired)

    def turn_light_off(self):
        """Turn the light off; with no sound playing either, stop playback."""
        if self.is_sound_on:
            self._update({"color": {"enabled": False}})
        else:
            self.turn_off()

    def set_light_brightness(self, brightness: int):
        if self.is_light_on:
            self._update({"color": {"i": convert_from_percentage(brightness)}})
        else:
            self.turn_light_on(brightness=brightness)

    def set_light_color(self, color_id: int):
        if self.is_light_on:
            self._update({"color": {"id": color_id}})
        else:
            self.turn_light_on(color_id=color_id)

    def _light_color_id(self) -> int:
        for candidate in (self.color_id, self.default_color_id):
            if candidate in RESTORE_COLOR_NAMES:
                return candidate
        return RESTORE_DEFAULT_COLOR_ID

    def _light_brightness(self) -> int:
        for candidate in (self.brightness, self.default_brightness):
            if candidate:
                return candidate
        return RESTORE_DEFAULT_BRIGHTNESS

    # ---- sound --------------------------------------------------------------

    def play_sound(self, sound_id: int | None = None, volume: int | None = None):
        """Play a sound, starting remote playback if nothing plays."""
        volume = volume if volume is not None else self.last_volume
        desired: dict[str, Any] = {
            "sound": {
                "enabled": True,
                "id": sound_id or self._sound_id(),
                "v": convert_from_percentage(volume),
            }
        }
        if not self.is_playing:
            desired["content"] = dict(REMOTE_CONTENT)
            desired["color"] = {"enabled": False}
        if volume > 0:
            self.last_volume = volume
        _LOGGER.debug(f"Playing sound on {self.device_name}: {desired}")
        self._update(desired)

    def stop_sound(self):
        """Stop the sound; with the light off too, stop playback."""
        if self.is_light_on:
            self._update({"sound": {"enabled": False}})
        else:
            self.turn_off()

    def set_volume(self, volume: int):
        """Set the volume; while nothing plays, only remember it for next time."""
        if volume > 0:
            self.last_volume = volume
        if self.is_sound_on:
            self._update({"sound": {"v": convert_from_percentage(volume)}})

    def set_sound(self, sound_id: int):
        if self.is_sound_on:
            self._update({"sound": {"id": sound_id}})
        else:
            self.play_sound(sound_id=sound_id)

    def _sound_id(self) -> int:
        for candidate in (self.sound_id, self.default_sound_id):
            if candidate in RESTORE_SOUND_NAMES:
                return candidate
        return RESTORE_DEFAULT_SOUND_ID

    # ---- clock --------------------------------------------------------------

    def set_clock(self, on: bool | None = None, brightness: int | None = None):
        """Turn the clock display on or off and/or set its brightness."""
        clock: dict[str, Any] = {}
        if on is not None:
            flags = self.clock_flags or 0
            clock["flags"] = flags | RIOT_FLAGS_CLOCK_ON if on else flags & ~RIOT_FLAGS_CLOCK_ON
        if brightness is not None:
            clock["i"] = convert_from_percentage(brightness)
        if clock:
            self._update({"restoreClock": clock})

    def set_clock_24h(self, enabled: bool):
        flags = self.clock_flags or 0
        flags = flags | RIOT_FLAGS_CLOCK_24_HOUR if enabled else flags & ~RIOT_FLAGS_CLOCK_24_HOUR
        self._update({"restoreClock": {"flags": flags}})

    def set_clock_off_at_night(self, off_at_night: bool):
        """Turn the night schedule (off between turnOffAt and turnOnAt) on or off."""
        mode = RESTORE_CLOCK_MODE_OFF_AT_NIGHT if off_at_night else RESTORE_CLOCK_MODE_ALWAYS_ON
        self._update({"restoreClock": {"turnOffMode": mode}})

    def set_clock_schedule(self, turn_on_at: time | None = None, turn_off_at: time | None = None):
        clock = {}
        if turn_on_at is not None:
            clock["turnOnAt"] = turn_on_at.strftime("%H:%M:%S")
        if turn_off_at is not None:
            clock["turnOffAt"] = turn_off_at.strftime("%H:%M:%S")
        if clock:
            self._update({"restoreClock": clock})

    # ---- all alarms -----------------------------------------------------------

    def set_alarms_disabled(self, disabled: bool):
        """Silence every alarm (the crossed-bell button) or allow them again."""
        self._update({"alarmsDisabled": disabled})

    # ---- individual alarms (Hatch's alarm API) --------------------------------

    def configure_alarm_api(
        self,
        api: "Hatch",
        auth_token: str,
        alarms: list[dict[str, Any]] | None = None,
        api_url: str | None = None,
    ) -> None:
        self._alarm_api = api
        self._alarm_auth_token = auth_token
        self.alarm_api_url = api_url
        self.alarm_capable = True
        if alarms is not None:
            self._set_restore_alarms(alarms)

    def restore_alarm_by_id(self, alarm_id: int | str) -> dict[str, Any] | None:
        return next(
            (alarm for alarm in self.restore_alarms if str(alarm.get("id")) == str(alarm_id)),
            None,
        )

    async def refresh_alarms(self) -> list[dict[str, Any]]:
        api, auth_token = self._configured_alarm_api()
        alarms, self.alarm_api_url = await fetch_restore_alarms(
            api, auth_token, self.mac, preferred_url=self.alarm_api_url
        )
        self._set_restore_alarms(alarms)
        self.publish_updates()
        return self.restore_alarms

    async def set_restore_alarm_enabled(self, alarm_id: int | str, enabled: bool) -> int:
        """Turn one alarm on or off, the way the Hatch app does.

        The device is told which alarm ids to keep loaded first, and only once
        it has confirmed is the change saved to Hatch. Returns the alarm's id,
        which this does not change.
        """
        alarms = await self._alarms_for_edit()
        target = self._alarm_in(alarms, alarm_id)
        updated = [
            {**alarm, "enabled": enabled} if alarm is target else alarm
            for alarm in alarms
        ]
        await self._sync_device_alarm_ids(self._enabled_alarm_ids(updated))
        await self._save_alarms([self._alarm_request(alarm) for alarm in updated])
        return int(target["id"])

    async def set_restore_alarm_schedule(
        self,
        alarm_id: int | str,
        wake_time: time | None = None,
        weekdays: Iterable[str] | None = None,
    ) -> int:
        """Change an alarm's time and/or repeat days, the way the Hatch app does.

        The device only loads an alarm by id, so an edit is a new alarm: Hatch
        creates an edited copy, the device is moved over to the copy's id, and
        the original is then deleted. Returns the copy's id, which replaces
        ``alarm_id`` from here on. An empty ``weekdays`` makes a one-time alarm.
        """
        alarms = await self._alarms_for_edit()
        original = self._alarm_in(alarms, alarm_id)
        edited = deepcopy(original)
        if weekdays is not None:
            edited["daysOfWeek"] = weekdays_to_days_of_week(weekdays)
        wake_time = wake_time or restore_alarm_wake_time(original)
        if wake_time is None:
            raise ValueError(f"alarm {alarm_id} has no time to keep")
        edited["time"], edited["absoluteTime"] = self._alarm_moment(
            original, wake_time, int(edited.get("daysOfWeek") or 0)
        )

        api, auth_token = self._configured_alarm_api()
        created = await api.create_restore_alarm(
            auth_token=auth_token,
            alarm=self._alarm_request(edited, active=True),
            base_url=self._alarm_url(),
        )
        copy = self._created_copy(created, alarms, edited)
        if copy is None:
            raise ClientError(f"Hatch did not return the edited copy of alarm {alarm_id}")
        # Hatch returns the copy inactive; it becomes the active one below.
        copy = {**copy, "enabled": original.get("enabled", True), "active": True}

        remaining = [alarm for alarm in alarms if alarm is not original]
        await self._sync_device_alarm_ids(self._enabled_alarm_ids([*remaining, copy]))
        await self._save_alarms(
            sorted(
                [
                    *(self._alarm_request(alarm) for alarm in remaining),
                    self._alarm_request(original, active=False),
                    self._alarm_request(copy, active=True),
                ],
                key=lambda alarm: int(alarm["id"]),
            )
        )
        return int(copy["id"])

    async def set_alarm_weekdays(self, alarm_id: int | str, weekdays: Iterable[str]) -> int:
        """Same signature as the scheduled-routine alarm models' method."""
        return await self.set_restore_alarm_schedule(alarm_id, weekdays=list(weekdays))

    @staticmethod
    def _created_copy(
        created: list[dict[str, Any]] | None,
        alarms: list[dict[str, Any]],
        edited: dict[str, Any],
    ) -> dict[str, Any] | None:
        """The alarm a create call made, out of the list Hatch answers with.

        The answer can also hold alarms deleted by earlier edits, which are
        new to ``alarms`` too, so prefer the one matching what was sent, and
        the newest of those.
        """
        known_ids = {str(alarm.get("id")) for alarm in alarms}
        candidates = [
            alarm
            for alarm in created or []
            if isinstance(alarm, dict)
            and alarm.get("id") is not None
            and str(alarm.get("id")) not in known_ids
        ]
        matching = [
            alarm
            for alarm in candidates
            if alarm.get("time") == edited.get("time")
            and alarm.get("daysOfWeek") == edited.get("daysOfWeek")
        ]
        pool = matching or candidates
        return max(pool, key=lambda alarm: int(alarm["id"])) if pool else None

    def _configured_alarm_api(self) -> "tuple[Hatch, str]":
        if self._alarm_api is None or self._alarm_auth_token is None:
            raise RuntimeError(f"Alarm API is not configured for {self.device_name}")
        return self._alarm_api, self._alarm_auth_token

    def _alarm_url(self) -> str:
        return self.alarm_api_url or RESTORE_ALARM_API_URLS[0]

    def _set_restore_alarms(self, alarms: list[dict[str, Any]]) -> None:
        self.restore_alarms = sorted(
            (
                deepcopy(alarm)
                for alarm in alarms or []
                if isinstance(alarm, dict) and alarm.get("active", True)
            ),
            key=lambda alarm: int(alarm.get("id") or 0),
        )
        self.restore_alarms_loaded = True

    async def _alarms_for_edit(self) -> list[dict[str, Any]]:
        # Always start from Hatch's current list: the update below replaces the
        # whole list, so a stale copy could undo changes made in the app.
        return await self.refresh_alarms()

    def _alarm_in(self, alarms: list[dict[str, Any]], alarm_id: int | str) -> dict[str, Any]:
        alarm = next((alarm for alarm in alarms if str(alarm.get("id")) == str(alarm_id)), None)
        if alarm is None:
            raise ValueError(f"Alarm {alarm_id} not found for {self.device_name}")
        return alarm

    @staticmethod
    def _enabled_alarm_ids(alarms: list[dict[str, Any]]) -> list[int]:
        return sorted(
            int(alarm["id"])
            for alarm in alarms
            if alarm.get("enabled") and alarm.get("active", True) and alarm.get("id") is not None
        )

    def _alarm_request(self, alarm: dict[str, Any], **overrides: Any) -> dict[str, Any]:
        """An alarm as the app sends it: the fetched alarm, minus derived fields."""
        request = {key: deepcopy(value) for key, value in alarm.items() if key != "isExpiredOneOff"}
        request.setdefault("macAddress", self.mac)
        sound = request.get("sound")
        if isinstance(sound, dict):
            sound.setdefault("duration", 0)
            sound.setdefault("until", "duration")
        color = request.get("color")
        if isinstance(color, dict):
            color.setdefault("until", "duration")
        request.update(overrides)
        return request

    def _alarm_moment(
        self, alarm: dict[str, Any], wake_time: time, days_of_week: int
    ) -> tuple[str, int]:
        """The alarm's "time" string and absoluteTime (ms) for a new time of day.

        A repeating alarm keeps its original date, as the app does. A one-time
        alarm goes off at the next occurrence of the time.
        """
        zone = self._zone()
        now = datetime.now(zone)
        wake_time = wake_time.replace(microsecond=0, tzinfo=None)
        try:
            day = datetime.strptime(str(alarm.get("time")), ALARM_TIME_FORMAT).date()
        except ValueError:
            day = now.date()
        if not days_of_week:
            day = now.date()
            if datetime.combine(day, wake_time, tzinfo=zone) <= now:
                day += timedelta(days=1)
        moment = datetime.combine(day, wake_time, tzinfo=zone)
        return moment.strftime(ALARM_TIME_FORMAT), int(moment.timestamp() * 1000)

    def _zone(self) -> tzinfo:
        try:
            return ZoneInfo(self.timezone) if self.timezone else UTC
        except (ZoneInfoNotFoundError, ValueError):
            return UTC

    async def _save_alarms(self, alarms: list[dict[str, Any]]) -> None:
        api, auth_token = self._configured_alarm_api()
        saved = await api.update_restore_alarms(
            auth_token=auth_token, alarms=alarms, base_url=self._alarm_url()
        )
        self._set_restore_alarms(saved)
        self.publish_updates()

    async def _sync_device_alarm_ids(self, ids: list[int]) -> None:
        """Tell the device which alarms to load, and wait until it has."""
        previous = list(self.requested_alarm_ids)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._update, self._alarm_ids_desired(ids))
        if await self._wait_for_alarm_ids(ids):
            return
        _LOGGER.warning(
            f"{self.device_name} did not confirm alarm ids {ids}; restoring {previous}"
        )
        try:
            await loop.run_in_executor(None, self._update, self._alarm_ids_desired(previous))
        except Exception as error:
            _LOGGER.warning(f"restoring alarm ids on {self.device_name} failed: {error!r}")
        raise DeviceSyncError(
            f"{self.device_name} did not confirm the new alarm list; nothing was saved"
        )

    @staticmethod
    def _alarm_ids_desired(ids: list[int]) -> dict[str, Any]:
        return {"content": {"requested": {"alarms": {"ids": list(ids)}}}}

    async def _wait_for_alarm_ids(self, ids: list[int]) -> bool:
        wanted = sorted(ids)
        deadline = asyncio.get_running_loop().time() + ALARM_SYNC_TIMEOUT
        while True:
            if sorted(self.requested_alarm_ids) == wanted and self.requested_alarms_status == "success":
                return True
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(ALARM_SYNC_POLL_INTERVAL)
