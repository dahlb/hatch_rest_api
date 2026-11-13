# The original Hatch Restore (product `restore`)

Protocol notes for the first Hatch Restore, as handled by `hatch_rest_api.Restore`.
Everything here was observed on a real device (hardware 5.12.1, firmware 5.1.376)
in November 2026; the tools used are described under [How this was verified](#how-this-was-verified).
All ids and values below are examples.

## Which Restore is this?

Hatch sold two first-generation Restores that look the same and report different
product codes to the Hatch cloud:

| Product code | Class | Notes |
|---|---|---|
| `restore` | `Restore` | The original. Model label RESTORE01 or RESTORE02 underneath (both FCC ids share one manual) |
| `restoreIot` | `RestoreIot` | The later first-gen unit, on the newer cloud layout |

The Restore 2 and Restore 3 are `restoreV4` and `restoreV5`.

Before `restore` was added, `Hatch.iot_devices()` never asked for it. Hatch only
returns devices whose product code is requested, so an account holding only this
model got an empty list and setup failed with "No compatible devices found".

## Cloud pieces

- **REST API**: the library uses `https://data.hatchbaby.com/`. The Hatch app
  (iOS 6.44) uses `https://prod-sleep.hatchbaby.com/` for the same endpoints.
- **Device state**: an AWS IoT device shadow over MQTT, reached with
  `service/app/restPlus/token/v1/fetch` and Cognito, like the other IoT models.

## Shadow layout

Only the keys `Restore` reads. The device reports many more, such as headphone
pairing, SD card details and memory test results.

| Key | Example | `Restore` attribute | Notes |
|---|---|---|---|
| `connected` | `true` | `is_online` | |
| `rssi` | `-48` | `rssi` | dBm |
| `deviceInfo.f` / `.hwVersion` | `"5.1.376"` / `"5.12.1"` | `firmware_version` / `hardware_version` | |
| `timezone` | `"America/New_York"` | `timezone` | Used for alarm times |
| `content.playing` | `"none"`, `"routine"`, `"remote"` | `current_playing` | |
| `content.step` | `2` | `current_step` | 1-based routine step |
| `content.routineId` | `501` | `routine_id` | The routine the device has loaded |
| `content.requested.alarms.ids` / `.status` | `[1002]` / `"success"` | `requested_alarm_ids` / `requested_alarms_status` | The alarms the device has loaded, see [Alarms](#alarms) |
| `sound.enabled` / `.id` / `.v` | `true` / `10040` / `19660` | `sound_enabled` / `sound_id` / `volume` | `v` is 0–65535 |
| `color.enabled` / `.id` / `.i` | `true` / `229` / `32767` | `color_enabled` / `color_id` / `brightness` | Catalog color ids, not RGB |
| `deviceDefaults.*` | `colorId`, `i`, `soundId`, `v` | `default_*` | |
| `restoreClock.flags` | `32768` | `clock_flags` | bit 15 display on, bit 11 24-hour (the `RIOT_FLAGS_CLOCK_*` bits) |
| `restoreClock.i` | `2621` | `clock_brightness` | |
| `restoreClock.turnOnAt` / `.turnOffAt` | `"07:00:00"` / `"22:00:00"` | `clock_turn_on_at` / `clock_turn_off_at` | |
| `restoreClock.turnOffMode` | `"never"`, `"custom"` | `clock_turn_off_mode` | |
| `alarmsDisabled` | `false` | `alarms_disabled` | |
| `snoozeDuration`, `alarmDuration`, `alarmRampDuration` | `540`, `3600`, `0` | same, snake_case | Seconds |

The `RestoreIot` layout is different (`current.*`, `clock.*`), so the two classes
cannot share a parser.

## Writes

Each row was sent as the desired shadow state in a guided test on a real device,
and the result was observed on the device.

| Control | Desired state | Result |
|---|---|---|
| Start routine at step n | `{"content": {"playing": "routine", "paused": false, "offset": 0, "step": n}}` | ✅ (step 1 and step 2 tried) |
| Stop everything | `{"content": {"playing": "none", "paused": false, "offset": 0, "step": 0}}` | ✅ |
| Light, nothing playing | `{"color": {"enabled": true, "id": 229, "i": 19660}}` | ❌ stored and reported, but no light |
| Light, remote playback | `{"content": {"playing": "remote", "paused": false, "offset": 0, "step": 0}, "color": {...}}` | ✅ |
| Light brightness / color | `{"color": {"i": 45874}}` / `{"color": {"id": 218}}` | ✅ while on |
| Sound, remote playback | `{"content": {...remote}, "sound": {"enabled": true, "id": 10040, "v": 9830}}` | ✅ |
| Volume / sound | `{"sound": {"v": 19660}}` / `{"sound": {"id": 10033}}` | ✅ while playing, also during a routine |
| Light off, sound kept | `{"color": {"enabled": false}}` | ✅ |
| Sound off, light kept | `{"sound": {"enabled": false}}` | ✅ |
| Clock brightness | `{"restoreClock": {"i": 26214}}` | ✅ |
| Clock display off / on | `{"restoreClock": {"flags": flags & ~0x8000}}` / `flags \| 0x8000` | ✅ |
| Clock 24-hour | `{"restoreClock": {"flags": flags \| 0x800}}` | ✅ |
| Clock off at night | `{"restoreClock": {"turnOffMode": "custom", "turnOffAt": "...", "turnOnAt": "..."}}` | ✅ |
| Clock always off | `{"restoreClock": {"turnOffMode": "always"}}` | ❌ stored and reported, but no effect; clear the display flag instead |
| All alarms off / on | `{"alarmsDisabled": true}` / `false` | ✅ the crossed-bell indicator follows |

Behaviour worth knowing:

- **Remote playback.** The light and sound only do anything while something is
  playing. `Restore.turn_light_on()` and `play_sound()` start `"remote"`
  playback when nothing plays.
- **Volume resets.** When playback stops, the device itself writes `sound.v: 0`
  and `color.enabled: false` back into the desired state. `Restore` keeps the
  last non-zero volume in `last_volume` for the next sound.
- **Device-side controls** (the top of the device) start, step and stop the
  routine; the shadow reports it like any other change.

## Routines

`GET service/app/routine/v2/fetch?macAddress=<mac>&types=routine` returns the
device's routines (one bedtime routine on the device tested), with named steps.
In those definitions a step's sound and color ids are offset by 500000 from the
ids the shadow reports (sound `510039` plays as `10039`, color `500208` shows as
`208`). The app reads the same routine with
`GET service/app/routine/routine/v1/fetch/id/<routineId>`, which uses the plain ids.

## Alarms

Alarms are not in the shadow, and none of the endpoints the newer Restores use
return them (`routine/v2` and `routine/v3` with `types=alarm`, or `routine/v3`
with no type: no alarms). This model has its own alarm API, found by recording
the Hatch app.

| Call | Use |
|---|---|
| `GET service/app/alarm/v1/fetch/<mac>` | Every alarm |
| `POST service/app/alarm/v1/create` (one alarm) | Create an alarm; the answer lists the alarms, the new one `"active": false` |
| `POST service/app/alarm/v1/update` (list of alarms) | Replace the list; an alarm sent with `"active": false` is deleted |
| `GET service/app/alarm/v1/fetchDefault` | A template for a new alarm |

An alarm:

```json
{
  "id": 1002,
  "active": true,
  "enabled": true,
  "daysOfWeek": 62,
  "time": "2026-01-05 07:00:00",
  "absoluteTime": 1767614400000,
  "sound": {"id": 10024, "v": 65535},
  "color": {"id": 27, "i": 65535, "duration": 1800, "until": "duration"},
  "colorStartsEarly": true,
  "isExpiredOneOff": false,
  "macAddress": "AA:BB:CC:DD:EE:FF"
}
```

- `active: false` means deleted; `enabled` is the alarm's on/off switch.
- `daysOfWeek` is a bitmask: Sunday 1, Monday 2, Tuesday 4, Wednesday 8,
  Thursday 16, Friday 32, Saturday 64 (62 is Monday to Friday). 0 is a one-time
  alarm.
- `time` is local to the device's `timezone`. For a repeating alarm only the time
  of day matters, and the app keeps the original date when editing.
  `absoluteTime` is the same moment in milliseconds since the epoch.
- `color` is the sunrise: catalog color, brightness, and how long before the
  alarm time it starts (`duration`, seconds) when `colorStartsEarly` is set.
- When sending, the app leaves out `isExpiredOneOff` and adds `"duration": 0,
  "until": "duration"` to `sound`.

**The device loads alarms by id.** Its shadow holds the ids it should load, and
it fetches each alarm's details itself. The app's own logs, which it uploads to
`service/app/restore/v1/logs`, name the steps:

- **Turning an alarm on or off**
  1. Write `{"content": {"requested": {"alarms": {"ids": [<enabled ids>]}}}}` to
     the shadow.
  2. Wait until the device reports the same ids in
     `content.requested.alarms.ids`, with `status: "success"`.
  3. `alarm/v1/update` with the full list, `enabled` changed.
- **Editing an alarm** (time, days, sound…). The id must change, so the device
  loads the new details.
  1. `alarm/v1/create` with the edited alarm; Hatch answers with a copy under a
     new id.
  2. Write the enabled ids to the shadow, with the copy's id in place of the
     original, and wait for the device to confirm.
  3. `alarm/v1/update` with the full list: the original `active: false`, the copy
     `active: true`.

`Restore.set_restore_alarm_enabled()` and `set_restore_alarm_schedule()` follow
these flows. If the device does not confirm within 20 seconds, the previous ids
are written back and nothing is saved (`DeviceSyncError`); a copy that was
already created stays inactive. `create`'s answer can include alarms deleted by
earlier edits, so the copy is picked as the newest alarm that matches what was
sent.

The alarm API is tried on `data.hatchbaby.com` first, falling back to
`prod-sleep.hatchbaby.com` (what the app uses); `Restore.alarm_api_url` records
which one answered.

## Content catalog

The sounds live on the device's SD card (reported as `SDContent`), and the catalog
from `service/app/content/v1/fetchByProduct?product=restore` is a fixed legacy
one. `const.py` lists it:

- `RESTORE_SOUNDS`: the 31 sounds.
- `RESTORE_ALARM_SOUNDS`: 10 alarm-only sounds.
- `RESTORE_COLORS`: 22 colors.
- `RESTORE_SUNRISE_COLORS`: 10 alarm-only sunrise colors.
- `RESTORE_BASIC_COLORS`: a second palette whose names repeat the 22 colors'.

## How this was verified

Two tools in [a fork of ha_hatch](https://github.com/jimbo2412/ha_hatch/tree/main/scripts),
`scripts/probe_restore.py` and `scripts/hatch_capture.py`, documented in its
`scripts/README.md`:

- **The probe** logs in, reads the shadow, and with `--test` steps through every
  write above, asking what the device did.
- **The capture** records the Hatch app's API calls through a local proxy, which
  is how the alarm API was found.

Both redact credentials and identifying values from everything they write.
