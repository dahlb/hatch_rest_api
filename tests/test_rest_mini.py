"""RestMini reads its shadow and builds the expected updates."""

from hatch_rest_api import RestMini, RestMiniAudioTrack
from hatch_rest_api.util import convert_from_percentage

from .device_fakes import listener, recording_device, sent


def test_reads_reported_state() -> None:
    """Shadow fields map onto the device attributes and notify listeners."""
    device = recording_device(RestMini)
    device._update_local_state(
        {
            "connected": True,
            "deviceInfo": {"f": "1.2.3"},
            "current": {
                "playing": "remote",
                "sound": {"id": RestMiniAudioTrack.WhiteNoise.value, "v": 32768},
            },
        }
    )

    assert device.is_online is True
    assert device.firmware_version == "1.2.3"
    assert device.audio_track is RestMiniAudioTrack.WhiteNoise
    assert device.volume == 50
    assert device.is_playing is True
    listener(device).assert_called_once_with()


def test_missing_fields_keep_their_values() -> None:
    """A partial update leaves fields it doesn't mention alone."""
    device = recording_device(RestMini, volume=40, current_playing="remote")
    device._update_local_state({"connected": False})

    assert device.volume == 40
    assert device.is_playing is True
    assert device.is_online is False


def test_not_playing() -> None:
    """is_playing is False when nothing is playing."""
    device = recording_device(RestMini, current_playing="none")
    assert device.is_playing is False


def test_set_volume() -> None:
    """set_volume sends the volume on the device's 16-bit scale."""
    device = recording_device(RestMini)
    device.set_volume(25)
    assert sent(device) == [{"current": {"sound": {"v": convert_from_percentage(25)}}}]


def test_set_audio_track_plays_it() -> None:
    """set_audio_track starts the track indefinitely."""
    device = recording_device(RestMini)
    device.set_audio_track(RestMiniAudioTrack.Heartbeat)
    assert sent(device) == [
        {
            "current": {
                "playing": "remote",
                "step": 1,
                "sound": {"id": RestMiniAudioTrack.Heartbeat.value, "until": "indefinite"},
            }
        }
    ]


def test_set_audio_track_none_stops() -> None:
    """set_audio_track(NONE) stops playback."""
    device = recording_device(RestMini)
    device.set_audio_track(RestMiniAudioTrack.NONE)
    assert sent(device) == [{"current": {"playing": "none", "step": 0}}]
