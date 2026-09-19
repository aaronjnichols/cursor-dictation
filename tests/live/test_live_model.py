from __future__ import annotations

import os
from pathlib import Path

import pytest

from cursor_dictation.transcription.faster_whisper_engine import FasterWhisperEngine
from scripts.benchmark_model import load_pcm_wav

_MODEL_PATH = os.environ.get("CURSOR_DICTATION_MODEL_PATH")
_AUDIO_PATH = os.environ.get("CURSOR_DICTATION_AUDIO_FIXTURE")

pytestmark = [
    pytest.mark.live_model,
    pytest.mark.skipif(
        not _MODEL_PATH or not _AUDIO_PATH,
        reason=(
            "set CURSOR_DICTATION_MODEL_PATH and CURSOR_DICTATION_AUDIO_FIXTURE "
            "to run offline inference"
        ),
    ),
]


def test_local_model_transcribes_fixture_with_hub_forced_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _MODEL_PATH is not None
    assert _AUDIO_PATH is not None
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    audio = load_pcm_wav(Path(_AUDIO_PATH))
    engine = FasterWhisperEngine()

    engine.load(Path(_MODEL_PATH))
    transcript = engine.transcribe(audio, language="en", vocabulary=())

    assert transcript.text.strip()
