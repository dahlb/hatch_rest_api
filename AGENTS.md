# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

`hatch_rest_api` is an async Python client for Hatch sleep devices (the Rest and Restore
families). It logs in to
the Hatch cloud API over HTTP (`aiohttp`), then talks to each device through its AWS IoT
device shadow over MQTT (`awsiotsdk` / `awscrt`). It is published to PyPI and is the
library behind a Home Assistant integration, so keep the public API stable.

Much of the protocol knowledge is ported from
[homebridge-hatch-baby-rest](https://github.com/dgreif/homebridge-hatch-baby-rest).

## Layout

```
src/hatch_rest_api/
  __init__.py                 Public exports (__all__) and the RestDevice union type
  hatch.py                    Hatch HTTP API client (login, devices, favorites, routines, content)
  aws_http.py                 Fetches AWS Cognito credentials for the MQTT connection
  contentful.py               Contentful GraphQL client (Restore sound catalog)
  util_bootstrap.py           get_rest_devices(): login -> discover -> MQTT connect -> device objects
  shadow_client_subscriber.py ShadowClientSubscriberMixin: base for all devices, syncs the shadow
  callbacks.py                CallbacksMixin: state-change callback registration
  scheduled_routine.py        Alarm (scheduled routine) helpers and ScheduledRoutineAlarmMixin
  rest_mini.py, rest_plus.py, rest_iot.py, rest_baby.py,
  restore.py, restore_iot.py, restore_v4.py, restore_v5.py   One class per device family
  const.py                    VERSION, audio track enums, color/sound sentinel IDs, product constants
  errors.py                   BaseError, AuthError, RateError, DeviceSyncError
  util.py, util_http.py       Value conversion, safe JSON access, request logging/redaction
  live_smoke_test.py          Interactive script that hits the real Hatch APIs (not unit-tested)
tests/                        pytest suite (no network access)
scripts/                      setup, lint, test, live_smoke_test helpers
```

### How devices work

- `Hatch.iot_devices()` filters the account's devices to supported `product` strings, and
  `get_rest_devices()` in `util_bootstrap.py` maps each one to a device class (`restPlus`,
  `riot`/`riotPlus`, `restBaby`, `restore`, `restoreIot`, `restoreV4`, `restoreV5`; anything else
  falls through to `RestMini`). Adding a device type means updating both places, plus an
  export in `__init__.py` and the `RestDevice` union.
- Every device class subclasses `ShadowClientSubscriberMixin`. Subclasses implement
  `_update_local_state(state)` to map the reported shadow onto attributes, and call
  `self._update({...})` to send a desired-state change; the device's reported state then
  arrives back through the shadow subscription and `_update_local_state`.
- Devices with alarms also mix in `ScheduledRoutineAlarmMixin`.
- Blocking MQTT/SDK futures are bounded by `MQTT_TIMEOUT`; blocking `awscrt` calls in async
  code go through `loop.run_in_executor` (see `util_bootstrap.py`).

## Environment and commands

Python 3.14 is used for development and CI (`requires-python >= 3.12`).

```bash
scripts/setup      # creates .venv with python3.14, installs `--group dev -e .`, installs prek hooks
scripts/lint       # .venv/bin/prek run -a  (ruff check --fix, ruff format, codespell, actionlint, yaml/toml/json checks)
scripts/test       # .venv/bin/python -m pytest  (extra args are passed through)
```

Without the scripts: `pip install --group dev -e .`, then `prek run -a` and `pytest`.

Run lint and tests before finishing any change. CI runs both on every PR.

## Code style

- Ruff with `select = ["ALL"]`, line length 100, double quotes, Google-style docstrings.
  Check `[tool.ruff.lint]` in `pyproject.toml` for the ignore list rather than adding
  `# noqa` comments; if a new ignore is truly needed, prefer a per-file ignore with a reason.
- Every module, class, and public function has a docstring; type-annotate everything.
- Use module-level `_LOGGER = logging.getLogger(__name__)` and `%`-style log arguments.
- Never log credentials, tokens, or emails unredacted; use
  `util.clean_dictionary_for_logging` for request/response payloads.
- Raise `AuthError` / `RateError` / `BaseError` from `errors.py` for API failures.

## Testing

- Tests live in `tests/` and must not touch the network or real Hatch accounts.
- Build device objects with `Cls.__new__(Cls)` and replace `_update` with a recorder
  (see `tests/test_rest_iot_light_and_sound.py`) to assert on outgoing shadow payloads.
- `asyncio_mode = "auto"` and a 20s per-test timeout are configured.
- Coverage is reported on PRs (green at 90%); add tests for new behavior.
- `scripts/live_smoke_test` exercises the real APIs and writes to a real device. Only run
  it when the user explicitly asks and provides credentials. Prefer `--read-only`. Never
  commit `scripts/hatch_rest_api.env` or transcript output.

## Commits, PRs, and releases

- Commit messages and PR titles **must** use Conventional / semantic commit format
  (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:` ...). The PR title is
  linted, and releases are cut from these messages.
- Do not edit `VERSION` in `src/hatch_rest_api/const.py` (`pyproject.toml` reads it as a
  dynamic version); the release workflow bumps it, tags, creates
  the GitHub release, and publishes to PyPI on every push to `main`.
- Dependency bumps come from Dependabot (ruff bumps auto-merge) and hook revisions in
  `prek.toml` from `prek_autoupdate.yml`; don't hand-edit either unless that is the task.
