from datetime import datetime, time, timedelta
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from .hatch import Hatch

ALARM_ROUTINE_TYPE = "alarm"
# Android models scheduled-routine alarms this way for Restore, Restore 2, and Restore 3.
SCHEDULED_ROUTINE_ALARM_PRODUCTS: frozenset[str] = frozenset(
    {"restoreIot", "restoreV4", "restoreV5"}
)
WEEKDAY_BITS: dict[str, int] = {
    "monday": 2,
    "tuesday": 4,
    "wednesday": 8,
    "thursday": 16,
    "friday": 32,
    "saturday": 64,
    "sunday": 1,
}
WEEKDAY_SHORT_NAMES: dict[str, str] = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}
WEEKDAYS_MASK = sum(WEEKDAY_BITS.values())
WEEKDAYS_ONLY_MASK = (
    WEEKDAY_BITS["monday"]
    | WEEKDAY_BITS["tuesday"]
    | WEEKDAY_BITS["wednesday"]
    | WEEKDAY_BITS["thursday"]
    | WEEKDAY_BITS["friday"]
)
WEEKENDS_MASK = WEEKDAY_BITS["sunday"] | WEEKDAY_BITS["saturday"]


class ScheduledRoutineAlarm(TypedDict, total=False):
    id: int
    name: str
    active: bool
    enabled: bool
    type: str
    macAddress: str
    startTime: str | None
    endTime: str | None
    daysOfWeek: int | None
    displayOrder: int | None
    steps: NotRequired[list[dict[str, Any]]]


def alarm_update_payload(
    alarm: ScheduledRoutineAlarm,
    enabled: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    if "id" not in alarm:
        raise ValueError("Cannot update alarm without an id")

    start_time = alarm.get("startTime")
    end_time = alarm.get("endTime")
    if enabled and _is_one_time_alarm(alarm):
        start_time, end_time = _next_one_time_alarm_times(
            alarm,
            now=now,
        )

    return {
        "id": alarm["id"],
        "name": alarm.get("name"),
        "active": alarm.get("active"),
        "enabled": enabled,
        "displayOrder": alarm.get("displayOrder"),
        "startTime": start_time,
        "endTime": end_time,
    }


def alarm_wake_time_update_payload(
    alarm: ScheduledRoutineAlarm,
    wake_time: time,
    now: datetime | None = None,
) -> dict[str, Any]:
    if "id" not in alarm:
        raise ValueError("Cannot update alarm without an id")

    start_time = alarm.get("startTime")
    end_time = alarm.get("endTime")
    parsed_start_time = _parse_required_local_datetime(start_time, "startTime")
    wake_time = wake_time.replace(tzinfo=None)

    parsed_end_time = _parse_local_datetime(end_time)
    if parsed_end_time is None and end_time is not None:
        raise ValueError("Cannot update alarm wake time without a valid endTime")

    sunrise_lead = _alarm_sunrise_lead(alarm, parsed_start_time, parsed_end_time)
    if _is_one_time_alarm(alarm):
        updated_end_time = _next_datetime_for_time(wake_time, now=now)
    elif parsed_end_time is not None:
        updated_end_time = datetime.combine(parsed_end_time.date(), wake_time)
    else:
        existing_wake_time = parsed_start_time + sunrise_lead
        updated_end_time = datetime.combine(existing_wake_time.date(), wake_time)
    updated_start_time = updated_end_time - sunrise_lead

    return {
        "id": alarm["id"],
        "name": alarm.get("name"),
        "active": alarm.get("active"),
        "enabled": alarm.get("enabled"),
        "displayOrder": alarm.get("displayOrder"),
        "startTime": _format_like_original(start_time, updated_start_time),
        "endTime": (
            _format_like_original(end_time, updated_end_time)
            if end_time is not None
            else None
        ),
    }


def alarm_weekdays_update_payload(
    alarm: ScheduledRoutineAlarm,
    weekdays: Iterable[str],
) -> dict[str, Any]:
    if "id" not in alarm:
        raise ValueError("Cannot update alarm without an id")

    return {
        "id": alarm["id"],
        "name": alarm.get("name"),
        "active": alarm.get("active"),
        "enabled": alarm.get("enabled"),
        "displayOrder": alarm.get("displayOrder"),
        "startTime": alarm.get("startTime"),
        "endTime": alarm.get("endTime"),
        "daysOfWeek": weekdays_to_days_of_week(weekdays),
    }


def weekdays_to_days_of_week(weekdays: Iterable[str]) -> int:
    days_of_week = 0
    if isinstance(weekdays, str):
        weekdays = [weekdays]
    for weekday in weekdays:
        normalized_weekday = str(weekday).strip().lower()
        try:
            days_of_week |= WEEKDAY_BITS[normalized_weekday]
        except KeyError as error:
            raise ValueError(f"Unsupported alarm weekday: {weekday}") from error
    return days_of_week


def days_of_week_to_weekdays(days_of_week: int | None) -> list[str]:
    normalized_days_of_week = _normalize_days_of_week(days_of_week)
    return [
        weekday
        for weekday, bit in WEEKDAY_BITS.items()
        if normalized_days_of_week & bit
    ]


def days_of_week_label(days_of_week: int | None) -> str:
    normalized_days_of_week = _normalize_days_of_week(days_of_week)
    if normalized_days_of_week == 0:
        return "Once"
    if normalized_days_of_week == WEEKDAYS_ONLY_MASK:
        return "Weekdays"
    if normalized_days_of_week == WEEKENDS_MASK:
        return "Weekends"
    if normalized_days_of_week == WEEKDAYS_MASK:
        return "Every day"
    return ", ".join(
        WEEKDAY_SHORT_NAMES[weekday]
        for weekday in days_of_week_to_weekdays(normalized_days_of_week)
    )


def alarm_routines(routines: list[ScheduledRoutineAlarm]) -> list[ScheduledRoutineAlarm]:
    return [
        routine
        for routine in routines
        if routine.get("type") == ALARM_ROUTINE_TYPE
    ]


def _is_one_time_alarm(alarm: ScheduledRoutineAlarm) -> bool:
    days_of_week = alarm.get("daysOfWeek")
    return days_of_week is None or days_of_week == 0


def _normalize_days_of_week(days_of_week: int | None) -> int:
    if days_of_week is None:
        return 0
    if isinstance(days_of_week, bool) or not isinstance(days_of_week, int):
        raise TypeError(f"Unsupported alarm daysOfWeek value: {days_of_week}")
    if days_of_week < 0 or days_of_week > WEEKDAYS_MASK:
        raise ValueError(f"Unsupported alarm daysOfWeek value: {days_of_week}")
    return days_of_week


def _next_one_time_alarm_times(
    alarm: ScheduledRoutineAlarm,
    now: datetime | None = None,
) -> tuple[str | None, str | None]:
    start_time = alarm.get("startTime")
    end_time = alarm.get("endTime")
    parsed_start_time = _parse_local_datetime(start_time)
    parsed_end_time = _parse_local_datetime(end_time)
    if parsed_end_time is not None:
        next_end_time = _next_datetime_for_time(parsed_end_time.time(), now=now)
        if parsed_start_time is None:
            return start_time, _format_like_original(end_time, next_end_time)
        next_start_time = next_end_time - (parsed_end_time - parsed_start_time)
        return (
            _format_like_original(start_time, next_start_time),
            _format_like_original(end_time, next_end_time),
        )

    if parsed_start_time is None:
        return start_time, end_time

    if end_time is None:
        sunrise_duration = _alarm_sunrise_duration_seconds(alarm)
        if sunrise_duration is not None:
            sunrise_lead = timedelta(seconds=sunrise_duration)
            current_wake_time = parsed_start_time + sunrise_lead
            next_end_time = _next_datetime_for_time(
                current_wake_time.time(),
                now=now,
            )
            next_start_time = next_end_time - sunrise_lead
            return _format_like_original(start_time, next_start_time), end_time

    next_start_time = _next_datetime_for_time(parsed_start_time.time(), now=now)
    return _format_like_original(start_time, next_start_time), end_time


def _alarm_sunrise_lead(
    alarm: ScheduledRoutineAlarm,
    parsed_start_time: datetime,
    parsed_end_time: datetime | None,
) -> timedelta:
    if parsed_end_time is not None:
        return parsed_end_time - parsed_start_time

    sunrise_duration = _alarm_sunrise_duration_seconds(alarm)
    if sunrise_duration is None:
        raise ValueError(
            "Cannot update alarm wake time without a valid sunrise duration"
        )
    return timedelta(seconds=sunrise_duration)


def _alarm_sunrise_duration_seconds(alarm: ScheduledRoutineAlarm) -> int | None:
    steps = alarm.get("steps") or []
    sunrise_step_duration = next(
        (
            duration
            for step in steps
            if isinstance(step, dict)
            and str(step.get("name", "")).lower() == "sunrise"
            and (duration := _step_color_duration_seconds(step)) is not None
        ),
        None,
    )
    if sunrise_step_duration is not None:
        return sunrise_step_duration

    return next(
        (
            duration
            for step in steps
            if isinstance(step, dict)
            and (duration := _step_color_duration_seconds(step)) is not None
        ),
        None,
    )


def _step_color_duration_seconds(step: dict[str, Any]) -> int | None:
    if step.get("enabled") is False:
        return None

    color = step.get("color")
    if not isinstance(color, dict) or color.get("ignore") is True:
        return None

    duration = color.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        return None

    return duration


def _next_datetime_for_time(
    value: time,
    now: datetime | None = None,
) -> datetime:
    value = value.replace(tzinfo=None)

    if now is None:
        now = datetime.now()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)

    next_time = datetime.combine(now.date(), value)
    if next_time <= now:
        next_time = next_time + timedelta(days=1)

    return next_time


def _parse_local_datetime(value: str) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _parse_required_local_datetime(value: str | None, field: str) -> datetime:
    parsed = _parse_local_datetime(value)
    if parsed is None:
        raise ValueError(f"Cannot update alarm wake time without a valid {field}")
    return parsed


def _format_like_original(original: str | None, value: datetime) -> str:
    if not isinstance(original, str):
        return value.isoformat(timespec="seconds")
    if "." in original:
        formatted = value.isoformat()
    elif len(original.split("T", 1)[-1].split(":")) <= 2:
        formatted = value.isoformat(timespec="minutes")
    else:
        formatted = value.isoformat(timespec="seconds")

    if "T" not in original and " " in original:
        return formatted.replace("T", " ", 1)
    return formatted


class ScheduledRoutineAlarmMixin:
    alarms: list[ScheduledRoutineAlarm]
    alarm_capable: bool = False
    alarms_loaded: bool = False
    _alarm_api: "Hatch | None" = None
    _alarm_auth_token: str | None = None

    def configure_alarm_api(
        self,
        api: "Hatch",
        auth_token: str,
        alarms: list[ScheduledRoutineAlarm] | None = None,
    ) -> None:
        self._alarm_api = api
        self._alarm_auth_token = auth_token
        self.alarm_capable = True
        self.alarms_loaded = alarms is not None
        self.alarms = list(alarms or [])

    def alarm_by_id(self, alarm_id: int | str) -> ScheduledRoutineAlarm | None:
        alarm_id_string = str(alarm_id)
        return next(
            (
                alarm
                for alarm in getattr(self, "alarms", [])
                if str(alarm.get("id")) == alarm_id_string
            ),
            None,
        )

    async def refresh_alarms(self) -> list[ScheduledRoutineAlarm]:
        api, auth_token = self._configured_alarm_api()
        self.alarms = await api.scheduled_routines(
            auth_token=auth_token,
            mac=self.mac,
            types=[ALARM_ROUTINE_TYPE],
        )
        self.alarms_loaded = True
        self.publish_updates()
        return self.alarms

    async def set_alarm_enabled(self, alarm_id: int | str, enabled: bool) -> None:
        alarm = self.alarm_by_id(alarm_id)
        if alarm is None:
            await self.refresh_alarms()
            alarm = self.alarm_by_id(alarm_id)
        if alarm is None:
            raise ValueError(f"Alarm {alarm_id} not found for {self.device_name}")

        api, auth_token = self._configured_alarm_api()
        updated_alarms = await api.update_scheduled_routine_alarm_enabled(
            auth_token=auth_token,
            mac=self.mac,
            alarm=alarm,
            enabled=enabled,
        )
        if updated_alarms:
            self._replace_alarms(updated_alarms)
        else:
            self._replace_alarms(
                [{**alarm, **alarm_update_payload(alarm, enabled)}]
            )
        self.publish_updates()

    async def set_alarm_wake_time(self, alarm_id: int | str, wake_time: time) -> None:
        alarm = self.alarm_by_id(alarm_id)
        if alarm is None:
            await self.refresh_alarms()
            alarm = self.alarm_by_id(alarm_id)
        if alarm is None:
            raise ValueError(f"Alarm {alarm_id} not found for {self.device_name}")

        api, auth_token = self._configured_alarm_api()
        updated_alarms = await api.update_scheduled_routine_alarm_wake_time(
            auth_token=auth_token,
            mac=self.mac,
            alarm=alarm,
            wake_time=wake_time,
        )
        if updated_alarms:
            self._replace_alarms(updated_alarms)
        else:
            self._replace_alarms(
                [{**alarm, **alarm_wake_time_update_payload(alarm, wake_time)}]
            )
        self.publish_updates()

    async def set_alarm_weekdays(
        self,
        alarm_id: int | str,
        weekdays: Iterable[str],
    ) -> None:
        alarm = self.alarm_by_id(alarm_id)
        if alarm is None:
            await self.refresh_alarms()
            alarm = self.alarm_by_id(alarm_id)
        if alarm is None:
            raise ValueError(f"Alarm {alarm_id} not found for {self.device_name}")

        # Materialize once so the API call and the fallback payload see the same values
        # even if the caller passed a single-pass generator.
        weekdays_list = list(weekdays)
        api, auth_token = self._configured_alarm_api()
        updated_alarms = await api.update_scheduled_routine_alarm_weekdays(
            auth_token=auth_token,
            mac=self.mac,
            alarm=alarm,
            weekdays=weekdays_list,
        )
        if updated_alarms:
            self._replace_alarms(updated_alarms)
        else:
            self._replace_alarms(
                [{**alarm, **alarm_weekdays_update_payload(alarm, weekdays_list)}]
            )
        self.publish_updates()

    def _configured_alarm_api(self) -> tuple["Hatch", str]:
        if self._alarm_api is None or self._alarm_auth_token is None:
            raise RuntimeError(f"{self.device_name} alarm API is not configured")
        return self._alarm_api, self._alarm_auth_token

    def _replace_alarms(self, updated_alarms: list[ScheduledRoutineAlarm]) -> None:
        if not updated_alarms:
            return

        by_id = {
            str(alarm.get("id")): alarm
            for alarm in updated_alarms
            if alarm.get("id") is not None
        }
        merged = [
            by_id.get(str(alarm.get("id")), alarm)
            for alarm in getattr(self, "alarms", [])
        ]
        existing_ids = {str(alarm.get("id")) for alarm in merged}
        merged.extend(
            alarm
            for alarm_id, alarm in by_id.items()
            if alarm_id not in existing_ids
        )
        self.alarms = merged
