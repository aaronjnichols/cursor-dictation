from __future__ import annotations

import json
import wave
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import scripts.benchmark_model as benchmark_module
from cursor_dictation.core.models import RecordedAudio, Transcript
from cursor_dictation.transcription.engine import ModelInfo
from scripts.benchmark_model import (
    BenchmarkError,
    BenchmarkResult,
    ProcessMemory,
    load_pcm_wav,
    main,
    read_windows_process_memory,
    run_benchmark,
)


class FakeEngine:
    def __init__(self, text: str = "private transcript") -> None:
        self.text = text
        self.loaded_path: Path | None = None
        self.transcribe_calls = 0

    def load(self, model_path: Path) -> ModelInfo:
        self.loaded_path = model_path
        return ModelInfo(path=model_path, device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript:
        assert audio.sample_rate == 16_000
        assert audio.channels == 1
        assert language == "en"
        assert vocabulary == ()
        self.transcribe_calls += 1
        return Transcript(self.text)


def _write_wav(
    path: Path,
    *,
    samples: Sequence[int],
    sample_rate: int = 16_000,
    channels: int = 1,
    sample_width: int = 2,
) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        if sample_width == 2:
            data = np.asarray(samples, dtype="<i2").tobytes()
        else:
            data = np.asarray(samples, dtype=np.uint8).tobytes()
        handle.writeframes(data)


def test_load_pcm_wav_reads_16khz_mono_16bit_samples(tmp_path: Path) -> None:
    wav_path = tmp_path / "fixture.wav"
    _write_wav(wav_path, samples=(-32768, 0, 32767))

    audio = load_pcm_wav(wav_path)

    assert audio.sample_rate == 16_000
    assert audio.channels == 1
    assert audio.duration_seconds == pytest.approx(3 / 16_000)
    assert np.asarray(audio.samples).dtype == np.float32
    np.testing.assert_allclose(audio.samples, [-1.0, 0.0, 32767 / 32768])


@pytest.mark.parametrize(
    ("sample_rate", "channels", "sample_width", "samples", "message"),
    [
        (8_000, 1, 2, (0,), "16 kHz"),
        (16_000, 2, 2, (0, 0), "mono"),
        (16_000, 1, 1, (128,), "16-bit"),
        (16_000, 1, 2, (), "no audio frames"),
    ],
)
def test_load_pcm_wav_rejects_unsupported_or_empty_audio(
    tmp_path: Path,
    sample_rate: int,
    channels: int,
    sample_width: int,
    samples: Sequence[int],
    message: str,
) -> None:
    wav_path = tmp_path / "invalid.wav"
    _write_wav(
        wav_path,
        samples=samples,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )

    with pytest.raises(BenchmarkError, match=message):
        load_pcm_wav(wav_path)


def test_run_benchmark_warms_once_and_reports_median_without_text(tmp_path: Path) -> None:
    wav_path = tmp_path / "one-second.wav"
    _write_wav(wav_path, samples=[0] * 16_000)
    model_path = tmp_path / "model"
    model_path.mkdir()
    engine = FakeEngine()
    clock_values = iter((10.0, 10.5, 20.0, 20.2, 30.0, 30.4, 40.0, 40.3))

    result = run_benchmark(
        model_path=model_path,
        wav_path=wav_path,
        runs=3,
        engine_factory=lambda: engine,
        timer=lambda: next(clock_values),
        memory_reader=lambda: ProcessMemory(
            working_set_bytes=100_000,
            peak_working_set_bytes=200_000,
        ),
    )

    assert engine.loaded_path == model_path.resolve()
    assert engine.transcribe_calls == 4
    assert result.load_time_seconds == pytest.approx(0.5)
    assert result.audio_duration_seconds == pytest.approx(1.0)
    assert result.median_inference_seconds == pytest.approx(0.3)
    assert result.real_time_factor == pytest.approx(0.3)
    assert result.output_character_count == len(engine.text)
    assert result.working_set_bytes == 100_000
    assert result.peak_working_set_bytes == 200_000
    serialized = result.to_json()
    assert engine.text not in serialized
    assert "transcript" not in serialized.lower()


def test_run_benchmark_allows_unavailable_windows_memory(tmp_path: Path) -> None:
    wav_path = tmp_path / "short.wav"
    _write_wav(wav_path, samples=[0] * 16)
    model_path = tmp_path / "model"
    model_path.mkdir()
    clock_values = iter((0.0, 0.1, 1.0, 1.2))

    result = run_benchmark(
        model_path=model_path,
        wav_path=wav_path,
        runs=1,
        engine_factory=FakeEngine,
        timer=lambda: next(clock_values),
        memory_reader=lambda: None,
    )

    assert result.working_set_bytes is None
    assert result.peak_working_set_bytes is None


def test_run_benchmark_rejects_nonpositive_run_count(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkError, match="runs"):
        run_benchmark(
            model_path=tmp_path / "model",
            wav_path=tmp_path / "audio.wav",
            runs=0,
        )


def test_main_prints_json_and_honors_run_count(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    captured_runs: list[int] = []
    expected = BenchmarkResult(
        runs=7,
        load_time_seconds=1.0,
        audio_duration_seconds=2.0,
        median_inference_seconds=0.5,
        real_time_factor=0.25,
        output_character_count=42,
        working_set_bytes=None,
        peak_working_set_bytes=None,
    )

    def fake_run_benchmark(*, model_path: Path, wav_path: Path, runs: int) -> BenchmarkResult:
        assert model_path == (tmp_path / "model")
        assert wav_path == (tmp_path / "audio.wav")
        captured_runs.append(runs)
        return expected

    monkeypatch.setattr("scripts.benchmark_model.run_benchmark", fake_run_benchmark)

    exit_code = main([str(tmp_path / "model"), str(tmp_path / "audio.wav"), "--runs", "7"])

    assert exit_code == 0
    assert captured_runs == [7]
    assert json.loads(capsys.readouterr().out) == expected.to_dict()


def test_windows_memory_reader_returns_working_set_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def memory_info(process: object) -> dict[str, int]:
        assert process == "process"
        return {"WorkingSetSize": 123, "PeakWorkingSetSize": 456}

    modules = {
        "win32api": SimpleNamespace(GetCurrentProcess=lambda: "process"),
        "win32process": SimpleNamespace(GetProcessMemoryInfo=memory_info),
    }
    monkeypatch.setattr(benchmark_module.sys, "platform", "win32")
    monkeypatch.setattr(
        benchmark_module.importlib,
        "import_module",
        lambda name: modules[name],
    )

    assert read_windows_process_memory() == ProcessMemory(
        working_set_bytes=123,
        peak_working_set_bytes=456,
    )


def test_windows_memory_reader_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_import(_name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(benchmark_module.sys, "platform", "win32")
    monkeypatch.setattr(
        benchmark_module.importlib,
        "import_module",
        missing_import,
    )

    assert read_windows_process_memory() is None
