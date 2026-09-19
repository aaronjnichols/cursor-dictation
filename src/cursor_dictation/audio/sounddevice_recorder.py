from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from threading import Event, RLock
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from cursor_dictation.audio.recorder import (
    AudioCaptureError,
    AudioDevice,
    AudioDeviceError,
    RecorderAlreadyRunningError,
    RecorderNotRunningError,
    RecordingCompletionReason,
)
from cursor_dictation.core.models import RecordedAudio

DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_MAX_DURATION_SECONDS = 10 * 60.0


class _DefaultDevice(Protocol):
    device: object


class _IndexableDevicePair(Protocol):
    def __getitem__(self, index: int) -> object: ...


class _InputStream(Protocol):
    @property
    def active(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class _SoundDeviceApi(Protocol):
    default: _DefaultDevice
    CallbackAbort: type[BaseException]
    CallbackStop: type[BaseException]

    def query_devices(self) -> Sequence[Mapping[str, object]]: ...

    def query_hostapis(self) -> Sequence[Mapping[str, object]]: ...

    def InputStream(self, **kwargs: object) -> _InputStream: ...


class SoundDeviceRecorder:
    """Capture mono float32 audio in memory through PortAudio."""

    def __init__(
        self,
        *,
        sd_module: _SoundDeviceApi | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        if sd_module is None:
            import sounddevice

            sd_module = cast(_SoundDeviceApi, sounddevice)

        self._sd = sd_module
        self._sample_rate = sample_rate
        self._max_duration_seconds = float(max_duration_seconds)
        self._max_samples = int(sample_rate * max_duration_seconds)
        self._capture_sample_rate = sample_rate
        if self._max_samples <= 0:
            raise ValueError("max_duration_seconds is shorter than one sample")

        self._lock = RLock()
        self._stream: _InputStream | None = None
        self._blocks: list[NDArray[np.float32]] = []
        self._sample_count = 0
        self._input_level = 0.0
        self._limit_reached = False
        self._active_device_id: str | None = None
        self._used_default_fallback = False
        self._completion_event = Event()
        self._completion_reason: RecordingCompletionReason | None = None
        self._capture_error_message: str | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            stream = self._stream
            return stream is not None and _stream_is_active(stream)

    @property
    def max_duration_seconds(self) -> float:
        return self._max_duration_seconds

    @property
    def input_level(self) -> float:
        with self._lock:
            return self._input_level

    @property
    def limit_reached(self) -> bool:
        with self._lock:
            return self._limit_reached

    @property
    def active_device_id(self) -> str | None:
        with self._lock:
            return self._active_device_id

    @property
    def used_default_fallback(self) -> bool:
        with self._lock:
            return self._used_default_fallback

    def wait_for_completion(self, timeout: float | None = None) -> RecordingCompletionReason | None:
        if not self._completion_event.wait(timeout):
            return None
        with self._lock:
            return self._completion_reason

    def list_devices(self) -> tuple[AudioDevice, ...]:
        devices = self._query_devices()
        host_api_names = self._query_host_api_names()
        device_ids = _stable_device_ids(devices, host_api_names=host_api_names)
        default_index = self._default_input_index(devices)
        found: list[AudioDevice] = []
        for index, item in enumerate(devices):
            channels = _integer_value(item.get("max_input_channels"), default=0)
            if channels <= 0:
                continue
            found.append(
                AudioDevice(
                    id=device_ids[index],
                    name=str(item.get("name", f"Input device {index}")),
                    max_input_channels=channels,
                    default_sample_rate=_float_value(item.get("default_samplerate")),
                    is_default=index == default_index,
                )
            )
        return tuple(found)

    def start(self, device_id: str | None) -> None:
        with self._lock:
            if self._stream is not None:
                raise RecorderAlreadyRunningError("A recording is already in progress")

        devices = self._query_devices()
        host_api_names = self._query_host_api_names()
        device_ids = _stable_device_ids(devices, host_api_names=host_api_names)
        input_indexes = {
            device_ids[index]: index
            for index, item in enumerate(devices)
            if _integer_value(item.get("max_input_channels"), default=0) > 0
        }
        default_index = self._default_input_index(devices)
        default_id = device_ids[default_index] if default_index is not None else None
        requested_exists = device_id is not None and device_id in input_indexes

        if requested_exists:
            selected_id = device_id
            used_fallback = False
        else:
            selected_id = default_id
            used_fallback = device_id is not None

        selected_index = input_indexes.get(selected_id) if selected_id is not None else None
        capture_rates = [self._sample_rate]
        if selected_index is not None:
            native_rate = round(_float_value(devices[selected_index].get("default_samplerate")))
            if native_rate > 0 and native_rate != self._sample_rate:
                capture_rates.append(native_rate)

        last_error: Exception | None = None
        for capture_rate in capture_rates:
            try:
                self._start_stream(
                    selected_index=selected_index,
                    selected_id=selected_id,
                    used_fallback=used_fallback,
                    capture_rate=capture_rate,
                )
            except Exception as error:
                last_error = error
                continue
            return
        raise AudioDeviceError(
            "Selected microphone could not open at 16 kHz mono or its native sample rate"
        ) from last_error

    def stop(self) -> RecordedAudio:
        with self._lock:
            stream = self._stream
            if stream is None:
                raise RecorderNotRunningError("No recording is in progress")
            if self._completion_reason is None:
                if _stream_is_active(stream):
                    self._completion_reason = RecordingCompletionReason.MANUAL_STOP
                else:
                    self._completion_reason = RecordingCompletionReason.DEVICE_STOPPED
                    self._capture_error_message = "Input stream stopped unexpectedly"

        try:
            self._stop_and_close(stream)
        except BaseException:
            with self._lock:
                self._blocks = []
                self._sample_count = 0
                self._input_level = 0.0
                self._limit_reached = False
                self._stream = None
                self._active_device_id = None
            raise
        with self._lock:
            completion_reason = self._completion_reason
            capture_error_message = self._capture_error_message
            blocks = self._blocks
            capture_sample_rate = self._capture_sample_rate
            self._blocks = []
            self._sample_count = 0
            self._stream = None
            self._active_device_id = None

        if completion_reason in {
            RecordingCompletionReason.CAPTURE_ERROR,
            RecordingCompletionReason.DEVICE_STOPPED,
        }:
            blocks.clear()
            raise AudioCaptureError(capture_error_message or "Input stream stopped unexpectedly")

        if blocks:
            samples = np.concatenate(blocks).astype(np.float32, copy=False)
        else:
            samples = np.empty(0, dtype=np.float32)
        samples = _resample_mono(
            samples,
            input_sample_rate=capture_sample_rate,
            output_sample_rate=self._sample_rate,
        )
        return RecordedAudio(
            samples=cast(Sequence[float], samples),
            sample_rate=self._sample_rate,
            channels=1,
        )

    def cancel(self) -> None:
        with self._lock:
            stream = self._stream
            if stream is None:
                self._blocks = []
                self._sample_count = 0
                return
            if self._completion_reason is None:
                self._completion_reason = RecordingCompletionReason.CANCELLED

        try:
            self._stop_and_close(stream)
        finally:
            with self._lock:
                self._blocks = []
                self._sample_count = 0
                self._input_level = 0.0
                self._limit_reached = False
                self._stream = None
                self._active_device_id = None

    def _query_devices(self) -> Sequence[Mapping[str, object]]:
        try:
            return self._sd.query_devices()
        except Exception as error:
            raise AudioDeviceError("Could not enumerate input devices") from error

    def _start_stream(
        self,
        *,
        selected_index: int | None,
        selected_id: str | None,
        used_fallback: bool,
        capture_rate: int,
    ) -> None:
        with self._lock:
            self._completion_event.clear()
            self._completion_reason = None
            self._capture_error_message = None
        stream = self._sd.InputStream(
            device=selected_index,
            samplerate=capture_rate,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
            finished_callback=self._stream_finished_callback,
        )
        with self._lock:
            self._blocks = []
            self._sample_count = 0
            self._max_samples = int(capture_rate * self._max_duration_seconds)
            self._capture_sample_rate = capture_rate
            self._input_level = 0.0
            self._limit_reached = False
            self._active_device_id = selected_id
            self._used_default_fallback = used_fallback
            self._stream = stream

        try:
            stream.start()
        except Exception:
            self._close_failed_start(stream)
            raise

    def _query_host_api_names(self) -> Mapping[int, str]:
        try:
            host_apis = self._sd.query_hostapis()
        except Exception as error:
            raise AudioDeviceError("Could not enumerate audio host APIs") from error
        return {index: str(item.get("name", index)) for index, item in enumerate(host_apis)}

    def _default_input_index(self, devices: Sequence[Mapping[str, object]]) -> int | None:
        try:
            raw_default = self._sd.default.device
            if not isinstance(raw_default, (int, str)):
                raw_default = cast(_IndexableDevicePair, raw_default)[0]
            index = int(cast(int | str, raw_default))
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        if index < 0 or index >= len(devices):
            return None
        channels = _integer_value(devices[index].get("max_input_channels"), default=0)
        return index if channels > 0 else None

    def _audio_callback(
        self,
        input_data: NDArray[np.float32],
        _frames: int,
        _time_info: object,
        status: object,
    ) -> None:
        if bool(status):
            with self._lock:
                self._completion_reason = RecordingCompletionReason.CAPTURE_ERROR
                self._capture_error_message = str(status)
            raise self._sd.CallbackAbort()

        block = np.asarray(input_data, dtype=np.float32).reshape(-1).copy()
        reached_limit = False
        with self._lock:
            if self._stream is None or self._limit_reached:
                return
            remaining = self._max_samples - self._sample_count
            if remaining <= 0:
                self._limit_reached = True
                self._completion_reason = RecordingCompletionReason.LIMIT_REACHED
                reached_limit = True
            else:
                accepted = block[:remaining]
                if accepted.size:
                    self._blocks.append(accepted)
                    self._sample_count += int(accepted.size)
                    rms = float(np.sqrt(np.mean(np.square(accepted, dtype=np.float32))))
                    self._input_level = min(1.0, rms)
                if self._sample_count >= self._max_samples:
                    self._limit_reached = True
                    self._completion_reason = RecordingCompletionReason.LIMIT_REACHED
                    reached_limit = True

        if reached_limit:
            raise self._sd.CallbackStop()

    def _stream_finished_callback(self) -> None:
        with self._lock:
            if self._completion_reason is None:
                self._completion_reason = RecordingCompletionReason.DEVICE_STOPPED
                self._capture_error_message = "Input stream stopped unexpectedly"
            self._completion_event.set()

    def _close_failed_start(self, stream: _InputStream) -> None:
        try:
            stream.close()
        except Exception:
            pass
        finally:
            with self._lock:
                self._stream = None
                self._blocks = []
                self._sample_count = 0
                self._active_device_id = None

    @staticmethod
    def _stop_and_close(stream: _InputStream) -> None:
        try:
            stream.stop()
        finally:
            stream.close()


def _integer_value(value: object, *, default: int) -> int:
    try:
        return int(cast(int | float | str, value))
    except (TypeError, ValueError):
        return default


def _float_value(value: object) -> float:
    try:
        return float(cast(int | float | str, value))
    except (TypeError, ValueError):
        return 0.0


def _stable_device_id(
    device: Mapping[str, object],
    *,
    index: int,
    host_api_names: Mapping[int, str],
) -> str:
    host_api_index = _integer_value(device.get("hostapi"), default=-1)
    host_api = host_api_names.get(host_api_index, f"hostapi-{host_api_index}")
    name = str(device.get("name", f"Input device {index}"))
    return f"{host_api}:{name}"


def _stable_device_ids(
    devices: Sequence[Mapping[str, object]],
    *,
    host_api_names: Mapping[int, str],
) -> dict[int, str]:
    base_ids = {
        index: _stable_device_id(
            device,
            index=index,
            host_api_names=host_api_names,
        )
        for index, device in enumerate(devices)
        if _integer_value(device.get("max_input_channels"), default=0) > 0
    }
    counts = Counter(base_ids.values())
    ordinals: Counter[str] = Counter()
    unique: dict[int, str] = {}
    for index, base_id in base_ids.items():
        if counts[base_id] == 1:
            unique[index] = base_id
            continue
        ordinals[base_id] += 1
        unique[index] = f"{base_id} [{ordinals[base_id]}]"
    return unique


def _stream_is_active(stream: _InputStream) -> bool:
    try:
        return bool(stream.active)
    except Exception:
        return False


def _resample_mono(
    samples: NDArray[np.float32],
    *,
    input_sample_rate: int,
    output_sample_rate: int,
) -> NDArray[np.float32]:
    if samples.size == 0 or input_sample_rate == output_sample_rate:
        return samples
    output_count = max(1, round(samples.size * output_sample_rate / input_sample_rate))
    source_positions = np.arange(output_count, dtype=np.float64) * (
        input_sample_rate / output_sample_rate
    )
    source_positions = np.minimum(source_positions, samples.size - 1)
    resampled = np.interp(
        source_positions,
        np.arange(samples.size, dtype=np.float64),
        samples,
    )
    return resampled.astype(np.float32, copy=False)
