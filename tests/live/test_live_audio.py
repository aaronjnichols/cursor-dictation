from __future__ import annotations

import os
import time

import pytest

from cursor_dictation.audio.sounddevice_recorder import SoundDeviceRecorder

pytestmark = [
    pytest.mark.live_audio,
    pytest.mark.skipif(
        os.environ.get("CURSOR_DICTATION_RUN_LIVE_AUDIO") != "1",
        reason="set CURSOR_DICTATION_RUN_LIVE_AUDIO=1 to open the default microphone",
    ),
]


def test_default_microphone_captures_in_memory() -> None:
    recorder = SoundDeviceRecorder(max_duration_seconds=2.0)

    devices = recorder.list_devices()
    assert devices, "Windows reported no input devices"

    recorder.start(None)
    try:
        time.sleep(0.75)
    finally:
        audio = recorder.stop()

    assert audio.sample_rate == 16_000
    assert audio.channels == 1
    assert len(audio.samples) >= 8_000
