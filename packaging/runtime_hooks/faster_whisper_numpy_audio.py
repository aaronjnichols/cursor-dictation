"""Keep the frozen app on its supported in-memory NumPy audio path.

faster-whisper imports its optional file-decoding module at package import time.
Cursor Dictation never gives it file paths, so bundling PyAV and a full FFmpeg codec
distribution would add unused native code. This hook supplies the two small helpers
that faster-whisper imports while making unsupported file decoding fail explicitly.
"""

from __future__ import annotations

import sys
from types import ModuleType

import numpy as np


def decode_audio(*_args: object, **_kwargs: object) -> np.ndarray:
    raise RuntimeError("Frozen Cursor Dictation accepts in-memory audio only")


def pad_or_trim(array: np.ndarray, length: int = 3000, *, axis: int = -1) -> np.ndarray:
    if array.shape[axis] > length:
        array = array.take(indices=range(length), axis=axis)
    if array.shape[axis] < length:
        pad_widths = [(0, 0)] * array.ndim
        pad_widths[axis] = (0, length - array.shape[axis])
        array = np.pad(array, pad_widths)
    return array


audio_module = ModuleType("faster_whisper.audio")
audio_module.decode_audio = decode_audio  # type: ignore[attr-defined]
audio_module.pad_or_trim = pad_or_trim  # type: ignore[attr-defined]
sys.modules["faster_whisper.audio"] = audio_module
