from __future__ import annotations

from PySide6.QtWidgets import QLabel

from cursor_dictation.core.models import AppState
from cursor_dictation.ui.status_overlay import StatusOverlay


def test_overlay_maps_runtime_states_to_short_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.set_state(AppState.RECORDING)
    assert overlay.status_text == "Recording..."
    assert overlay.is_active

    overlay.set_state(AppState.TRANSCRIBING)
    assert overlay.status_text == "Transcribing locally..."
    assert overlay.is_active

    overlay.set_state(AppState.LOADING_MODEL)
    assert overlay.status_text == "Loading local model..."
    assert overlay.is_active

    overlay.set_state(AppState.IDLE)
    assert overlay.status_text == "Ready"
    assert not overlay.is_active


def test_overlay_can_show_busy_copy_and_error_feedback(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.show_busy()
    assert overlay.status_text == "Transcribing..."

    overlay.show_copied()
    assert overlay.status_text == "Copied"

    overlay.show_error("Microphone unavailable")
    assert overlay.status_text == "Microphone unavailable"


def test_unresolved_error_feedback_does_not_auto_dismiss(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)
    overlay.set_state(AppState.ERROR_WITH_TRANSCRIPT)

    overlay.show_error("Copy or discard the transcript")
    overlay._dismiss_feedback()  # type: ignore[attr-defined]

    assert overlay.isVisible()
    assert overlay.status_text == "Copy or discard the transcript"


def test_recording_warns_with_one_minute_left(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)
    overlay.set_state(AppState.RECORDING)

    overlay._display_recording_time(9 * 60)  # type: ignore[attr-defined]

    assert overlay.status_text == "Recording... 1 minute left"


def test_recording_waveform_reflects_input_level(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)
    waveform = overlay.findChild(QLabel, "statusWaveform")
    assert waveform is not None

    overlay.set_input_level(1.0)

    assert "█" in waveform.text()
