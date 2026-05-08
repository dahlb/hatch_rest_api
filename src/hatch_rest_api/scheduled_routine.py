from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from .hatch import Hatch

ALARM_ROUTINE_TYPE = "alarm"


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
    if enabled and _is_one_time_alarm(alarm):
        start_time = _next_one_time_start_time(start_time, now=now)

    return {
        "id": alarm["id"],
        "name": alarm.get("name"),
        "active": alarm.get("active"),
        "enabled": enabled,
        "displayOrder": alarm.get("displayOrder"),
        "startTime": start_time,
        "endTime": alarm.get("endTime"),
    }


def alarm_routines(routines: list[ScheduledRoutineAlarm]) -> list[ScheduledRoutineAlarm]:
    return [
        routine
        for routine in routines
        if routine.get("type") == ALARM_ROUTINE_TYPE
    ]


def _is_one_time_alarm(alarm: ScheduledRoutineAlarm) -> bool:
    days_of_week = alarm.get("daysOfWeek")
    return days_of_week is None or days_of_week == 0


def _next_one_time_start_time(
    start_time: str | None,
    now: datetime | None = None,
) -> str | None:
    if not isinstance(start_time, str):
        return start_time

    parsed_start_time = _parse_local_datetime(start_time)
    if parsed_start_time is None:
        return start_time

    if now is None:
        now = datetime.now()
    if parsed_start_time.tzinfo is not None:
        parsed_start_time = parsed_start_time.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)

    next_start_time = datetime.combine(now.date(), parsed_start_time.time())
    if next_start_time <= now:
        next_start_time = next_start_time + timedelta(days=1)

    return _format_like_original(start_time, next_start_time)


def _parse_local_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_like_original(original: str, value: datetime) -> str:
    if "." in original:
        return value.isoformat()
    if len(original.split("T", 1)[-1].split(":")) <= 2:
        return value.isoformat(timespec="minutes")
    return value.isoformat(timespec="seconds")


class ScheduledRoutineAlarmMixin:
    alarms: list[ScheduledRoutineAlarm]
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
            alarm["enabled"] = enabled
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
