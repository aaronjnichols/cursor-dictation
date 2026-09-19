from __future__ import annotations

import json
from pathlib import Path

import pytest

from cursor_dictation.diagnostics.logging import SafeEventLogger, configure_logging


def test_structured_log_contains_only_named_safe_fields(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    events = SafeEventLogger(logger, component="transcription")

    events.info("transcription_completed", duration_ms=1234, model_id="small.en")
    for handler in logger.handlers:
        handler.flush()

    line = (tmp_path / "cursor-dictation.log").read_text(encoding="utf-8").strip()
    payload = json.loads(line)

    assert payload["event"] == "transcription_completed"
    assert payload["component"] == "transcription"
    assert payload["duration_ms"] == 1234
    assert payload["model_id"] == "small.en"
    assert "message" not in payload


@pytest.mark.parametrize("field", ["transcript", "text", "audio", "clipboard", "window_title"])
def test_logger_rejects_sensitive_or_unknown_fields(tmp_path: Path, field: str) -> None:
    events = SafeEventLogger(configure_logging(tmp_path), component="test")

    with pytest.raises(ValueError, match="not allowed"):
        events.info("bad_event", **{field: "private material"})


def test_configure_logging_is_idempotent(tmp_path: Path) -> None:
    first = configure_logging(tmp_path)
    second = configure_logging(tmp_path)

    assert first is second
    assert len(first.handlers) == 1
