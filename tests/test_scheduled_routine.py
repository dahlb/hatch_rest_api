"""Tests for scheduled-routine alarm payloads, API calls and the device mixin."""

from collections.abc import Iterable
from datetime import datetime, time
from typing import Any, ClassVar
import unittest

import pytest

from hatch_rest_api.hatch import Hatch
from hatch_rest_api.scheduled_routine import (
    SCHEDULED_ROUTINE_ALARM_PRODUCTS,
    ScheduledRoutineAlarmMixin,
    alarm_update_payload,
    alarm_wake_time_update_payload,
    alarm_weekdays_update_payload,
    days_of_week_label,
    days_of_week_to_weekdays,
    weekdays_to_days_of_week,
)


class FakeResponse:
    """Stand-in for an aiohttp response with a fixed JSON payload."""

    status = 200
    headers: ClassVar[dict[str, str]] = {}

    def __init__(self, url: str, payload: dict[str, Any]) -> None:
        """Store the request URL and the payload to return."""
        self.url = url
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        """Return the payload."""
        return self._payload

    async def text(self) -> str:
        """Return the payload as text."""
        return str(self._payload)


class FakeSession:
    """Stand-in for an aiohttp session that mimics the routine endpoints."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[tuple[str, str, dict[str, str], Any]] = []
        self.last_mrds: list[dict[str, Any]] = []

    async def get(self, url: str, headers: dict[str, str], params: dict[str, Any]) -> FakeResponse:
        """Record the call and return one alarm routine."""
        self.calls.append(("GET", url, headers, params))
        return FakeResponse(
            url,
            {
                "status": "success",
                "payload": [
                    {
                        "id": 2,
                        "name": "Wake",
                        "active": True,
                        "enabled": True,
                        "type": "alarm",
                        "macAddress": "AA:BB:CC",
                        "displayOrder": 1,
                    }
                ],
            },
        )

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
        """Record the call and answer an edit or a data-version confirmation."""
        self.calls.append(("POST", url, headers, json))
        if url.endswith("/service/app/routine/v2/editMultiple"):
            self.last_mrds = json["mrds"]
            item = {
                "id": json["mrds"][0]["id"],
                "name": json["mrds"][0]["name"],
                "active": json["mrds"][0]["active"],
                "enabled": json["mrds"][0]["enabled"],
                "type": "alarm",
                "macAddress": "AA:BB:CC",
                "startTime": json["mrds"][0]["startTime"],
                "endTime": json["mrds"][0]["endTime"],
            }
            if "daysOfWeek" in json["mrds"][0]:
                item["daysOfWeek"] = json["mrds"][0]["daysOfWeek"]
            return FakeResponse(
                url,
                {
                    "status": "success",
                    "payload": {
                        "confirmDataVersion": True,
                        "item": [item],
                        "dataVersion": "version-1",
                    },
                },
            )
        item = {
            "id": self.last_mrds[0]["id"],
            "name": self.last_mrds[0]["name"],
            "active": self.last_mrds[0]["active"],
            "enabled": self.last_mrds[0]["enabled"],
            "type": "alarm",
            "macAddress": "AA:BB:CC",
            "startTime": self.last_mrds[0]["startTime"],
            "endTime": self.last_mrds[0]["endTime"],
        }
        if "daysOfWeek" in self.last_mrds[0]:
            item["daysOfWeek"] = self.last_mrds[0]["daysOfWeek"]
        return FakeResponse(
            url,
            {
                "status": "success",
                "payload": [
                    {"id": 5, "type": "routine", "enabled": True},
                    item,
                ],
            },
        )


class EmptyAlarmUpdateApi:
    """Fake Hatch API whose alarm updates return no routines."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[tuple[Any, ...]] = []

    async def update_scheduled_routine_alarm_enabled(
        self,
        auth_token: str,
        mac: str,
        alarm: dict[str, Any],
        enabled: bool,
    ) -> list[dict[str, Any]]:
        """Record the call and return no routines."""
        self.calls.append((auth_token, mac, alarm["id"], enabled))
        return []

    async def update_scheduled_routine_alarm_weekdays(
        self,
        auth_token: str,
        mac: str,
        alarm: dict[str, Any],
        weekdays: Iterable[str],
    ) -> list[dict[str, Any]]:
        """Record the call and return no routines."""
        self.calls.append((auth_token, mac, alarm["id"], list(weekdays)))
        return []


class RefreshAlarmApi:
    """Fake Hatch API that returns a fixed list of alarms."""

    def __init__(self, alarms: list[dict[str, Any]]) -> None:
        """Store the alarms to return."""
        self.alarms = alarms
        self.calls: list[tuple[str, str, list[str]]] = []

    async def scheduled_routines(
        self,
        auth_token: str,
        mac: str,
        types: list[str],
    ) -> list[dict[str, Any]]:
        """Record the call and return the stored alarms."""
        self.calls.append((auth_token, mac, types))
        return list(self.alarms)


class FakeAlarmDevice(ScheduledRoutineAlarmMixin):
    """Minimal device using the alarm mixin that counts published updates."""

    mac = "AA:BB:CC"
    device_name = "Restore"

    def __init__(self) -> None:
        """Start with no published updates."""
        self.publish_count = 0

    def publish_updates(self) -> None:
        """Count the update."""
        self.publish_count += 1


class ScheduledRoutineAlarmTest(unittest.TestCase):
    """Alarm payload helpers and weekday conversions."""

    def test_alarm_products_include_all_restore_generations(self) -> None:
        """Alarm products include all restore generations."""
        assert {"restoreIot", "restoreV4", "restoreV5"} == SCHEDULED_ROUTINE_ALARM_PRODUCTS

    def test_alarm_update_payload_preserves_active_and_toggles_enabled(self) -> None:
        """Alarm update payload preserves active and toggles enabled."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": False,
            "enabled": True,
            "displayOrder": 7,
            "startTime": "2026-05-08T07:30:00",
            "endTime": "2026-05-08T08:00:00",
            "daysOfWeek": 127,
        }

        payload = alarm_update_payload(alarm, False)

        assert payload["id"] == 2
        assert payload["name"] == "Wake"
        assert payload["active"] is False
        assert payload["enabled"] is False
        assert payload["displayOrder"] == 7
        assert payload["startTime"] == "2026-05-08T07:30:00"
        assert payload["endTime"] == "2026-05-08T08:00:00"

    def test_weekdays_to_days_of_week_converts_weekday_lists_to_bitmask(self) -> None:
        """Weekdays to days of week converts weekday lists to bitmask."""
        assert weekdays_to_days_of_week(["monday", "tuesday", "friday"]) == 38
        assert weekdays_to_days_of_week([]) == 0
        assert weekdays_to_days_of_week([" Sunday ", "SATURDAY"]) == 65

    def test_days_of_week_to_weekdays_and_label_convert_bitmask(self) -> None:
        """Days of week to weekdays and label convert bitmask."""
        assert days_of_week_to_weekdays(38) == ["monday", "tuesday", "friday"]
        assert days_of_week_to_weekdays(127) == [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        assert days_of_week_to_weekdays(0) == []
        assert days_of_week_label(0) == "Once"
        assert days_of_week_label(62) == "Weekdays"
        assert days_of_week_label(65) == "Weekends"
        assert days_of_week_label(127) == "Every day"
        assert days_of_week_label(42) == "Mon, Wed, Fri"

    def test_alarm_weekdays_update_payload_preserves_fields_and_updates_days(self) -> None:
        """Alarm weekdays update payload preserves fields and updates days."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": False,
            "enabled": True,
            "displayOrder": 7,
            "startTime": "2026-05-08T07:30:00",
            "endTime": "2026-05-08T08:00:00",
            "daysOfWeek": 127,
        }

        payload = alarm_weekdays_update_payload(alarm, ["monday", "friday"])

        assert payload["id"] == 2
        assert payload["name"] == "Wake"
        assert payload["active"] is False
        assert payload["enabled"] is True
        assert payload["displayOrder"] == 7
        assert payload["startTime"] == "2026-05-08T07:30:00"
        assert payload["endTime"] == "2026-05-08T08:00:00"
        assert payload["daysOfWeek"] == 34

    def test_alarm_weekdays_update_payload_allows_one_time_alarm(self) -> None:
        """Alarm weekdays update payload allows one time alarm."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": True,
            "startTime": "2026-05-08T07:30:00",
            "endTime": "2026-05-08T08:00:00",
            "daysOfWeek": 127,
        }

        payload = alarm_weekdays_update_payload(alarm, [])

        assert payload["daysOfWeek"] == 0
        assert payload["enabled"] is True
        assert payload["startTime"] == "2026-05-08T07:30:00"
        assert payload["endTime"] == "2026-05-08T08:00:00"

    def test_alarm_weekdays_update_payload_rejects_invalid_weekday(self) -> None:
        """Alarm weekdays update payload rejects invalid weekday."""
        alarm = {"id": 2}

        with pytest.raises(ValueError, match="Unsupported alarm weekday"):
            alarm_weekdays_update_payload(alarm, ["funday"])

    def test_one_time_alarm_enable_rolls_wake_time_to_tomorrow_when_time_passed(self) -> None:
        """One time alarm enable rolls wake time to tomorrow when time passed."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08T07:00:00",
            "endTime": "2026-05-08T07:30:00",
            "daysOfWeek": 0,
        }

        payload = alarm_update_payload(
            alarm,
            True,
            now=datetime(2026, 5, 8, 8, 0, 0),
        )

        assert payload["startTime"] == "2026-05-09T07:00:00"
        assert payload["endTime"] == "2026-05-09T07:30:00"

    def test_one_time_alarm_enable_rolls_wake_time_to_today_when_time_is_future(self) -> None:
        """One time alarm enable rolls wake time to today when time is future."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-07T07:00:00",
            "endTime": "2026-05-07T07:30:00",
            "daysOfWeek": 0,
        }

        payload = alarm_update_payload(
            alarm,
            True,
            now=datetime(2026, 5, 8, 6, 0, 0),
        )

        assert payload["startTime"] == "2026-05-08T07:00:00"
        assert payload["endTime"] == "2026-05-08T07:30:00"

    def test_wake_time_update_preserves_sunrise_lead_for_repeating_alarm(self) -> None:
        """Wake time update preserves sunrise lead for repeating alarm."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "displayOrder": 3,
            "startTime": "2026-05-08T07:00:00",
            "endTime": "2026-05-08T07:30:00",
            "daysOfWeek": 127,
        }

        payload = alarm_wake_time_update_payload(alarm, time(8, 15))

        assert payload["id"] == 2
        assert payload["name"] == "Wake"
        assert payload["active"] is True
        assert payload["enabled"] is False
        assert payload["displayOrder"] == 3
        assert payload["startTime"] == "2026-05-08T07:45:00"
        assert payload["endTime"] == "2026-05-08T08:15:00"

    def test_wake_time_update_rolls_one_time_alarm_to_next_occurrence(self) -> None:
        """Wake time update rolls one time alarm to next occurrence."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08T07:00:00",
            "endTime": "2026-05-08T07:30:00",
            "daysOfWeek": 0,
        }

        payload = alarm_wake_time_update_payload(
            alarm,
            time(6, 45),
            now=datetime(2026, 5, 8, 8, 0, 0),
        )

        assert payload["startTime"] == "2026-05-09T06:15:00"
        assert payload["endTime"] == "2026-05-09T06:45:00"

    def test_wake_time_update_uses_sunrise_duration_when_end_time_is_missing(self) -> None:
        """Wake time update uses sunrise duration when end time is missing."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08T10:45:00",
            "endTime": None,
            "daysOfWeek": 62,
            "steps": [
                {
                    "name": "Sunrise",
                    "enabled": True,
                    "color": {"duration": 2700, "ignore": False},
                }
            ],
        }

        payload = alarm_wake_time_update_payload(alarm, time(11, 15))

        assert payload["startTime"] == "2026-05-08T10:30:00"
        assert payload["endTime"] is None
        assert payload["enabled"] is False

    def test_one_time_alarm_enable_uses_sunrise_duration_when_end_time_is_missing(self) -> None:
        """One time alarm enable uses sunrise duration when end time is missing."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08 10:45:00",
            "endTime": None,
            "daysOfWeek": 0,
            "steps": [
                {
                    "name": "Sunrise",
                    "enabled": True,
                    "color": {"duration": 2700, "ignore": False},
                }
            ],
        }

        payload = alarm_update_payload(
            alarm,
            True,
            now=datetime(2026, 5, 8, 12, 0, 0),
        )

        assert payload["startTime"] == "2026-05-09 10:45:00"
        assert payload["endTime"] is None

    def test_wake_time_update_requires_sunrise_duration_when_end_time_is_missing(self) -> None:
        """Wake time update requires sunrise duration when end time is missing."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08T10:45:00",
            "endTime": None,
            "daysOfWeek": 62,
        }

        with pytest.raises(ValueError, match="valid sunrise duration"):
            alarm_wake_time_update_payload(alarm, time(11, 15))

    def test_wake_time_update_requires_valid_start_time(self) -> None:
        """Wake time update requires valid start time."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "not-a-date",
            "endTime": "2026-05-08T07:30:00",
            "daysOfWeek": 127,
        }

        with pytest.raises(ValueError, match="valid startTime"):
            alarm_wake_time_update_payload(alarm, time(6, 45))

    def test_wake_time_update_requires_valid_end_time_when_end_time_is_present(self) -> None:
        """Wake time update requires valid end time when end time is present."""
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08T07:00:00",
            "endTime": "not-a-date",
            "daysOfWeek": 127,
        }

        with pytest.raises(ValueError, match="valid endTime"):
            alarm_wake_time_update_payload(alarm, time(6, 45))


class HatchScheduledRoutineApiTest(unittest.IsolatedAsyncioTestCase):
    """Hatch client calls for reading and editing scheduled routines."""

    async def test_scheduled_routine_fetch_uses_v3_alarm_query(self) -> None:
        """Scheduled routine fetch uses v3 alarm query."""
        session = FakeSession()
        api = Hatch(client_session=session)

        routines = await api.scheduled_routines(
            auth_token="token",
            mac="AA:BB:CC",
            types=["alarm"],
        )

        assert routines[0]["id"] == 2
        method, url, headers, params = session.calls[0]
        assert method == "GET"
        assert url.endswith("/service/app/routine/v3/fetch")
        assert headers["X-HatchBaby-Auth"] == "token"
        assert params == {"macAddress": "AA:BB:CC", "types": ["alarm"]}

    async def test_alarm_update_uses_edit_multiple_and_confirms_data_version(self) -> None:
        """Alarm update uses edit multiple and confirms data version."""
        session = FakeSession()
        api = Hatch(client_session=session)
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": True,
            "type": "alarm",
            "macAddress": "AA:BB:CC",
            "displayOrder": 1,
            "startTime": "2026-05-08T07:30:00",
            "endTime": "2026-05-08T08:00:00",
            "daysOfWeek": 127,
        }

        updated = await api.update_scheduled_routine_alarm_enabled(
            auth_token="token",
            mac="AA:BB:CC",
            alarm=alarm,
            enabled=False,
        )

        assert updated == [
            {
                "id": 2,
                "name": "Wake",
                "active": True,
                "enabled": False,
                "type": "alarm",
                "macAddress": "AA:BB:CC",
                "startTime": "2026-05-08T07:30:00",
                "endTime": "2026-05-08T08:00:00",
            }
        ]
        _, edit_url, _, edit_body = session.calls[0]
        assert edit_url.endswith("/service/app/routine/v2/editMultiple")
        assert edit_body["type"] == "alarm"
        assert edit_body["mrds"][0]["id"] == 2
        assert edit_body["mrds"][0]["active"] is True
        assert edit_body["mrds"][0]["enabled"] is False
        assert edit_body["mrds"][0]["startTime"] == "2026-05-08T07:30:00"
        assert edit_body["mrds"][0]["endTime"] == "2026-05-08T08:00:00"

        _, confirm_url, _, confirm_body = session.calls[1]
        assert confirm_url.endswith("/service/app/v2/dataVersion")
        assert confirm_body == {
            "dataVersion": "version-1",
            "macAddress": "AA:BB:CC",
            "success": True,
            "returnAllRoutines": True,
        }

    async def test_alarm_wake_time_update_uses_edit_multiple_and_preserves_enabled(
        self,
    ) -> None:
        """Alarm wake time update uses edit multiple and preserves enabled."""
        session = FakeSession()
        api = Hatch(client_session=session)
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "type": "alarm",
            "macAddress": "AA:BB:CC",
            "displayOrder": 1,
            "startTime": "2026-05-08T07:30:00",
            "endTime": "2026-05-08T08:00:00",
            "daysOfWeek": 127,
        }

        updated = await api.update_scheduled_routine_alarm_wake_time(
            auth_token="token",
            mac="AA:BB:CC",
            alarm=alarm,
            wake_time=time(8, 15),
        )

        assert updated == [
            {
                "id": 2,
                "name": "Wake",
                "active": True,
                "enabled": False,
                "type": "alarm",
                "macAddress": "AA:BB:CC",
                "startTime": "2026-05-08T07:45:00",
                "endTime": "2026-05-08T08:15:00",
            }
        ]
        _, edit_url, _, edit_body = session.calls[0]
        assert edit_url.endswith("/service/app/routine/v2/editMultiple")
        assert edit_body["type"] == "alarm"
        assert edit_body["mrds"][0]["active"] is True
        assert edit_body["mrds"][0]["enabled"] is False
        assert edit_body["mrds"][0]["startTime"] == "2026-05-08T07:45:00"
        assert edit_body["mrds"][0]["endTime"] == "2026-05-08T08:15:00"

    async def test_alarm_weekdays_update_uses_edit_multiple_and_confirms_data_version(
        self,
    ) -> None:
        """Alarm weekdays update uses edit multiple and confirms data version."""
        session = FakeSession()
        api = Hatch(client_session=session)
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "type": "alarm",
            "macAddress": "AA:BB:CC",
            "displayOrder": 1,
            "startTime": "2026-05-08T07:30:00",
            "endTime": "2026-05-08T08:00:00",
            "daysOfWeek": 127,
        }

        updated = await api.update_scheduled_routine_alarm_weekdays(
            auth_token="token",
            mac="AA:BB:CC",
            alarm=alarm,
            weekdays=["monday", "tuesday", "friday"],
        )

        assert updated == [
            {
                "id": 2,
                "name": "Wake",
                "active": True,
                "enabled": False,
                "type": "alarm",
                "macAddress": "AA:BB:CC",
                "startTime": "2026-05-08T07:30:00",
                "endTime": "2026-05-08T08:00:00",
                "daysOfWeek": 38,
            }
        ]
        _, edit_url, _, edit_body = session.calls[0]
        assert edit_url.endswith("/service/app/routine/v2/editMultiple")
        assert edit_body["type"] == "alarm"
        assert edit_body["mrds"][0]["active"] is True
        assert edit_body["mrds"][0]["enabled"] is False
        assert edit_body["mrds"][0]["startTime"] == "2026-05-08T07:30:00"
        assert edit_body["mrds"][0]["endTime"] == "2026-05-08T08:00:00"
        assert edit_body["mrds"][0]["daysOfWeek"] == 38

        _, confirm_url, _, confirm_body = session.calls[1]
        assert confirm_url.endswith("/service/app/v2/dataVersion")
        assert confirm_body == {
            "dataVersion": "version-1",
            "macAddress": "AA:BB:CC",
            "success": True,
            "returnAllRoutines": True,
        }


class ScheduledRoutineAlarmMixinTest(unittest.IsolatedAsyncioTestCase):
    """Device alarm mixin behavior."""

    async def test_failed_initial_fetch_remains_alarm_capable_for_refresh(self) -> None:
        """Failed initial fetch remains alarm capable for refresh."""
        api = RefreshAlarmApi(
            [
                {
                    "id": 2,
                    "name": "Wake",
                    "type": "alarm",
                    "macAddress": "AA:BB:CC",
                }
            ]
        )
        device = FakeAlarmDevice()

        device.configure_alarm_api(api=api, auth_token="token", alarms=None)

        assert device.alarm_capable is True
        assert device.alarms_loaded is False
        assert device.alarms == []

        refreshed = await device.refresh_alarms()

        assert api.calls == [("token", "AA:BB:CC", ["alarm"])]
        assert device.alarms_loaded is True
        assert refreshed == api.alarms
        assert device.alarms == api.alarms
        assert device.publish_count == 1

    async def test_set_alarm_enabled_fallback_rolls_one_time_alarm_times(self) -> None:
        """Set alarm enabled fallback rolls one time alarm times."""
        api = EmptyAlarmUpdateApi()
        device = FakeAlarmDevice()
        device.configure_alarm_api(
            api=api,
            auth_token="token",
            alarms=[
                {
                    "id": 2,
                    "name": "Wake",
                    "active": True,
                    "enabled": False,
                    "type": "alarm",
                    "macAddress": "AA:BB:CC",
                    "startTime": "2000-01-01T07:00:00",
                    "endTime": "2000-01-01T07:30:00",
                    "daysOfWeek": 0,
                }
            ],
        )
        before_update = datetime.now()

        await device.set_alarm_enabled(2, True)

        assert api.calls == [("token", "AA:BB:CC", 2, True)]
        assert device.publish_count == 1
        updated_alarm = device.alarms[0]
        assert updated_alarm["enabled"] is True
        assert updated_alarm["daysOfWeek"] == 0
        assert updated_alarm["startTime"] != "2000-01-01T07:00:00"
        assert updated_alarm["endTime"] != "2000-01-01T07:30:00"
        updated_start = datetime.fromisoformat(updated_alarm["startTime"])
        updated_end = datetime.fromisoformat(updated_alarm["endTime"])
        assert updated_end > before_update
        assert (updated_end - updated_start).total_seconds() == 1800

    async def test_set_alarm_weekdays_accepts_generator_input(self) -> None:
        """Set alarm weekdays accepts generator input."""
        api = EmptyAlarmUpdateApi()
        device = FakeAlarmDevice()
        device.configure_alarm_api(
            api=api,
            auth_token="token",
            alarms=[
                {
                    "id": 2,
                    "name": "Wake",
                    "active": True,
                    "enabled": True,
                    "type": "alarm",
                    "macAddress": "AA:BB:CC",
                    "startTime": "2026-05-08T07:30:00",
                    "endTime": "2026-05-08T08:00:00",
                    "daysOfWeek": 0,
                }
            ],
        )

        await device.set_alarm_weekdays(
            2,
            (weekday for weekday in ["monday", "wednesday", "friday"]),
        )

        assert api.calls == [("token", "AA:BB:CC", 2, ["monday", "wednesday", "friday"])]
        assert device.publish_count == 1
        updated_alarm = device.alarms[0]
        assert updated_alarm["daysOfWeek"] == 42


if __name__ == "__main__":
    unittest.main()
