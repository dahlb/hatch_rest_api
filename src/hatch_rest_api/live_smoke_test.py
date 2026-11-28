"""Manual live Hatch API smoke-test script for local development.

This module is an interactive development harness, not part of the automated
pytest suite. It connects to the real Hatch APIs with credentials entered at
the terminal (or loaded from a credentials file or environment variables),
discovers the account's devices, connects them to AWS IoT, prints their current
shadow state, listens for real-time shadow updates, and sends one sample control
update to the first device.

Use this when developing or debugging behavior that needs a live Hatch account,
such as captured shadow payloads, favorites/routines/sound discovery, control
writes, or MQTT connection issues that are hard to represent from stored
fixtures alone. Do not use it as a substitute for adding deterministic tests in
``tests/``; any fixed behavior should still be covered by pytest fixtures or
unit tests where practical.

The script intentionally prints raw inspected state to the console and mutates
``sys.path`` so it can be run directly from a source checkout without installing
the package first. Unless ``--read-only`` is given it writes the first device's
current volume back to it, which exercises the control path and triggers a
shadow update without changing the device's settings.

Run it through the repository helper script so it starts from the project root
and uses the repository virtual environment:
``scripts/live_smoke_test``.
"""

from argparse import ArgumentParser, Namespace
import asyncio
from asyncio import AbstractEventLoop, sleep
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
import json
import logging
import os
from pathlib import Path
import sys
import tomllib
import traceback as traceback_module
from types import TracebackType
from typing import Any, TextIO

from aiohttp import ClientSession

path_src = Path(__file__).parents[1]
sys.path.append(str(path_src))

from hatch_rest_api.util_bootstrap import RestDevice, get_rest_devices

logger = logging.getLogger("hatch_rest_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

SMOKE_TEST_WAIT_SECONDS = 300
INITIAL_STATE_WAIT_SECONDS = 15
USERNAME_KEYS = ("HATCH_EMAIL", "HATCH_USERNAME", "email", "username")
PASSWORD_KEYS = ("HATCH_PASSWORD", "password")

INTRO_TEXT = """\
This smoke test connects to the live Hatch APIs.
It discovers your devices, connects them to AWS IoT, prints their current
state, listens for real-time shadow updates, sends one sample control update to
the first device, and then waits so incoming realtime messages can be observed.

Unless ``--read-only`` is provided, this script writes the first device's
current volume back to it. The value is unchanged, but the write goes through
the live AWS IoT shadow and should produce a shadow update. After that, it
waits 5 minutes, so the terminal will appear to pause while it listens for
MQTT messages.

Enter the Hatch account email address and password that you use for the
official Hatch app. These credentials are read from this terminal session
only; the script does not store them.
"""


@dataclass(frozen=True)
class CredentialSource:
    """Hatch credentials loaded from a non-interactive source.

    Args:
        username: Hatch account email address.
        password: Hatch account password.
        description: Human-readable source description for console output.
    """

    username: str
    password: str
    description: str


@dataclass(frozen=True)
class SmokeTestOptions:
    """Parsed smoke-test command-line options.

    Args:
        credentials_file: Optional file to read Hatch credentials from.
        output_file: Optional file to write a full smoke-test transcript to.
        read_only: Whether to skip the sample device control update.
    """

    credentials_file: Path | None = None
    output_file: Path | None = None
    read_only: bool = False


class TeeTextIO:
    """Text stream that writes to a console stream and a transcript file."""

    def __init__(self, console: TextIO, transcript: TextIO) -> None:
        """Initialize the tee stream.

        Args:
            console: Original console stream.
            transcript: Output transcript stream.
        """
        self._console = console
        self._transcript = transcript
        self.encoding = getattr(console, "encoding", None)

    def write(self, text: str) -> int:
        """Write text to both wrapped streams.

        Args:
            text: Text to write.

        Returns:
            The number of characters accepted by the console stream.
        """
        written = self._console.write(text)
        self._transcript.write(text)
        return written

    def flush(self) -> None:
        """Flush both wrapped streams."""
        self._console.flush()
        self._transcript.flush()

    def isatty(self) -> bool:
        """Return whether the console stream is attached to a terminal.

        Returns:
            True when the original console stream is a TTY.
        """
        return self._console.isatty()


class SmokeTestTranscript:
    """Context manager that tees console and log output to a file."""

    def __init__(self, output_file: Path) -> None:
        """Initialize transcript capture.

        Args:
            output_file: File that should receive the captured transcript.
        """
        self._output_file = output_file
        self._transcript: TextIO | None = None
        self._stdout: TextIO | None = None
        self._stderr: TextIO | None = None
        self._original_handler_streams: list[tuple[logging.StreamHandler[TextIO], TextIO]] = []

    def __enter__(self) -> None:
        """Start teeing stdout, stderr, and logger streams."""
        self._output_file.parent.mkdir(parents=True, exist_ok=True)
        self._transcript = self._output_file.open("w", encoding="utf-8")
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = TeeTextIO(sys.stdout, self._transcript)
        sys.stderr = TeeTextIO(sys.stderr, self._transcript)
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self._original_handler_streams.append((handler, handler.stream))
                handler.setStream(sys.stderr)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop teeing output and close the transcript file.

        Args:
            exc_type: Exception type raised inside the context, if any.
            exc_value: Exception raised inside the context, if any.
            traceback: Traceback raised inside the context, if any.
        """
        for handler, stream in self._original_handler_streams:
            handler.setStream(stream)
        if self._stdout is not None:
            sys.stdout = self._stdout
        if self._stderr is not None:
            sys.stderr = self._stderr
        if exc_type is not None and self._transcript is not None:
            traceback_module.print_exception(
                exc_type,
                exc_value,
                traceback,
                file=self._transcript,
            )
        if self._transcript is not None:
            self._transcript.close()


def parse_args(argv: list[str] | None = None) -> SmokeTestOptions:
    """Parse command-line arguments for the live smoke test.

    Args:
        argv: Optional argument list. Uses process arguments when omitted.

    Returns:
        Parsed smoke-test options.
    """
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials-file",
        type=Path,
        help=(
            "Read credentials from a .env, TOML, or JSON file. Supported keys "
            "include HATCH_EMAIL/HATCH_PASSWORD and email/password."
        ),
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Write stdout, stderr, and smoke-test logs to this transcript file.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Skip the sample device control update while leaving other smoke-test steps enabled.",
    )
    namespace: Namespace = parser.parse_args(argv)
    return SmokeTestOptions(
        credentials_file=resolve_invocation_path(namespace.credentials_file),
        output_file=resolve_invocation_path(namespace.output_file),
        read_only=namespace.read_only,
    )


def resolve_invocation_path(path: Path | None) -> Path | None:
    """Resolve a command-line path relative to the launcher invocation directory.

    Args:
        path: Optional path from a command-line argument.

    Returns:
        Absolute path when a relative path was supplied through the launcher.
    """
    if path is None or path.is_absolute():
        return path
    invocation_cwd = os.environ.get("HATCH_REST_API_LIVE_SMOKE_CWD")
    if invocation_cwd is None:
        return path
    return Path(invocation_cwd) / path


def strip_env_value(value: str) -> str:
    """Normalize a dotenv value by trimming whitespace and quotes.

    Args:
        value: Raw value read from a dotenv line.

    Returns:
        Normalized dotenv value.
    """
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def read_dotenv_credentials(credentials_file: Path) -> dict[str, str]:
    """Read key-value credentials from a dotenv-style file.

    Args:
        credentials_file: File containing one ``KEY=value`` entry per line.

    Returns:
        Parsed dotenv key-value mapping.
    """
    credentials: dict[str, str] = {}
    for line in credentials_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        credentials[key.strip()] = strip_env_value(value)
    return credentials


def read_credentials_file(credentials_file: Path) -> dict[str, Any]:
    """Read Hatch credentials from a supported config file format.

    Args:
        credentials_file: .env, TOML, or JSON credential file.

    Returns:
        Parsed credential mapping.
    """
    if credentials_file.suffix == ".json":
        with credentials_file.open(encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items()}
        raise ValueError("JSON credentials file must contain an object")
    if credentials_file.suffix == ".toml":
        with credentials_file.open("rb") as file:
            data = tomllib.load(file)
        hatch_data = data.get("hatch")
        if isinstance(hatch_data, dict):
            return {str(key): value for key, value in hatch_data.items()}
        return {str(key): value for key, value in data.items()}
    return read_dotenv_credentials(credentials_file)


def find_first_value(credentials: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    """Find the first non-empty credential value among supported keys.

    Args:
        credentials: Credential mapping to inspect.
        keys: Ordered candidate key names.

    Returns:
        First matching non-empty value, or None.
    """
    for key in keys:
        value = credentials.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise TypeError("Credential values must be strings")
        if value:
            return value
    return None


def credential_source_from_mapping(
    credentials: Mapping[str, Any],
    description: str,
) -> CredentialSource | None:
    """Build a credential source from a mapping when both values are present.

    Args:
        credentials: Mapping that may contain username and password values.
        description: Source description for console output.

    Returns:
        Credential source when both username and password are present.
    """
    username = find_first_value(credentials, USERNAME_KEYS)
    password = find_first_value(credentials, PASSWORD_KEYS)
    if username is None or password is None:
        return None
    return CredentialSource(username=username, password=password, description=description)


def load_credentials(options: SmokeTestOptions) -> CredentialSource | None:
    """Load Hatch credentials from file or environment when available.

    Args:
        options: Smoke-test command-line options.

    Returns:
        Non-interactive credential source when both credentials are found.
    """
    if options.credentials_file is not None:
        credentials = read_credentials_file(options.credentials_file)
        credential_source = credential_source_from_mapping(
            credentials,
            str(options.credentials_file),
        )
        if credential_source is None:
            raise ValueError("Credentials file must include both email and password")
        return credential_source
    return credential_source_from_mapping(os.environ, "environment variables")


@contextmanager
def capture_output(output_file: Path | None) -> Iterator[None]:
    """Optionally tee smoke-test output to a transcript file.

    Args:
        output_file: Transcript file path, if capture is requested.

    Yields:
        Control while output capture is active.
    """
    if output_file is None:
        yield
        return
    with SmokeTestTranscript(output_file):
        yield


async def read_input(prompt: str) -> str:
    """Read terminal input without blocking the event loop.

    Args:
        prompt: Prompt to display to the user.

    Returns:
        The entered input text.
    """
    return await asyncio.to_thread(input, prompt)


async def read_password() -> str:
    """Read a password without blocking the event loop.

    Returns:
        The password entered by the user.
    """
    return await asyncio.to_thread(getpass)


def current_timestamp() -> str:
    """Return the current local date and time for console output.

    Returns:
        Local timestamp formatted for human-readable smoke-test logs.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def device_state(device: RestDevice) -> str:
    """Return a device's type and current state for console output.

    Args:
        device: Loaded Hatch device.

    Returns:
        Device class name followed by the state its ``__str__`` reports.
    """
    return f"{type(device).__name__} {device}"


def print_devices(label: str, devices: Sequence[RestDevice]) -> None:
    """Print the current in-memory state of every loaded device.

    Args:
        label: Heading that identifies why the devices are being printed.
        devices: Loaded Hatch devices.
    """
    print(f"{label}: {[device_state(device) for device in devices]}")


def has_reported_state(device: RestDevice) -> bool:
    """Return whether a device has applied at least one shadow document.

    Args:
        device: Loaded Hatch device.

    Returns:
        True once a shadow ``get`` or ``update`` response has been applied.
    """
    return device.document_version >= 0


class ShadowUpdatePrinter:
    """Print a device's state whenever its shadow publishes an update.

    awscrt invokes shadow callbacks on its own event loop thread. Each callback
    is handed to the asyncio event loop with ``call_soon_threadsafe`` so device
    state is only read from the loop thread, matching how library consumers
    use it.
    """

    def __init__(self, devices: Sequence[RestDevice], loop: AbstractEventLoop) -> None:
        """Initialize the printer.

        Args:
            devices: Loaded Hatch devices whose updates should be printed.
            loop: Event loop that should print incoming updates.
        """
        self._devices = list(devices)
        self._loop = loop
        self._callbacks: list[tuple[RestDevice, Callable[[], None]]] = []
        self._initial_state = asyncio.Event()

    def attach(self) -> None:
        """Register a thread-safe update callback on every device."""
        for device in self._devices:

            def callback(device: RestDevice = device) -> None:
                self._loop.call_soon_threadsafe(self.handle_update, device)

            device.register_callback(callback)
            self._callbacks.append((device, callback))
        # Shadow responses may already have arrived while devices were created.
        self._check_initial_state()

    def detach(self) -> None:
        """Remove every callback registered by :meth:`attach`."""
        while self._callbacks:
            device, callback = self._callbacks.pop()
            device.remove_callback(callback)

    def handle_update(self, device: RestDevice) -> None:
        """Print a device's state after a shadow update.

        Args:
            device: Device whose shadow published an update.
        """
        print(f"Shadow update at {current_timestamp()}: {device_state(device)}")
        self._check_initial_state()

    def _check_initial_state(self) -> None:
        if all(has_reported_state(device) for device in self._devices):
            self._initial_state.set()

    async def wait_for_initial_state(
        self, wait_seconds: float = INITIAL_STATE_WAIT_SECONDS
    ) -> bool:
        """Wait until every device has applied its first shadow document.

        Each device requests its shadow when it is created, but the response
        arrives asynchronously over MQTT, so attributes such as ``volume`` still
        hold class defaults until it does.

        Args:
            wait_seconds: Maximum seconds to wait.

        Returns:
            True when every device reported state before the wait ran out.
        """
        try:
            async with asyncio.timeout(wait_seconds):
                await self._initial_state.wait()
        except TimeoutError:
            missing = [
                device.device_name for device in self._devices if not has_reported_state(device)
            ]
            print(f"No shadow state received within {wait_seconds} seconds for: {missing}")
            return False
        return True


async def send_sample_control_update(devices: Sequence[RestDevice]) -> bool:
    """Write the first device's current volume back to it.

    Args:
        devices: Loaded Hatch devices.

    Returns:
        True when the update was sent, otherwise False when there is no device
        or the device has not reported a volume value.
    """
    if not devices:
        print("No devices available; skipping sample control update.")
        return False
    device = devices[0]
    volume = getattr(device, "volume", None)
    if not has_reported_state(device) or not isinstance(volume, int) or isinstance(volume, bool):
        print(f"{device.device_name} does not report volume; skipping sample control update.")
        return False
    print(f"Writing current volume {volume} back to {device.device_name}.")
    # Shadow publishes block on the MQTT acknowledgement.
    await asyncio.to_thread(device.set_volume, volume)
    return True


async def maybe_send_sample_control_update(
    devices: Sequence[RestDevice],
    *,
    read_only: bool,
) -> bool:
    """Send the sample control update unless the smoke test is in read-only mode.

    Args:
        devices: Loaded Hatch devices.
        read_only: Whether to skip mutation calls.

    Returns:
        True when the update is sent successfully, otherwise False.
    """
    if read_only:
        print("Read-only mode enabled; skipping sample control update.")
        return False
    return await send_sample_control_update(devices)


async def disconnect_mqtt(mqtt_connection: Any) -> None:
    """Disconnect the AWS IoT MQTT connection and wait for it to close.

    Args:
        mqtt_connection: Connection returned by ``get_rest_devices``.
    """
    disconnect_future = await asyncio.to_thread(mqtt_connection.disconnect)
    await asyncio.to_thread(disconnect_future.result)


async def unsubscribe_devices(devices: Sequence[RestDevice]) -> None:
    """Release every device's shadow subscriptions.

    Args:
        devices: Loaded Hatch devices.
    """
    for device in devices:
        # Unsubscribing blocks on the MQTT acknowledgement.
        await asyncio.to_thread(device.unsubscribe)


async def main(options: SmokeTestOptions) -> None:
    """Log in, load devices, print shadow updates, and send one sample update.

    Args:
        options: Parsed smoke-test command-line options.
    """
    print(INTRO_TEXT)
    print()
    credentials = load_credentials(options)
    if credentials is None:
        username = await read_input("Hatch account email address: ")
        password = await read_password()
    else:
        username = credentials.username
        password = credentials.password
        print(f"Using Hatch credentials from {credentials.description}.")
    client_session: ClientSession | None = None
    mqtt_connection: Any = None
    devices: list[RestDevice] = []
    printer: ShadowUpdatePrinter | None = None
    completed = False
    print()
    print(f"Starting Smoke Test at {current_timestamp()}")
    print("--------------------------------------------------------------------------")
    print()
    try:
        client_session = ClientSession()
        _, mqtt_connection, devices, expiration = await get_rest_devices(
            username,
            password,
            client_session=client_session,
        )
        print(f"AWS IoT credentials expire at {expiration}")
        printer = ShadowUpdatePrinter(devices, asyncio.get_running_loop())
        printer.attach()
        await printer.wait_for_initial_state()
        print_devices("Devices", devices)

        await maybe_send_sample_control_update(devices, read_only=options.read_only)

        print()
        print("--------------------------------------------------------------------------")
        print("The script will now wait 5 minutes, so MQTT messages can be observed")
        print("--------------------------------------------------------------------------")
        print()
        await sleep(SMOKE_TEST_WAIT_SECONDS)
        completed = True
    finally:
        if printer is not None:
            printer.detach()
        await unsubscribe_devices(devices)
        if mqtt_connection is not None:
            await disconnect_mqtt(mqtt_connection)
        if client_session is not None:
            await client_session.close()
        if completed:
            print()
            print("--------------------------------------------------------------------------")
            print(f"Smoke test complete at {current_timestamp()}")


if __name__ == "__main__":
    smoke_test_options = parse_args()
    with capture_output(smoke_test_options.output_file):
        asyncio.run(main(smoke_test_options))
