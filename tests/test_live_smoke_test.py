"""Tests for the live smoke-test command-line helpers."""

import asyncio
from collections.abc import Callable
import io
import json
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

from hatch_rest_api import live_smoke_test
from hatch_rest_api.live_smoke_test import (
    CredentialSource,
    ShadowUpdatePrinter,
    SmokeTestOptions,
    SmokeTestTranscript,
    TeeTextIO,
    load_credentials,
    main,
    maybe_send_sample_control_update,
    parse_args,
    send_sample_control_update,
)

CREDENTIAL_ENV_KEYS = ("HATCH_EMAIL", "HATCH_USERNAME", "HATCH_PASSWORD", "email", "password")


@pytest.fixture(autouse=True)
def clear_credential_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's own credentials out of every test."""
    for key in CREDENTIAL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("HATCH_REST_API_LIVE_SMOKE_CWD", raising=False)


class FakeDevice:
    """Device double with the attributes the smoke test reads."""

    def __init__(
        self,
        device_name: str = "Nursery",
        document_version: int = 3,
        volume: Any = 42,
    ) -> None:
        """Create a device that has already reported state by default."""
        self.device_name = device_name
        self.document_version = document_version
        self.volume = volume
        self.callbacks: set[Callable[[], None]] = set()
        self.volumes_set: list[int] = []
        self.unsubscribed = False

    def __str__(self) -> str:
        """Return a stable state string."""
        return f"{{'device_name': '{self.device_name}', 'volume': {self.volume}}}"

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Record a callback."""
        self.callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Forget a callback."""
        self.callbacks.discard(callback)

    def publish_updates(self) -> None:
        """Run every callback, as a shadow update would."""
        for callback in list(self.callbacks):
            callback()

    def set_volume(self, percentage: int) -> None:
        """Record a volume write."""
        self.volumes_set.append(percentage)

    def unsubscribe(self) -> None:
        """Record that subscriptions were released."""
        self.unsubscribed = True


def test_load_credentials_reads_dotenv_file(tmp_path: Path) -> None:
    """Credentials are read from a dotenv-style file before prompting."""
    credentials_file = tmp_path / "hatch_rest_api.env"
    credentials_file.write_text(
        "# comment\nHATCH_EMAIL=dotenv@example.com\nHATCH_PASSWORD='dotenv password'\n",
        encoding="utf-8",
    )

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials == CredentialSource(
        username="dotenv@example.com",
        password="dotenv password",
        description=str(credentials_file),
    )


def test_load_credentials_prefers_file_over_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit credential files take precedence over process environment."""
    credentials_file = tmp_path / "hatch.toml"
    credentials_file.write_text(
        'email = "file@example.com"\npassword = "file-password"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HATCH_EMAIL", "env@example.com")
    monkeypatch.setenv("HATCH_PASSWORD", "env-password")

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials is not None
    assert credentials.username == "file@example.com"
    assert credentials.password == "file-password"


def test_load_credentials_reads_hatch_toml_section(tmp_path: Path) -> None:
    """TOML files may nest credentials under a ``[hatch]`` table."""
    credentials_file = tmp_path / "hatch.toml"
    credentials_file.write_text(
        '[hatch]\nusername = "section@example.com"\npassword = "section-password"\n',
        encoding="utf-8",
    )

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials is not None
    assert credentials.username == "section@example.com"


def test_load_credentials_reads_json_file(tmp_path: Path) -> None:
    """JSON objects with email/password keys are supported."""
    credentials_file = tmp_path / "hatch.json"
    credentials_file.write_text(
        json.dumps({"email": "json@example.com", "password": "json-password"}),
        encoding="utf-8",
    )

    credentials = load_credentials(SmokeTestOptions(credentials_file=credentials_file))

    assert credentials is not None
    assert credentials.username == "json@example.com"
    assert credentials.password == "json-password"


def test_load_credentials_rejects_json_array(tmp_path: Path) -> None:
    """A JSON credentials file must contain an object."""
    credentials_file = tmp_path / "hatch.json"
    credentials_file.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain an object"):
        load_credentials(SmokeTestOptions(credentials_file=credentials_file))


def test_load_credentials_rejects_incomplete_file(tmp_path: Path) -> None:
    """A credentials file without a password is an error rather than a prompt."""
    credentials_file = tmp_path / "hatch_rest_api.env"
    credentials_file.write_text("HATCH_EMAIL=only@example.com\n", encoding="utf-8")

    with pytest.raises(ValueError, match="both email and password"):
        load_credentials(SmokeTestOptions(credentials_file=credentials_file))


def test_load_credentials_rejects_non_string_values(tmp_path: Path) -> None:
    """Credential values must be strings."""
    credentials_file = tmp_path / "hatch.json"
    credentials_file.write_text(json.dumps({"email": 1, "password": "x"}), encoding="utf-8")

    with pytest.raises(TypeError):
        load_credentials(SmokeTestOptions(credentials_file=credentials_file))


def test_load_credentials_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables are used when no credentials file is given."""
    monkeypatch.setenv("HATCH_EMAIL", "env@example.com")
    monkeypatch.setenv("HATCH_PASSWORD", "env-password")

    credentials = load_credentials(SmokeTestOptions())

    assert credentials == CredentialSource(
        username="env@example.com",
        password="env-password",
        description="environment variables",
    )


def test_load_credentials_returns_none_without_source() -> None:
    """Missing credentials fall back to the interactive prompt."""
    assert load_credentials(SmokeTestOptions()) is None


def test_parse_args_defaults() -> None:
    """Default options run every smoke-test step."""
    assert parse_args([]) == SmokeTestOptions()


def test_parse_args_maps_every_option() -> None:
    """Every command-line option maps onto the smoke-test options."""
    options = parse_args(
        [
            "--credentials-file",
            "/tmp/live_smoke_test.env",
            "--output-file",
            "/tmp/smoke.txt",
            "--read-only",
        ]
    )

    assert options == SmokeTestOptions(
        credentials_file=Path("/tmp/live_smoke_test.env"),
        output_file=Path("/tmp/smoke.txt"),
        read_only=True,
    )


def test_parse_args_resolves_relative_paths_from_launcher_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative paths are resolved against where the launcher was invoked."""
    monkeypatch.setenv("HATCH_REST_API_LIVE_SMOKE_CWD", str(tmp_path))

    options = parse_args(["--credentials-file", "./smoke.env", "--output-file", "smoke.txt"])

    assert options.credentials_file == tmp_path / "smoke.env"
    assert options.output_file == tmp_path / "smoke.txt"


def test_tee_text_io_writes_to_both_streams() -> None:
    """The tee stream mirrors writes to the console and the transcript."""
    console = io.StringIO()
    transcript = io.StringIO()
    tee = TeeTextIO(console, transcript)

    assert tee.write("hello") == 5
    tee.flush()

    assert console.getvalue() == "hello"
    assert transcript.getvalue() == "hello"
    assert tee.isatty() is False


def test_smoke_test_transcript_captures_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Printed output is written to the transcript file."""
    output_file = tmp_path / "nested" / "smoke-output.txt"

    with SmokeTestTranscript(output_file):
        print("captured line")  # noqa: T201

    assert "captured line" in output_file.read_text(encoding="utf-8")
    assert "captured line" in capsys.readouterr().out


def test_smoke_test_transcript_captures_traceback(tmp_path: Path) -> None:
    """Exceptions raised inside the transcript are recorded in it."""
    output_file = tmp_path / "smoke-output.txt"

    with pytest.raises(RuntimeError), SmokeTestTranscript(output_file):
        raise RuntimeError("boom")

    assert "RuntimeError: boom" in output_file.read_text(encoding="utf-8")


async def test_shadow_update_printer_prints_updates_on_loop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Shadow callbacks are marshalled onto the loop and print device state."""
    device = FakeDevice()
    printer = ShadowUpdatePrinter([device], asyncio.get_running_loop())
    printer.attach()

    await asyncio.to_thread(device.publish_updates)
    await asyncio.sleep(0)

    assert "Shadow update at" in capsys.readouterr().out
    printer.detach()
    assert device.callbacks == set()


async def test_shadow_update_printer_waits_for_initial_state() -> None:
    """The initial-state wait finishes once every device reports a shadow."""
    device = FakeDevice(document_version=-1)
    printer = ShadowUpdatePrinter([device], asyncio.get_running_loop())
    printer.attach()
    waiter = asyncio.create_task(printer.wait_for_initial_state(wait_seconds=5))
    await asyncio.sleep(0)
    assert not waiter.done()

    device.document_version = 1
    device.publish_updates()

    assert await waiter is True


async def test_shadow_update_printer_ready_when_state_arrived_before_attach() -> None:
    """Devices that reported before attach do not wait at all."""
    printer = ShadowUpdatePrinter([FakeDevice()], asyncio.get_running_loop())
    printer.attach()

    assert await printer.wait_for_initial_state(wait_seconds=0.01) is True


async def test_shadow_update_printer_initial_state_times_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A device that never reports is named once the wait runs out."""
    printer = ShadowUpdatePrinter(
        [FakeDevice(device_name="Silent", document_version=-1)],
        asyncio.get_running_loop(),
    )
    printer.attach()

    assert await printer.wait_for_initial_state(wait_seconds=0.01) is False
    assert "Silent" in capsys.readouterr().out


async def test_send_sample_control_update_writes_current_volume() -> None:
    """The first device's current volume is written back unchanged."""
    first = FakeDevice(volume=37)
    second = FakeDevice(volume=10)

    assert await send_sample_control_update([first, second]) is True

    assert first.volumes_set == [37]
    assert second.volumes_set == []


async def test_send_sample_control_update_without_devices() -> None:
    """No devices means no control update."""
    assert await send_sample_control_update([]) is False


@pytest.mark.parametrize(
    "device",
    [
        FakeDevice(document_version=-1),
        FakeDevice(volume=None),
        FakeDevice(volume=True),
    ],
)
async def test_send_sample_control_update_skips_unknown_volume(device: FakeDevice) -> None:
    """Class-default or missing volumes are never written to a device."""
    assert await send_sample_control_update([device]) is False
    assert device.volumes_set == []


async def test_maybe_send_sample_control_update_respects_read_only() -> None:
    """Read-only mode never writes to a device."""
    device = FakeDevice()

    assert await maybe_send_sample_control_update([device], read_only=True) is False
    assert device.volumes_set == []


class FakeClientSession:
    """aiohttp session double that records closing."""

    instances: ClassVar[list[FakeClientSession]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Track every created session."""
        self.closed = False
        FakeClientSession.instances.append(self)

    async def close(self) -> None:
        """Record that the session was closed."""
        self.closed = True


def fake_mqtt_connection() -> MagicMock:
    """Return an MQTT connection double whose disconnect resolves immediately."""
    connection = MagicMock()
    connection.disconnect.return_value.result.return_value = None
    return connection


async def test_main_runs_full_flow_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The smoke test loads devices, writes volume, waits, and tears everything down."""
    device = FakeDevice()
    connection = fake_mqtt_connection()
    calls: dict[str, Any] = {}

    async def fake_get_rest_devices(email: str, password: str, **kwargs: Any) -> Any:
        calls["email"] = email
        calls["password"] = password
        calls["client_session"] = kwargs["client_session"]
        return MagicMock(), connection, [device], "2026-01-01T00:00:00Z"

    async def fake_sleep(seconds: float) -> None:
        calls["slept"] = seconds

    FakeClientSession.instances = []
    monkeypatch.setenv("HATCH_EMAIL", "env@example.com")
    monkeypatch.setenv("HATCH_PASSWORD", "env-password")
    monkeypatch.setattr(live_smoke_test, "ClientSession", FakeClientSession)
    monkeypatch.setattr(live_smoke_test, "get_rest_devices", fake_get_rest_devices)
    monkeypatch.setattr(live_smoke_test, "sleep", fake_sleep)

    await main(SmokeTestOptions())

    output = capsys.readouterr().out
    assert calls["email"] == "env@example.com"
    assert calls["password"] == "env-password"
    assert calls["client_session"] is FakeClientSession.instances[0]
    assert calls["slept"] == live_smoke_test.SMOKE_TEST_WAIT_SECONDS
    assert device.volumes_set == [42]
    assert device.unsubscribed is True
    assert device.callbacks == set()
    connection.disconnect.assert_called_once()
    assert FakeClientSession.instances[0].closed is True
    assert "Smoke test complete" in output


async def test_main_cleans_up_when_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Teardown still runs when the wait is interrupted."""
    device = FakeDevice()
    connection = fake_mqtt_connection()

    async def fake_get_rest_devices(email: str, password: str, **kwargs: Any) -> Any:
        return MagicMock(), connection, [device], "2026-01-01T00:00:00Z"

    async def interrupted_sleep(seconds: float) -> None:
        raise KeyboardInterrupt

    FakeClientSession.instances = []
    monkeypatch.setenv("HATCH_EMAIL", "env@example.com")
    monkeypatch.setenv("HATCH_PASSWORD", "env-password")
    monkeypatch.setattr(live_smoke_test, "ClientSession", FakeClientSession)
    monkeypatch.setattr(live_smoke_test, "get_rest_devices", fake_get_rest_devices)
    monkeypatch.setattr(live_smoke_test, "sleep", interrupted_sleep)

    with pytest.raises(KeyboardInterrupt):
        await main(SmokeTestOptions(read_only=True))

    assert device.volumes_set == []
    assert device.unsubscribed is True
    connection.disconnect.assert_called_once()
    assert FakeClientSession.instances[0].closed is True


async def test_main_prompts_and_closes_session_when_login_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interactive credentials are used and the session is closed on failure."""

    async def fake_read_input(prompt: str) -> str:
        return "typed@example.com"

    async def fake_read_password() -> str:
        return "typed-password"

    async def failing_get_rest_devices(email: str, password: str, **kwargs: Any) -> Any:
        assert email == "typed@example.com"
        assert password == "typed-password"
        raise RuntimeError("login failed")

    FakeClientSession.instances = []
    monkeypatch.setattr(live_smoke_test, "read_input", fake_read_input)
    monkeypatch.setattr(live_smoke_test, "read_password", fake_read_password)
    monkeypatch.setattr(live_smoke_test, "ClientSession", FakeClientSession)
    monkeypatch.setattr(live_smoke_test, "get_rest_devices", failing_get_rest_devices)

    with pytest.raises(RuntimeError, match="login failed"):
        await main(SmokeTestOptions())

    assert FakeClientSession.instances[0].closed is True
