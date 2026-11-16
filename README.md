[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

Api Wrapper for Hatch Rest mini API using async in python, this was inspired by [this guide](https://developers.home-assistant.io/docs/api_lib_index) to be a lightweight wrapper, with simple error handling.

a lot of this is a port of [homebridge-hatch-baby-rest](https://github.com/dgreif/homebridge-hatch-baby-rest) from node.

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


