import asyncio
import unittest
from unittest.mock import AsyncMock

from hatch_rest_api.restore_v5 import RestoreV5


class FakeRestoreV5(RestoreV5):
    def __init__(self):
        self._updates: list[dict] = []
        self._published = 0
        self.current_playing = "none"
        self.current_id = 0
        self.current_step = 0
        self.paused = False
        self.is_snoozed = False
        self.favorites: list[dict] = []
        self.device_name = "Fake Restore"
        self.mac = "AA:BB:CC:DD:EE:FF"
        self._alarm_api = None
        self._alarm_auth_token = None

    def _update(self, desired_state):
        self._updates.append(desired_state)

    def publish_updates(self):
        self._published += 1


class RestoreV5RoutineControlTest(unittest.TestCase):
    def test_stop_routine_writes_same_payload_as_turn_off(self):
        device = FakeRestoreV5()
        device.current_playing = "routine"
        device.current_step = 3

        device.stop_routine()

        self.assertEqual(
            device._updates,
            [{"current": {"srId": 0, "step": 0, "playing": "none"}}],
        )

    def test_pause_routine_writes_paused_true_when_routine_playing(self):
        device = FakeRestoreV5()
        device.current_playing = "routine"

        device.pause_routine()

        self.assertEqual(device._updates, [{"current": {"paused": True}}])

    def test_pause_routine_is_noop_when_no_routine_playing(self):
        device = FakeRestoreV5()
        device.current_playing = "none"

        device.pause_routine()

        self.assertEqual(device._updates, [])

    def test_pause_routine_is_noop_when_already_paused(self):
        device = FakeRestoreV5()
        device.current_playing = "routine"
        device.paused = True

        device.pause_routine()

        self.assertEqual(device._updates, [])

    def test_resume_routine_writes_paused_false_when_paused(self):
        device = FakeRestoreV5()
        device.current_playing = "routine"
        device.paused = True

        device.resume_routine()

        self.assertEqual(device._updates, [{"current": {"paused": False}}])

    def test_resume_routine_is_noop_when_not_paused(self):
        device = FakeRestoreV5()
        device.current_playing = "routine"
        device.paused = False

        device.resume_routine()

        self.assertEqual(device._updates, [])

    def test_snooze_alarm_writes_active_true_with_start_time(self):
        device = FakeRestoreV5()

        device.snooze_alarm()

        self.assertEqual(len(device._updates), 1)
        update = device._updates[0]
        self.assertIn("snooze", update)
        self.assertEqual(update["snooze"]["active"], True)
        # startTime is "YYYY-MM-DD HH:MM:SS" — 19 chars
        start_time = update["snooze"]["startTime"]
        self.assertEqual(len(start_time), 19)
        self.assertEqual(start_time[4], "-")
        self.assertEqual(start_time[7], "-")
        self.assertEqual(start_time[10], " ")
        self.assertEqual(start_time[13], ":")
        self.assertEqual(start_time[16], ":")


class RestoreV5AdvanceStepTest(unittest.TestCase):
    def _device_with_routine(self, *, steps: int, current_step: int = 0) -> FakeRestoreV5:
        device = FakeRestoreV5()
        device.current_playing = "routine"
        device.current_id = 42
        device.current_step = current_step
        device.favorites = [
            {
                "id": 42,
                "type": "routine",
                "steps": [{"name": f"step{i}"} for i in range(steps)],
            }
        ]
        return device

    def test_advance_step_writes_next_step(self):
        device = self._device_with_routine(steps=3, current_step=1)

        device.advance_step()

        self.assertEqual(device._updates, [{"current": {"step": 2}}])

    def test_advance_step_noop_when_at_last_step(self):
        device = self._device_with_routine(steps=3, current_step=2)

        device.advance_step()

        self.assertEqual(device._updates, [])

    def test_advance_step_noop_when_no_routine_playing(self):
        device = self._device_with_routine(steps=3, current_step=0)
        device.current_playing = "none"

        device.advance_step()

        self.assertEqual(device._updates, [])

    def test_advance_step_noop_when_paused(self):
        device = self._device_with_routine(steps=3, current_step=0)
        device.paused = True

        device.advance_step()

        self.assertEqual(device._updates, [])

    def test_advance_step_noop_when_routine_has_no_steps(self):
        device = self._device_with_routine(steps=0, current_step=0)

        device.advance_step()

        self.assertEqual(device._updates, [])

    def test_can_advance_step_reflects_remaining_steps(self):
        device = self._device_with_routine(steps=3, current_step=0)
        self.assertTrue(device.can_advance_step)
        device.current_step = 2
        self.assertFalse(device.can_advance_step)


class RestoreV5SwapRoutineTest(unittest.TestCase):
    def _device_with_swappables(self, active_id: int | None = 10) -> FakeRestoreV5:
        device = FakeRestoreV5()
        device.favorites = [
            {"id": 10, "type": "routine", "button0": True, "displayOrder": 0, "active": active_id == 10},
            {"id": 20, "type": "routine", "button0": True, "displayOrder": 1, "active": active_id == 20},
            {"id": 30, "type": "routine", "button0": True, "displayOrder": 2, "active": active_id == 30},
            {"id": 99, "type": "routine", "button0": False, "displayOrder": 3, "active": False},
        ]
        device._alarm_auth_token = "token"
        return device

    def test_swappable_routines_filters_and_sorts(self):
        device = self._device_with_swappables()
        ids = [r["id"] for r in device.swappable_routines]
        self.assertEqual(ids, [10, 20, 30])

    def test_can_swap_routine_requires_more_than_one(self):
        device = self._device_with_swappables()
        self.assertTrue(device.can_swap_routine)
        device.favorites = [device.favorites[0]]
        self.assertTrue(device.can_swap_routine is False)

    def test_swap_routine_advances_to_next_swappable(self):
        device = self._device_with_swappables(active_id=10)
        api = AsyncMock()
        api.bulk_edit_swappables = AsyncMock(
            return_value=[
                {"id": 10, "active": False},
                {"id": 20, "active": True},
            ]
        )
        device._alarm_api = api

        asyncio.run(device.swap_routine())

        api.bulk_edit_swappables.assert_awaited_once()
        kwargs = api.bulk_edit_swappables.await_args.kwargs
        self.assertEqual(kwargs["auth_token"], "token")
        self.assertEqual(kwargs["mac"], device.mac)
        self.assertEqual(
            [(r["id"], r["active"]) for r in kwargs["routines"]],
            [(10, False), (20, True)],
        )
        active_ids = [f["id"] for f in device.favorites if f.get("active")]
        self.assertEqual(active_ids, [20])

    def test_swap_routine_wraps_around(self):
        device = self._device_with_swappables(active_id=30)
        api = AsyncMock()
        api.bulk_edit_swappables = AsyncMock(return_value=[])
        device._alarm_api = api

        asyncio.run(device.swap_routine())

        kwargs = api.bulk_edit_swappables.await_args.kwargs
        self.assertEqual(
            [(r["id"], r["active"]) for r in kwargs["routines"]],
            [(30, False), (10, True)],
        )
        active_ids = [f["id"] for f in device.favorites if f.get("active")]
        self.assertEqual(active_ids, [10])

    def test_swap_routine_noop_when_only_one_swappable(self):
        device = self._device_with_swappables()
        device.favorites = [device.favorites[0]]
        api = AsyncMock()
        device._alarm_api = api

        asyncio.run(device.swap_routine())

        api.bulk_edit_swappables.assert_not_called()

    def test_swap_routine_raises_when_api_not_configured(self):
        device = self._device_with_swappables()
        device._alarm_api = None

        with self.assertRaises(RuntimeError):
            asyncio.run(device.swap_routine())

    def test_swap_routine_falls_back_to_first_when_none_active(self):
        device = self._device_with_swappables(active_id=None)
        api = AsyncMock()
        api.bulk_edit_swappables = AsyncMock(return_value=[])
        device._alarm_api = api

        asyncio.run(device.swap_routine())

        kwargs = api.bulk_edit_swappables.await_args.kwargs
        self.assertEqual(
            [(r["id"], r["active"]) for r in kwargs["routines"]],
            [(10, False), (20, True)],
        )


if __name__ == "__main__":
    unittest.main()
