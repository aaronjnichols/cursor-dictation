from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from cursor_dictation.audio.recorder import (
    AudioCaptureError,
    AudioDeviceError,
    RecorderNotRunningError,
    RecordingCompletionReason,
)
from cursor_dictation.audio.sounddevice_recorder import SoundDeviceRecorder


class FakeCallbackStop(Exception):
    pass


class FakeCallbackAbort(Exception):
    pass


class FakeInputOutputPair:
    def __init__(self, input_index: int, output_index: int) -> None:
        self._values = (input_index, output_index)

    def __getitem__(self, index: int) -> int:
        return self._values[index]


class FakeStream:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.stopped = False
        self.closed = False
        self.stop_error: Exception | None = None
        self.start_error: Exception | None = None
        self.active = False

    def start(self) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.active = True

    def stop(self) -> None:
        self.stopped = True
        was_active = self.active
        self.active = False
        try:
            if self.stop_error is not None:
                raise self.stop_error
        finally:
            if was_active:
                self.kwargs["finished_callback"]()

    def close(self) -> None:
        self.closed = True

    def push(self, samples: list[float], *, status: object = None) -> None:
        block = np.asarray(samples, dtype=np.float32).reshape((-1, 1))
        callback = self.kwargs["callback"]
        try:
            callback(block, len(block), None, status)
        except (FakeCallbackStop, FakeCallbackAbort):
            self.active = False
            self.kwargs["finished_callback"]()

    def finish_unexpectedly(self) -> None:
        self.active = False
        self.kwargs["finished_callback"]()


class FakeSoundDevice:
    CallbackStop = FakeCallbackStop
    CallbackAbort = FakeCallbackAbort

    def __init__(
        self,
        devices: list[dict[str, object]],
        *,
        default_input: int | None,
        rejected_sample_rates: set[int] | None = None,
    ) -> None:
        self._devices = devices
        input_index = default_input if default_input is not None else -1
        default_pair = FakeInputOutputPair(input_index, 9)
        self.default = SimpleNamespace(device=default_pair)
        self.streams: list[FakeStream] = []
        self.next_start_error: Exception | None = None
        self.rejected_sample_rates = rejected_sample_rates or set()

    def query_devices(self) -> list[dict[str, object]]:
        return self._devices

    def query_hostapis(self) -> list[dict[str, object]]:
        return [
            {"name": "MME"},
            {"name": "DirectSound"},
            {"name": "ASIO"},
            {"name": "Windows WASAPI"},
            {"name": "Windows WDM-KS"},
        ]

    def InputStream(self, **kwargs: Any) -> FakeStream:
        stream = FakeStream(**kwargs)
        sample_rate = int(kwargs["samplerate"])
        stream.start_error = (
            RuntimeError("invalid sample rate")
            if sample_rate in self.rejected_sample_rates
            else self.next_start_error
        )
        self.streams.append(stream)
        return stream


def _backend() -> FakeSoundDevice:
    return FakeSoundDevice(
        [
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "USB microphone",
                "hostapi": 3,
                "max_input_channels": 2,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Laptop microphone",
                "hostapi": 4,
                "max_input_channels": 1,
                "default_samplerate": 44100.0,
            },
        ],
        default_input=2,
    )


def test_lists_only_input_devices_and_marks_default() -> None:
    recorder = SoundDeviceRecorder(sd_module=_backend())

    devices = recorder.list_devices()

    assert [(device.id, device.name) for device in devices] == [
        ("Windows WASAPI:USB microphone", "USB microphone"),
        ("Windows WDM-KS:Laptop microphone", "Laptop microphone"),
    ]
    assert [device.is_default for device in devices] == [False, True]
    assert devices[0].default_sample_rate == 48000.0


def test_duplicate_names_on_same_host_api_get_distinct_device_ids() -> None:
    backend = FakeSoundDevice(
        [
            {
                "name": "USB microphone",
                "hostapi": 3,
                "max_input_channels": 1,
                "default_samplerate": 48_000.0,
            },
            {
                "name": "USB microphone",
                "hostapi": 3,
                "max_input_channels": 1,
                "default_samplerate": 48_000.0,
            },
        ],
        default_input=0,
    )
    recorder = SoundDeviceRecorder(sd_module=backend)

    devices = recorder.list_devices()

    assert devices[0].id != devices[1].id
    recorder.start(devices[1].id)
    assert backend.streams[-1].kwargs["device"] == 1


def test_missing_pinned_device_falls_back_to_current_default() -> None:
    backend = _backend()
    recorder = SoundDeviceRecorder(sd_module=backend)

    recorder.start("404")

    stream = backend.streams[-1]
    assert stream.kwargs["device"] == 2
    assert stream.kwargs["samplerate"] == 16_000
    assert stream.kwargs["channels"] == 1
    assert stream.kwargs["dtype"] == "float32"
    assert recorder.active_device_id == "Windows WDM-KS:Laptop microphone"
    assert recorder.used_default_fallback is True


def test_capture_buffers_float32_samples_and_reports_level() -> None:
    backend = _backend()
    recorder = SoundDeviceRecorder(sd_module=backend)
    recorder.start("Windows WASAPI:USB microphone")

    backend.streams[-1].push([0.0, -0.5, 0.5, 1.0])
    audio = recorder.stop()

    assert np.asarray(audio.samples).dtype == np.float32
    np.testing.assert_allclose(audio.samples, [0.0, -0.5, 0.5, 1.0])
    assert audio.sample_rate == 16_000
    assert audio.channels == 1
    assert audio.duration_seconds == pytest.approx(4 / 16_000)
    assert recorder.input_level == pytest.approx(np.sqrt(0.375))
    assert backend.streams[-1].stopped is True
    assert backend.streams[-1].closed is True


def test_device_native_capture_is_resampled_when_16khz_is_rejected() -> None:
    backend = FakeSoundDevice(
        [
            {
                "name": "Native-only microphone",
                "hostapi": 3,
                "max_input_channels": 1,
                "default_samplerate": 48_000.0,
            }
        ],
        default_input=0,
        rejected_sample_rates={16_000},
    )
    recorder = SoundDeviceRecorder(sd_module=backend)

    recorder.start(None)
    backend.streams[-1].push(np.linspace(-0.5, 0.5, 480, dtype=np.float32).tolist())
    audio = recorder.stop()

    assert [stream.kwargs["samplerate"] for stream in backend.streams] == [16_000, 48_000]
    assert backend.streams[0].closed is True
    assert audio.sample_rate == 16_000
    assert len(audio.samples) == 160
    assert audio.duration_seconds == pytest.approx(0.01)
    assert np.asarray(audio.samples).dtype == np.float32


def test_cancel_closes_stream_and_discards_buffer() -> None:
    backend = _backend()
    recorder = SoundDeviceRecorder(sd_module=backend)
    recorder.start(None)
    backend.streams[-1].push([0.25, 0.5])

    recorder.cancel()

    assert backend.streams[-1].stopped is True
    assert backend.streams[-1].closed is True
    assert recorder.is_recording is False
    with pytest.raises(RecorderNotRunningError):
        recorder.stop()


def test_capture_stops_at_hard_limit_without_growing_buffer() -> None:
    backend = _backend()
    recorder = SoundDeviceRecorder(
        sd_module=backend,
        sample_rate=4,
        max_duration_seconds=1.0,
    )
    recorder.start(None)

    backend.streams[-1].push([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])

    assert recorder.limit_reached is True
    assert recorder.is_recording is False
    assert recorder.wait_for_completion(timeout=0) is RecordingCompletionReason.LIMIT_REACHED
    audio = recorder.stop()
    np.testing.assert_allclose(audio.samples, [0.1, 0.2, 0.3, 0.4])
    assert audio.duration_seconds == pytest.approx(1.0)


def test_default_hard_limit_is_ten_minutes() -> None:
    recorder = SoundDeviceRecorder(sd_module=_backend())

    assert recorder.max_duration_seconds == 10 * 60


def test_stop_failure_still_closes_stream_and_releases_recording() -> None:
    backend = _backend()
    recorder = SoundDeviceRecorder(sd_module=backend)
    recorder.start(None)
    backend.streams[-1].push([0.25])
    backend.streams[-1].stop_error = RuntimeError("device removed")

    with pytest.raises(RuntimeError, match="device removed"):
        recorder.stop()

    assert backend.streams[-1].closed is True
    assert recorder.is_recording is False


def test_callback_error_notifies_owner_and_discards_audio() -> None:
    class DeviceErrorStatus:
        def __bool__(self) -> bool:
            return True

        def __str__(self) -> str:
            return "device unavailable"

    backend = _backend()
    recorder = SoundDeviceRecorder(sd_module=backend)
    recorder.start(None)

    backend.streams[-1].push([0.25], status=DeviceErrorStatus())

    assert recorder.wait_for_completion(timeout=0) is RecordingCompletionReason.CAPTURE_ERROR
    assert recorder.is_recording is False
    with pytest.raises(AudioCaptureError, match="device unavailable"):
        recorder.stop()
    assert recorder.is_recording is False


def test_unexpected_stream_finish_notifies_owner_and_discards_audio() -> None:
    backend = _backend()
    recorder = SoundDeviceRecorder(sd_module=backend)
    recorder.start(None)
    backend.streams[-1].push([0.25])

    backend.streams[-1].finish_unexpectedly()

    assert recorder.wait_for_completion(timeout=0) is RecordingCompletionReason.DEVICE_STOPPED
    with pytest.raises(AudioCaptureError, match="stopped unexpectedly"):
        recorder.stop()


def test_device_query_error_has_a_domain_specific_exception() -> None:
    class BrokenSoundDevice(FakeSoundDevice):
        def query_devices(self) -> list[dict[str, object]]:
            raise RuntimeError("PortAudio unavailable")

    recorder = SoundDeviceRecorder(sd_module=BrokenSoundDevice([], default_input=None))

    with pytest.raises(AudioDeviceError, match="enumerate"):
        recorder.list_devices()


def test_device_that_rejects_16khz_is_closed_and_reported() -> None:
    backend = _backend()
    backend.next_start_error = RuntimeError("invalid sample rate")
    recorder = SoundDeviceRecorder(sd_module=backend)

    with pytest.raises(AudioDeviceError, match="16 kHz"):
        recorder.start(None)

    assert backend.streams[-1].closed is True
    assert recorder.is_recording is False


def test_pinned_device_identity_survives_portaudio_index_reordering() -> None:
    pinned_id = _backend()
    original = SoundDeviceRecorder(sd_module=pinned_id).list_devices()[0].id
    reordered = FakeSoundDevice(
        [
            {
                "name": "Laptop microphone",
                "hostapi": 4,
                "max_input_channels": 1,
                "default_samplerate": 44100.0,
            },
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "USB microphone",
                "hostapi": 3,
                "max_input_channels": 2,
                "default_samplerate": 48000.0,
            },
        ],
        default_input=0,
    )
    recorder = SoundDeviceRecorder(sd_module=reordered)

    recorder.start(original)

    assert reordered.streams[-1].kwargs["device"] == 2
    assert recorder.active_device_id == "Windows WASAPI:USB microphone"
    assert recorder.used_default_fallback is False
