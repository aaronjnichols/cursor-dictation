from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
import time
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import numpy as np

from cursor_dictation.core.models import RecordedAudio
from cursor_dictation.transcription.engine import TranscriptionEngine
from cursor_dictation.transcription.faster_whisper_engine import FasterWhisperEngine


class BenchmarkError(RuntimeError):
    """The benchmark input or configuration is invalid."""


@dataclass(frozen=True, slots=True)
class ProcessMemory:
    working_set_bytes: int
    peak_working_set_bytes: int


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    runs: int
    load_time_seconds: float
    audio_duration_seconds: float
    median_inference_seconds: float
    real_time_factor: float
    output_character_count: int
    working_set_bytes: int | None
    peak_working_set_bytes: int | None

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "runs": self.runs,
            "load_time_seconds": self.load_time_seconds,
            "audio_duration_seconds": self.audio_duration_seconds,
            "median_inference_seconds": self.median_inference_seconds,
            "real_time_factor": self.real_time_factor,
            "output_character_count": self.output_character_count,
            "working_set_bytes": self.working_set_bytes,
            "peak_working_set_bytes": self.peak_working_set_bytes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


class _Win32Api(Protocol):
    def GetCurrentProcess(self) -> object: ...


class _Win32Process(Protocol):
    def GetProcessMemoryInfo(self, process: object) -> Mapping[str, object]: ...


def load_pcm_wav(path: Path) -> RecordedAudio:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            compression = handle.getcomptype()
            frame_count = handle.getnframes()
            payload = handle.readframes(frame_count)
    except (OSError, EOFError, wave.Error) as error:
        raise BenchmarkError(f"Could not read WAV file: {path}") from error

    if sample_rate != 16_000:
        raise BenchmarkError("Benchmark WAV must use a 16 kHz sample rate")
    if channels != 1:
        raise BenchmarkError("Benchmark WAV must be mono")
    if sample_width != 2:
        raise BenchmarkError("Benchmark WAV must use 16-bit PCM samples")
    if compression != "NONE":
        raise BenchmarkError("Benchmark WAV must use uncompressed PCM")
    if frame_count == 0:
        raise BenchmarkError("Benchmark WAV contains no audio frames")
    if len(payload) != frame_count * channels * sample_width:
        raise BenchmarkError("Benchmark WAV ended before all audio frames were read")

    integer_samples = np.frombuffer(payload, dtype="<i2")
    samples = (integer_samples.astype(np.float32) / np.float32(32768.0)).astype(
        np.float32,
        copy=False,
    )
    return RecordedAudio(
        samples=cast(Sequence[float], samples),
        sample_rate=sample_rate,
        channels=channels,
    )


def run_benchmark(
    *,
    model_path: Path,
    wav_path: Path,
    runs: int = 5,
    engine_factory: Callable[[], TranscriptionEngine] = FasterWhisperEngine,
    timer: Callable[[], float] = time.perf_counter,
    memory_reader: Callable[[], ProcessMemory | None] | None = None,
) -> BenchmarkResult:
    if runs < 1:
        raise BenchmarkError("runs must be at least 1")

    audio = load_pcm_wav(wav_path)
    engine = engine_factory()
    resolved_model_path = model_path.resolve()

    load_started = timer()
    engine.load(resolved_model_path)
    load_time = timer() - load_started

    engine.transcribe(audio, language="en", vocabulary=())

    inference_times: list[float] = []
    output_character_count = 0
    for _ in range(runs):
        inference_started = timer()
        transcript = engine.transcribe(audio, language="en", vocabulary=())
        inference_times.append(timer() - inference_started)
        output_character_count = len(transcript.text)

    median_inference = statistics.median(inference_times)
    duration = audio.duration_seconds
    memory = (memory_reader or read_windows_process_memory)()
    return BenchmarkResult(
        runs=runs,
        load_time_seconds=load_time,
        audio_duration_seconds=duration,
        median_inference_seconds=median_inference,
        real_time_factor=median_inference / duration,
        output_character_count=output_character_count,
        working_set_bytes=memory.working_set_bytes if memory is not None else None,
        peak_working_set_bytes=memory.peak_working_set_bytes if memory is not None else None,
    )


def read_windows_process_memory() -> ProcessMemory | None:
    if sys.platform != "win32":
        return None
    try:
        win32api = cast(_Win32Api, importlib.import_module("win32api"))
        win32process = cast(_Win32Process, importlib.import_module("win32process"))
        raw = win32process.GetProcessMemoryInfo(win32api.GetCurrentProcess())
        working_set = _positive_integer(raw.get("WorkingSetSize"))
        peak_working_set = _positive_integer(raw.get("PeakWorkingSetSize"))
    except Exception:
        return None
    if working_set is None or peak_working_set is None:
        return None
    return ProcessMemory(
        working_set_bytes=working_set,
        peak_working_set_bytes=peak_working_set,
    )


def _positive_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark an already-downloaded local CTranslate2 Whisper model.",
    )
    parser.add_argument("model_path", type=Path, help="Local CTranslate2 model directory")
    parser.add_argument("wav_path", type=Path, help="16 kHz mono 16-bit PCM WAV fixture")
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of timed inference runs after one warm-up (default: 5)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    arguments = parser.parse_args(argv)
    try:
        result = run_benchmark(
            model_path=cast(Path, arguments.model_path),
            wav_path=cast(Path, arguments.wav_path),
            runs=cast(int, arguments.runs),
        )
    except Exception as error:
        parser.exit(1, f"benchmark failed: {error}\n")
    print(result.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
