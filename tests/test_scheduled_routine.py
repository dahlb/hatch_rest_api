import unittest
from datetime import datetime

from hatch_rest_api.hatch import Hatch
from hatch_rest_api.scheduled_routine import (
    SCHEDULED_ROUTINE_ALARM_PRODUCTS,
    alarm_update_payload,
)


class FakeResponse:
    status = 200
    headers = {}

    def __init__(self, url: str, payload: dict):
        self.url = url
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)


class FakeSession:
    def __init__(self):
        self.calls = []

    async def get(self, url: str, headers: dict, params: dict):
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

    async def post(self, url: str, json: dict, headers: dict):
        self.calls.append(("POST", url, headers, json))
        if url.endswith("/service/app/routine/v2/editMultiple"):
            return FakeResponse(
                url,
                {
                    "status": "success",
                    "payload": {
                        "confirmDataVersion": True,
                        "item": [
                            {
                                "id": json["mrds"][0]["id"],
                                "name": json["mrds"][0]["name"],
                                "active": json["mrds"][0]["active"],
                                "enabled": json["mrds"][0]["enabled"],
                                "type": "alarm",
                                "macAddress": "AA:BB:CC",
                            }
                        ],
                        "dataVersion": "version-1",
                    },
                },
            )
        return FakeResponse(
            url,
            {
                "status": "success",
                "payload": [
                    {"id": 5, "type": "routine", "enabled": True},
                    {
                        "id": 2,
                        "name": "Wake",
                        "active": True,
                        "enabled": False,
                        "type": "alarm",
                        "macAddress": "AA:BB:CC",
                    },
                ],
            },
        )


class ScheduledRoutineAlarmTest(unittest.TestCase):
    def test_alarm_products_include_all_restore_generations(self):
        self.assertEqual(
            SCHEDULED_ROUTINE_ALARM_PRODUCTS,
            {"restoreIot", "restoreV4", "restoreV5"},
        )

    def test_alarm_update_payload_preserves_active_and_toggles_enabled(self):
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": False,
            "enabled": True,
            "displayOrder": 7,
            "startTime": "2026-05-08T07:30:00",
            "endTime": None,
            "daysOfWeek": 127,
        }

        payload = alarm_update_payload(alarm, False)

        self.assertEqual(payload["id"], 2)
        self.assertEqual(payload["name"], "Wake")
        self.assertIs(payload["active"], False)
        self.assertIs(payload["enabled"], False)
        self.assertEqual(payload["displayOrder"], 7)
        self.assertEqual(payload["startTime"], "2026-05-08T07:30:00")

    def test_one_time_alarm_rolls_to_tomorrow_when_time_passed(self):
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-08T07:30:00",
            "daysOfWeek": 0,
        }

        payload = alarm_update_payload(
            alarm,
            True,
            now=datetime(2026, 5, 8, 8, 0, 0),
        )

        self.assertEqual(payload["startTime"], "2026-05-09T07:30:00")

    def test_one_time_alarm_rolls_to_today_when_time_is_future(self):
        alarm = {
            "id": 2,
            "name": "Wake",
            "active": True,
            "enabled": False,
            "startTime": "2026-05-07T07:30:00",
            "daysOfWeek": 0,
        }

        payload = alarm_update_payload(
            alarm,
            True,
            now=datetime(2026, 5, 8, 6, 0, 0),
        )

        self.assertEqual(payload["startTime"], "2026-05-08T07:30:00")


class HatchScheduledRoutineApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_routine_fetch_uses_v3_alarm_query(self):
        session = FakeSession()
        api = Hatch(client_session=session)

        routines = await api.scheduled_routines(
            auth_token="token",
            mac="AA:BB:CC",
            types=["alarm"],
        )

        self.assertEqual(routines[0]["id"], 2)
        method, url, headers, params = session.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.endswith("/service/app/routine/v3/fetch"))
        self.assertEqual(headers["X-HatchBaby-Auth"], "token")
        self.assertEqual(params, {"macAddress": "AA:BB:CC", "types": ["alarm"]})

    async def test_alarm_update_uses_edit_multiple_and_confirms_data_version(self):
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
            "endTime": None,
            "daysOfWeek": 127,
        }

        updated = await api.update_scheduled_routine_alarm_enabled(
            auth_token="token",
            mac="AA:BB:CC",
            alarm=alarm,
            enabled=False,
        )

        self.assertEqual(updated, [
            {
                "id": 2,
                "name": "Wake",
                "active": True,
                "enabled": False,
                "type": "alarm",
                "macAddress": "AA:BB:CC",
            }
        ])
        _, edit_url, _, edit_body = session.calls[0]
        self.assertTrue(edit_url.endswith("/service/app/routine/v2/editMultiple"))
        self.assertEqual(edit_body["type"], "alarm")
        self.assertEqual(edit_body["mrds"][0]["id"], 2)
        self.assertIs(edit_body["mrds"][0]["active"], True)
        self.assertIs(edit_body["mrds"][0]["enabled"], False)

        _, confirm_url, _, confirm_body = session.calls[1]
        self.assertTrue(confirm_url.endswith("/service/app/v2/dataVersion"))
        self.assertEqual(confirm_body, {
            "dataVersion": "version-1",
            "macAddress": "AA:BB:CC",
            "success": True,
            "returnAllRoutines": True,
        })


if __name__ == "__main__":
    unittest.main()
