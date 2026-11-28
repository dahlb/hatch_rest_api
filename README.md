[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

An async Python client for Hatch sleep devices: the Rest and Restore families. It logs in
to the Hatch cloud API over HTTP (`aiohttp`), then talks to each device through its AWS IoT
device shadow over MQTT (`awsiotsdk`). It follows
[Home Assistant's guide to API libraries](https://developers.home-assistant.io/docs/api_lib_index)
and is the library behind the [ha_hatch](https://github.com/dahlb/ha_hatch) integration.

Much of the protocol knowledge is ported from
[homebridge-hatch-baby-rest](https://github.com/dgreif/homebridge-hatch-baby-rest).

## Supported Devices

`get_rest_devices()` returns one object per device on the account, picked by the device's
Hatch `product`:

| Device | `product` | Class | Highlights |
|---|---|---|---|
| Rest Mini | `restMini` | `RestMini` | sound track and volume |
| Rest+ | `restPlus` | `RestPlus` | sound, volume, power, light color |
| Rest 2nd gen / Rest+ 2nd gen | `riot`, `riotPlus` | `RestIot` | sound, light, clock, toddler lock, favorites |
| Rest Baby | `restBaby` | `RestBaby` | sound, light, clock, toddler lock, favorites |
| Restore (1st gen, original) | `restore` | `Restore` | routines, light, sound, clock, alarms; see [docs/restore.md](docs/restore.md) |
| Restore (1st gen) | `restoreIot` | `RestoreIot` | light, clock, favorites, alarms |
| Restore (V4) | `restoreV4` | `RestoreV4` | same as `RestoreV5` |
| Restore 3 | `restoreV5` | `RestoreV5` | light, sound, clock schedule and tap-to-show, favorites, alarms |

`RestDevice` is the union of these classes. An unrecognised `product` falls back to
`RestMini`.

## Installation

```bash
pip install hatch-rest-api
```

Requires Python 3.14.

## Basic Usage

```python
import asyncio

from aiohttp import ClientSession

from hatch_rest_api import RestIot, get_rest_devices


async def main() -> None:
    async with ClientSession() as session:
        api, mqtt_connection, devices, expiration = await get_rest_devices(
            email="you@example.com",
            password="your-password",
            client_session=session,
        )
        try:
            for device in devices:
                print(repr(device))  # <RestIot device_name='Nursery' thing_name='...'>
                print(device.as_dict())  # the device's current state as a dict

                # Called after every state update reported by the device.
                device.register_callback(lambda: print("updated"))

                if isinstance(device, RestIot):
                    # Sends the command without blocking the event loop.
                    await device.async_command(device.set_volume, 30)
        finally:
            for device in devices:
                await device.async_unsubscribe()
            await asyncio.to_thread(lambda: mqtt_connection.disconnect().result())


asyncio.run(main())
```

`get_rest_devices()` returns:

- `api`: the `Hatch` HTTP client, for favorites, routines and alarm requests.
- `mqtt_connection`: the shared AWS IoT connection. Disconnect it when you are done.
- `devices`: one `RestDevice` per supported device.
- `expiration`: when the AWS credentials expire, as a Unix timestamp. Call
  `get_rest_devices()` again before then to get a fresh connection and new device objects.

### Reading state

Each device mirrors its AWS IoT shadow. State such as `is_on`, `volume`, `audio_track`,
`is_light_on` or `is_clock_on` (which fields exist depends on the class) updates as the
device reports changes. `register_callback()` runs a callback after each update, and
`remove_callback()` removes it. `as_dict()` returns the whole state as a dict, which is
useful for diagnostics; `str(device)` prints the same.

### Sending commands

Commands such as `set_volume()`, `set_color()`, `set_audio_track()`, `set_clock()` and
`set_favorite()` publish a desired-state update to the device's shadow. Called directly
they are synchronous and block for up to 10 seconds while MQTT acknowledges the publish.

In async code, run any command with `async_command()` instead. It runs the command's
logic, then publishes its updates and awaits the acknowledgements without blocking the
event loop or using a thread:

```python
await device.async_command(device.set_color, 255, 0, 0, brightness=50)
await device.async_command(device.set_favorite, "Bedtime-101")
```

The arguments are type-checked against the command. `async_refresh()` and
`async_unsubscribe()` are the async forms of `refresh()` and `unsubscribe()`. The new state
arrives back through the shadow and triggers your callbacks.

Alarm methods, such as `refresh_alarms()` and `set_alarm_enabled()`, go through the Hatch
HTTP API and are `async`.

## Errors

The library's own errors subclass `BaseError`:

| Error | Raised when |
|---|---|
| `AuthError` | Hatch reports the session is invalid (error code `1001`). Log in again. |
| `RateError` | Hatch answers HTTP 429. Back off before retrying. `Hatch.content()` retries with exponential backoff on its own; other calls raise straight away. |
| `DeviceSyncError` | A device does not confirm a change it had to apply over MQTT (original Restore alarms). |
| `BaseError` | The account has no supported devices. |

Other failures from the Hatch HTTP API, such as an error response or a body that isn't
JSON, raise `aiohttp.ClientError`. MQTT failures raise the AWS IoT SDK's own exceptions.

## Development

```bash
scripts/setup   # creates .venv with Python 3.14 and installs prek hooks
scripts/lint    # prek (ruff, codespell, actionlint, file checks) and mypy --strict
scripts/test    # pytest with coverage
```

The test suite needs no network access. See [AGENTS.md](AGENTS.md) for the codebase
layout and conventions, and [RELEASE.md](RELEASE.md) for how releases are cut from
Conventional Commit messages.

## Live Smoke Test

The live smoke test connects to a real Hatch account, discovers its devices,
connects them to AWS IoT, prints their shadow state, listens for real-time
shadow updates, and sends one sample control update to the first device.

```bash
scripts/live_smoke_test
```

Use it only when you want to exercise the live Hatch APIs. The sample control
update writes the first device's current volume back to it, so the setting is
unchanged but the control path and shadow update are exercised. The script then
waits 5 minutes so MQTT messages can be observed.

To run non-interactively, put credentials in a local `env` file and pass it
with `--credentials-file`. Supported keys are `HATCH_EMAIL`/`HATCH_PASSWORD`
(see `scripts/hatch_rest_api.env.example`); TOML and JSON files with
`email`/`password` keys also work, as do `HATCH_EMAIL`/`HATCH_PASSWORD`
environment variables.

```bash
scripts/live_smoke_test --credentials-file scripts/hatch_rest_api.env --output-file /private/tmp/hatch_rest_api.txt --read-only
```

Other options:

- `--output-file` writes a full transcript (stdout, stderr, and logs) for later
  API debugging or fixture updates.
- `--read-only` skips the sample control update while still loading devices and
  listening for MQTT messages.

***

[hatch_rest_api]: https://github.com/dahlb/hatch_rest_api
[commits-shield]: https://img.shields.io/github/commit-activity/y/dahlb/hatch_rest_api.svg?style=for-the-badge
[commits]: https://github.com/dahlb/hatch_rest_api/commits/main
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/dahlb/hatch_rest_api.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Bren%20Dahl%20%40dahlb-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/dahlb/hatch_rest_api.svg?style=for-the-badge
[releases]: https://github.com/dahlb/hatch_rest_api/releases
[buymecoffee]: https://www.buymeacoffee.com/dahlb
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge


